"""Bounded in-process canary inbox; execution authorities remain canonical."""
from dataclasses import asdict, dataclass, fields
import fcntl
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import threading
import time

from sentinel.systemd_canary_live_observability import atomic_write, process_identity
from sentinel.live_remediation_activation_lease import TemporaryLiveRemediationActivationLease
from sentinel.remediation_action_catalog import RemediationActionEntry
from sentinel.resource_bound_remediation import build_bound_systemd_remediation_plan
from sentinel.systemd_commander_integration import SystemdCommanderIntegration
from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope, SystemdOperation, SystemdPrivilegeBoundary,
    SystemdReadOnlyInspector, SystemdUnitSnapshot,
)

UNIT = "airiv-sentinel-remediation-canary.service"
COMPONENT = "systemd:" + UNIT
ARGV = ("/usr/bin/systemctl", "--no-ask-password", "restart", UNIT)
MAX_BYTES = 4096
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CanaryLiveRequest:
    schema_version: int
    request_id: str
    approval_id: str
    created_at: float
    expires_at: float
    component_id: str
    unit: str
    action: str
    argv: tuple[str, ...]
    expected_pre_invocation_id: str

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("invalid_schema_version")
        if (self.component_id, self.unit, self.action, self.argv) != (
            COMPONENT, UNIT, "RESTART", ARGV
        ) or type(self.argv) is not tuple:
            raise ValueError("invalid_exact_target")
        for value in (self.request_id, self.approval_id):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
                raise ValueError("invalid_request_or_approval_id")
        if not isinstance(self.expected_pre_invocation_id, str) or not re.fullmatch(
            r"[0-9a-f]{32}", self.expected_pre_invocation_id
        ) or self.expected_pre_invocation_id == "0" * 32:
            raise ValueError("invalid_expected_invocation")
        for value in (self.created_at, self.expires_at):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("invalid_timestamp")
        if not 0 < self.expires_at - self.created_at <= 300:
            raise ValueError("invalid_request_lifetime")

    def validate_time(self, now):
        if not self.created_at <= now < self.expires_at:
            raise ValueError("request_outside_validity_window")

    @classmethod
    def parse(cls, raw, now):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate_field")
                result[key] = value
            return result
        if len(raw) > MAX_BYTES:
            raise ValueError("request_too_large")
        data = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(data, dict) or set(data) != {f.name for f in fields(cls)}:
            raise ValueError("invalid_schema_fields")
        if not isinstance(data["argv"], list):
            raise ValueError("invalid_argv")
        data["argv"] = tuple(data["argv"])
        request = cls(**data)
        request.validate_time(now)
        return request

    def build_plan(self, before):
        if not isinstance(before, SystemdUnitSnapshot):
            raise ValueError("invalid_pre_snapshot")
        if (before.identity.component_id != COMPONENT or not before.identity.live_eligible
                or before.load_state != "loaded" or before.active_state != "active"
                or before.invocation_id != self.expected_pre_invocation_id):
            raise ValueError("invalid_canary_precondition")
        scope = BoundSystemdActionScope(
            target=before.identity, operation=SystemdOperation.RESTART,
            privilege=SystemdPrivilegeBoundary(systemctl_binary=ARGV[0]),
            expected_pre_active_state="active", expected_post_active_state="active",
            require_new_invocation=True,
        )
        return build_bound_systemd_remediation_plan(
            before=before, scope=scope, run_id="canary-approval-" + self.approval_id,
            incident_id="canary-approval-" + self.approval_id, action=self.action,
            execution_id="canary-request-" + self.request_id,
            permit_id="canary-request-" + self.request_id,
        )


class SystemdCanaryLiveExecution:
    def __init__(self, commander, catalog, *, root=None, snapshot_provider=None, clock=time.time):
        repository = Path(__file__).resolve().parents[1]
        self.root = Path(root if root is not None else os.environ.get(
            "AIRIV_SENTINEL_RUNTIME_DIR", str(repository / "var" / "runtime")
        ))
        self.request_path = self.root / "systemd-canary-live-request.json"
        self.integration = SystemdCommanderIntegration(commander)
        self.catalog = catalog
        self.snapshot_provider = snapshot_provider or (lambda: SystemdReadOnlyInspector().inspect(UNIT))
        self.clock = clock
        self._lock = threading.RLock()
        self.state_path = self.root / "systemd-canary-live-state.json"
        self.evidence_path = self.root / "systemd-canary-live-evidence.json"
        self.last_result = None
        self.last_terminal_request_id = None
        self.last_terminal_outcome = None
        self._generation = 0
        self._cleanup_uncertain = False
        self._projection_failed = False

    def activation_facts(self):
        try:
            policy = self.integration.policy
            facts = dict(
                policy_activation_empty=not policy.allowed_actions,
                catalog_activation_empty=not (self.catalog.list_actions() or self.catalog.list_triggers()),
                bound_activation_empty=not policy.list_bound_runs(),
            )
            facts["activation_empty"] = all(facts.values()) and not (self._cleanup_uncertain or self._projection_failed)
            facts["cleanup_uncertain"] = self._cleanup_uncertain
            return facts
        except Exception:
            return dict(dict.fromkeys(("policy_activation_empty", "catalog_activation_empty",
                                      "bound_activation_empty", "activation_empty"), False),
                        cleanup_uncertain=self._cleanup_uncertain)

    def publish_state(self, phase, request=None):
        self._generation += 1
        atomic_write(self.root, self.state_path.name, dict(
            schema="systemd-canary-live-state", schema_version=1,
            process=process_identity(), generation=self._generation, timestamp=self.clock(),
            phase=phase, inbox_pending=os.path.lexists(self.request_path),
            active_request_id=request.request_id if request else None,
            active_approval_id=request.approval_id if request else None,
            last_terminal_request_id=self.last_terminal_request_id,
            last_terminal_outcome=self.last_terminal_outcome, **self.activation_facts(),
        ))

    def cycle(self):
        with self._lock:
            generation = self._generation
            result = self.poll_once()
            if generation == self._generation:
                self.publish_state("IDLE")
            return result

    def retain_evidence(self, request, plan, result, started, error):
        facts = self.activation_facts()
        outcome = "TERMINAL_SUCCESS" if (
            result is not None and result.recovered and error is None
            and facts["activation_empty"]
        ) else "TERMINAL_FAILURE"
        record = dict(schema="systemd-canary-live-evidence", schema_version=1,
                      process=process_identity(), request_id=None, approval_id=None,
                      started_at=started, finished_at=self.clock(), error=error,
                      terminal_outcome=outcome, cleanup_state=facts,
                      policy_result=None, execution_success=None, execution_exit_code=None,
                      verification_success=None, verification=None, replayed=None)
        if request is not None:
            record.update(asdict(request))
        if plan is not None:
            record.update(permit_id=plan.effect.permit_id, execution_id=plan.effect.execution_id,
                          effect_fingerprint=plan.effect.fingerprint,
                          pre_target_fingerprint=plan.before.identity.fingerprint,
                          pre_invocation_id=plan.before.invocation_id)
        # Read existing canonical identity evidence if verification raised before
        # the integration could return. Never claim, update, or replay a journal.
        identity = result.identity_record if result is not None else None
        if identity is None and plan is not None:
            identity = self.integration.commander.remediation_orchestrator.identity_boundary.journal.get(
                plan.effect.execution_id
            )
        if identity is not None:
            record["execution_identity_state"] = identity.state
            if identity.execution is not None:
                record["execution_exit_code"] = identity.execution["exit_code"]
                record["execution_success"] = identity.execution["exit_code"] == 0
        if result is not None:
            record.update(policy_result=asdict(result.authorization), replayed=result.replayed,
                          execution_success=result.execution.success if result.execution else None,
                          execution_exit_code=result.execution.exit_code if result.execution else None,
                          verification_success=result.verification.verified if result.verification else None,
                          verification=asdict(result.verification) if result.verification else None,
                          post_invocation_id=result.after.invocation_id if result.after else None,
                          post_target_fingerprint=result.after.identity.fingerprint if result.after else None)
        atomic_write(self.root, self.evidence_path.name, record)
        self.last_terminal_request_id = record["request_id"]
        self.last_terminal_outcome = outcome
        self.publish_state(outcome)

    def _consume(self):
        # No directory creation, observation, activation or journal claim on absence.
        try:
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        try:
            try:
                fd = os.open(self.request_path.name,
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
            except FileNotFoundError:
                return None
            with os.fdopen(fd, "rb") as stream:
                root_info = os.fstat(directory)
                if root_info.st_uid != os.getuid() or root_info.st_mode & 0o022:
                    raise ValueError("unsafe_inbox_directory")
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o022 or info.st_nlink != 1):
                    raise ValueError("unsafe_request_file")
                current = os.stat(self.request_path.name, dir_fd=directory, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("request_replaced")
                raw = stream.read(MAX_BYTES + 1)
                # Consume durably before any possible effect. A crash may lose a
                # request; it must never automatically retry an uncertain effect.
                os.unlink(self.request_path.name, dir_fd=directory)
                os.fsync(directory)
                return raw
        finally:
            os.close(directory)

    def poll_once(self):
        with self._lock:
            request = plan = result = None
            started = self.clock()
            error = None
            consumed = False
            try:
                raw = self._consume()
                if raw is None:
                    return None
                consumed = True
                request = CanaryLiveRequest.parse(raw, self.clock())
                self.publish_state("PROCESSING", request)
                policy = self.integration.policy
                if (policy.allowed_actions or policy.list_bound_runs()
                        or self.catalog.list_actions() or self.catalog.list_triggers()):
                    raise ValueError("production_activation_not_empty")
                plan = request.build_plan(self.snapshot_provider())
                request.validate_time(self.clock())
                entry = RemediationActionEntry(
                    action=request.action, command=" ".join(ARGV),
                    rationale="One-shot Commander approval " + request.approval_id,
                )
                lease = TemporaryLiveRemediationActivationLease(
                    policy=policy, catalog=self.catalog, effect=plan.effect, entry=entry,
                )
                try:
                    lease.activate()
                except BaseException:
                    self._cleanup_uncertain = True
                    raise
                try:
                    self.publish_state("PROCESSING", request)
                    result = self.integration.execute_verified(
                        plan=plan, incident_state="INVESTIGATING",
                        after_snapshot_provider=self.snapshot_provider,
                    )
                    self.last_result = result
                finally:
                    try:
                        if lease.close() is not True:
                            self._cleanup_uncertain = True
                    except BaseException:
                        # No reconciliation authority exists in this generation.
                        self._cleanup_uncertain = True
                        raise
            except Exception as exc:
                consumed = True
                error = type(exc).__name__
                logger.exception("Canary live request failed closed")
            finally:
                if consumed:
                    try:
                        self.retain_evidence(request, plan, result, started, error)
                    except Exception:
                        self._projection_failed = True
                        logger.exception("Canary projection persistence failed")
            return result
