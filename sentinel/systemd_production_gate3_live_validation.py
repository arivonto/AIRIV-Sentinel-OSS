"""Gate 3 one-shot live validation of the generic Commander production path.

The handler is dormant unless an exact private request file exists. The request
is consumed durably before any possible effect. It then composes the already
locked D8.16-D8.20 durable Commander path and Gate 2 explicit runtime path for
one exact dedicated probe service.

This module is validation-only. It does not broaden the production allowlist or
create an automatic remediation rule.
"""

from dataclasses import asdict, dataclass, fields
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_decider import CommanderIntentDecision
from sentinel.incidents.manager import Incident
from sentinel.live_remediation_activation_lease import (
    TemporaryLiveRemediationActivationLease,
)
from sentinel.remediation_action_catalog import RemediationActionEntry
from sentinel.systemd_canary_live_observability import atomic_write, process_identity
from sentinel.systemd_evidence import (
    TrustedSystemdEvidenceRecord,
    TrustedSystemdEvidenceStore,
)
from sentinel.systemd_incident_dispatch import (
    SystemdDispatchEvidenceIdentity,
    SystemdIncidentDispatchAssessment,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionStore,
)
from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer,
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_commander_activation_binding import (
    bind_systemd_production_commander_consumption_to_prepared_effect,
)
from sentinel.systemd_production_commander_activation_consumption import (
    consume_systemd_production_activation_from_commander_continuation,
)
from sentinel.systemd_production_commander_activation_issuance import (
    issue_systemd_production_activation_from_commander_continuation,
)
from sentinel.systemd_production_commander_authorization_handoff import (
    build_systemd_production_commander_authorization_context,
)
from sentinel.systemd_production_commander_incident_continuation import (
    build_systemd_production_commander_incident_continuation,
)
from sentinel.systemd_production_commander_resolution import (
    resolve_systemd_production_commander_result,
)
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    ProductionTargetMode,
    SystemdProductionTargetPolicy,
    SystemdProductionTargetRule,
)
from sentinel.systemd_remediation_safety import (
    SystemdPrivilegeBoundary,
    SystemdReadOnlyInspector,
    SystemdUnitSnapshot,
)


UNIT = "airiv-sentinel-production-remediation-probe.service"
COMPONENT = "systemd:" + UNIT
ARGV = ("/usr/bin/systemctl", "--no-ask-password", "restart", UNIT)
APPROVAL_ID = "GATE3-ONE-LIVE-GENERIC-PROBE-RESTART"
MAX_BYTES = 4096


def default_root() -> Path:
    return (
        Path.home()
        / ".local"
        / "state"
        / "airiv-sentinel-secure"
        / "gate3_generic_live_validation"
    )


@dataclass(frozen=True, slots=True)
class Gate3LiveRequest:
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
        if self.schema_version != 1 or type(self.schema_version) is not int:
            raise ValueError("invalid_schema_version")
        if self.approval_id != APPROVAL_ID:
            raise ValueError("invalid_gate3_approval")
        if (
            self.component_id,
            self.unit,
            self.action,
            self.argv,
        ) != (COMPONENT, UNIT, ACTION_RESTART, ARGV):
            raise ValueError("invalid_exact_gate3_target")
        if type(self.argv) is not tuple:
            raise ValueError("invalid_argv")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.request_id):
            raise ValueError("invalid_request_id")
        if not re.fullmatch(r"[0-9a-f]{32}", self.expected_pre_invocation_id):
            raise ValueError("invalid_expected_pre_invocation_id")
        if self.expected_pre_invocation_id == "0" * 32:
            raise ValueError("invalid_expected_pre_invocation_id")
        for value in (self.created_at, self.expires_at):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("invalid_timestamp")
        if not 0 < self.expires_at - self.created_at <= 300:
            raise ValueError("invalid_request_lifetime")

    def validate_time(self, now):
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("invalid_now")
        if not self.created_at <= now < self.expires_at:
            raise ValueError("request_outside_validity_window")

    @classmethod
    def parse(cls, raw: bytes, now: float):
        if len(raw) > MAX_BYTES:
            raise ValueError("request_too_large")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate_field")
                result[key] = value
            return result

        data = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(data, dict) or set(data) != {field.name for field in fields(cls)}:
            raise ValueError("invalid_schema_fields")
        if not isinstance(data["argv"], list):
            raise ValueError("invalid_argv")
        data["argv"] = tuple(data["argv"])
        request = cls(**data)
        request.validate_time(now)
        return request


class SystemdProductionGate3LiveValidation:
    """Daemon-owned one-shot Gate 3 validation surface."""

    def __init__(
        self,
        runtime,
        *,
        root=None,
        snapshot_provider=None,
        clock=time.time,
    ):
        # Avoid importing SentinelRuntime here: runtime owns this child and a
        # reverse import would create a composition cycle.
        required = (
            "policy",
            "incident_manager",
            "remediation_action_catalog",
            "systemd_production_preparation",
            "systemd_production_integration",
            "invoke_systemd_production_remediation",
        )
        if any(not hasattr(runtime, name) for name in required):
            raise TypeError("canonical Sentinel runtime composition required")

        self.runtime = runtime
        self.root = Path(root) if root is not None else default_root()
        self.request_path = self.root / "gate3-live-request.json"
        self.evidence_path = self.root / "gate3-live-evidence.json"
        self.snapshot_provider = snapshot_provider or (
            lambda: SystemdReadOnlyInspector().inspect(UNIT)
        )
        self.clock = clock
        self.last_result = None

    def cycle(self):
        raw = self._consume()
        if raw is None:
            return None
        return self._process(raw)

    def _consume(self):
        try:
            directory = os.open(
                self.root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except FileNotFoundError:
            return None

        try:
            try:
                fd = os.open(
                    self.request_path.name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory,
                )
            except FileNotFoundError:
                return None

            with os.fdopen(fd, "rb") as stream:
                root_info = os.fstat(directory)
                if root_info.st_uid != os.getuid() or root_info.st_mode & 0o022:
                    raise ValueError("unsafe_gate3_inbox_directory")
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o022
                    or info.st_nlink != 1
                ):
                    raise ValueError("unsafe_gate3_request_file")
                current = os.stat(
                    self.request_path.name,
                    dir_fd=directory,
                    follow_symlinks=False,
                )
                if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("gate3_request_replaced")
                raw = stream.read(MAX_BYTES + 1)
                # Single-use before effect: a crash may lose this request but
                # must never replay an uncertain production restart.
                os.unlink(self.request_path.name, dir_fd=directory)
                os.fsync(directory)
                return raw
        finally:
            os.close(directory)

    def _activation_empty(self):
        policy = self.runtime.policy
        catalog = self.runtime.remediation_action_catalog
        return (
            not policy.allowed_actions
            and not policy.list_bound_runs()
            and not policy.list_systemd_production_targets()
            and not catalog.list_actions()
            and not catalog.list_triggers()
        )

    def _build_commander_path(self, request, before, now, incident):
        if type(incident) is not Incident:
            raise TypeError("canonical Gate 3 incident required")
        if (
            incident.component_id != COMPONENT
            or incident.status != "INVESTIGATING"
            or self.runtime.incident_manager.get_active_incident(COMPONENT)
            is not incident
        ):
            raise ValueError("invalid_gate3_incident_continuity")

        observation_id = "gate3-observation-" + request.request_id
        investigation_id = "gate3-investigation-" + request.request_id
        evidence = TrustedSystemdEvidenceRecord(
            incident_id=incident.incident_id,
            component_id=COMPONENT,
            observation_id=observation_id,
            investigation_id=investigation_id,
            observed_at=now,
            snapshot=before,
        )
        evidence_store = TrustedSystemdEvidenceStore(self.root / "trusted_evidence")
        evidence_id = evidence_store.append(evidence)
        loaded_evidence = evidence_store.get(evidence_id)
        if loaded_evidence != evidence:
            raise ValueError("gate3_durable_evidence_roundtrip_failed")

        assessment = SystemdIncidentDispatchAssessment(
            candidate=True,
            incident_id=incident.incident_id,
            component_id=COMPONENT,
            unit=UNIT,
            action=ACTION_RESTART,
            reasons=("gate3_controlled_live_validation",),
            required_downstream_facts=(
                "trusted_fresh_evidence_to_bound_plan",
                "explicit_commander_production_target_rule",
                "canonical_commander_authorization",
            ),
            trusted_evidence_identities=(
                SystemdDispatchEvidenceIdentity.from_record(loaded_evidence),
            ),
        )

        suffix = request.request_id
        prepared = self.runtime.systemd_production_preparation.prepare(
            assessment=assessment,
            evidence=loaded_evidence,
            now=now,
            max_age_seconds=300.0,
            privilege=SystemdPrivilegeBoundary(systemctl_binary=ARGV[0]),
            run_id="gate3-run-" + suffix,
            execution_id="gate3-execution-" + suffix,
            permit_id="gate3-permit-" + suffix,
        )

        approval = TrustedSystemdProductionCommanderApproval(
            approval_id=request.approval_id,
            effect=prepared.plan.permit_binding,
            issued_at=now,
            expires_at=request.expires_at,
        )
        decision = CommanderIntentDecision(
            intent=CommanderIntent.NEED_COMMANDER,
            reason="Explicit Gate 3 Commander approval.",
        )
        continuation = build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=prepared.binding,
            prepared=prepared,
            approval=approval,
            now=now,
        )

        issuer = SystemdProductionCommanderApprovalIssuer(self.root / "issuance")
        grant = issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="gate3-activation-" + suffix,
            now=now,
        )
        consumption_store = SystemdProductionActivationConsumptionStore(
            self.root / "consumption"
        )
        consumption = consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=consumption_store,
            now=now,
        )
        activation_binding = (
            bind_systemd_production_commander_consumption_to_prepared_effect(
                continuation=continuation,
                grant=grant,
                consumption=consumption,
                now=now,
            )
        )
        authorization_context = (
            build_systemd_production_commander_authorization_context(
                continuation=continuation,
                binding=activation_binding,
                issuer=issuer,
                consumption_store=consumption_store,
            )
        )
        return continuation, activation_binding, authorization_context

    def _process(self, raw):
        started = self.clock()
        request = None
        incident = None
        continuation = None
        activation_binding = None
        authorization_context = None
        integration_result = None
        resolution = None
        before = None
        error = None

        try:
            request = Gate3LiveRequest.parse(raw, self.clock())
            if not self._activation_empty():
                raise ValueError("gate3_runtime_activation_not_empty")

            before = self.snapshot_provider()
            if type(before) is not SystemdUnitSnapshot:
                raise TypeError("gate3_snapshot_provider_must_return_snapshot")
            if (
                before.identity.component_id != COMPONENT
                or not before.identity.live_eligible
                or before.load_state != "loaded"
                or before.active_state != "active"
                or before.invocation_id != request.expected_pre_invocation_id
            ):
                raise ValueError("gate3_invalid_precondition")

            now = self.clock()
            request.validate_time(now)

            manager = self.runtime.incident_manager
            if manager.get_active_incident(COMPONENT) is not None:
                raise ValueError("gate3_probe_has_existing_active_incident")

            # Ownership is established in the caller before any downstream
            # Commander-path operation can fail. This guarantees the exception
            # handler can terminalize exactly the incident created by Gate 3.
            incident = manager.evaluate_anomaly(
                observation={
                    "pane_id": COMPONENT,
                    "agent_identity": "AIRIV_SYSTEM",
                    "source": "GATE3_CONTROLLED_LIVE_VALIDATION",
                },
                anomaly_type="GATE3_CONTROLLED_LIVE_VALIDATION",
                reason="One-shot Commander-approved generic systemd validation.",
            )
            manager.investigate(COMPONENT)

            (
                continuation,
                activation_binding,
                authorization_context,
            ) = self._build_commander_path(
                request,
                before,
                now,
                incident,
            )

            effect = continuation.prepared.plan.effect
            entry = RemediationActionEntry(
                action=effect.action,
                command=" ".join(effect.argv),
                rationale="Gate 3 one-shot generic production validation.",
            )
            lease = TemporaryLiveRemediationActivationLease(
                policy=self.runtime.policy,
                catalog=self.runtime.remediation_action_catalog,
                effect=effect,
                entry=entry,
            )

            with lease:
                self.runtime.policy.configure_systemd_production_target_policy(
                    SystemdProductionTargetPolicy(
                        [
                            SystemdProductionTargetRule(
                                UNIT,
                                ProductionTargetMode.COMMANDER_ONLY,
                                cooldown_seconds=3600.0,
                                retry_window_seconds=86400.0,
                                max_attempts_per_window=1,
                            )
                        ]
                    )
                )
                try:
                    activation_result = (
                        self.runtime.invoke_systemd_production_remediation(
                            activation_binding=activation_binding,
                            authorization_context=authorization_context,
                            incident_state="INVESTIGATING",
                            after_snapshot_provider=self.snapshot_provider,
                            production_now=now,
                            timeout=5.0,
                        )
                    )
                finally:
                    self.runtime.policy.clear_systemd_production_target_policy()

            runtime_result = activation_result.runtime_delegation_result
            if runtime_result is None or runtime_result.integration_result is None:
                raise ValueError("gate3_runtime_did_not_reach_integration")
            integration_result = runtime_result.integration_result
            resolution = resolve_systemd_production_commander_result(
                continuation=continuation,
                commander_authorization=authorization_context,
                integration_result=integration_result,
                incident_manager=self.runtime.incident_manager,
            )

            if (
                not activation_result.delegated
                or not runtime_result.delegated
                or not integration_result.authorization.authorized
                or not integration_result.execution_succeeded
                or not integration_result.verification_succeeded
                or not integration_result.recovered
                or resolution.final_outcome != "RECOVERED"
                or not self._activation_empty()
            ):
                raise ValueError("gate3_live_validation_incomplete")

            self.last_result = resolution

        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
            if incident is not None:
                active = self.runtime.incident_manager.get_active_incident(COMPONENT)
                if active is incident:
                    self.runtime.incident_manager.resolve(
                        component_id=COMPONENT,
                        recovery_evidence={
                            "source": "gate3_live_validation_failure",
                            "error": error,
                        },
                        observation={
                            "incident_id": incident.incident_id,
                            "component_id": COMPONENT,
                        },
                        final_outcome="UNRESOLVED",
                    )
        finally:
            # Target policy is never allowed to leak from this validation.
            self.runtime.policy.clear_systemd_production_target_policy()
            cleanup_empty = self._activation_empty()
            record = {
                "schema": "airiv-sentinel-gate3-live-evidence",
                "schema_version": 1,
                "process": process_identity(),
                "started_at": started,
                "finished_at": self.clock(),
                "request_id": request.request_id if request else None,
                "approval_id": request.approval_id if request else None,
                "component_id": COMPONENT,
                "unit": UNIT,
                "error": error,
                "cleanup_empty": cleanup_empty,
                "pre_invocation_id": (
                    before.invocation_id if before is not None else None
                ),
                "post_invocation_id": (
                    integration_result.after.invocation_id
                    if integration_result is not None
                    and integration_result.after is not None
                    else None
                ),
                "execution_id": (
                    continuation.execution_id if continuation is not None else None
                ),
                "activation_id": (
                    activation_binding.activation_id
                    if activation_binding is not None
                    else None
                ),
                "policy_authorized": (
                    integration_result.authorization.authorized
                    if integration_result is not None
                    else None
                ),
                "execution_succeeded": (
                    integration_result.execution_succeeded
                    if integration_result is not None
                    else None
                ),
                "verification_succeeded": (
                    integration_result.verification_succeeded
                    if integration_result is not None
                    else None
                ),
                "final_outcome": (
                    resolution.final_outcome if resolution is not None else None
                ),
            }
            record["terminal_outcome"] = (
                "TERMINAL_SUCCESS"
                if (
                    error is None
                    and cleanup_empty
                    and record["final_outcome"] == "RECOVERED"
                    and record["pre_invocation_id"]
                    and record["post_invocation_id"]
                    and record["pre_invocation_id"] != record["post_invocation_id"]
                )
                else "TERMINAL_FAILURE"
            )
            atomic_write(self.root, self.evidence_path.name, record)

        return self.last_result


def create_gate3_live_request(*, root=None, clock=time.time, snapshot_provider=None):
    """Create exactly one fresh private request; performs no remediation."""
    root = Path(root) if root is not None else default_root()
    request_path = root / "gate3-live-request.json"
    evidence_path = root / "gate3-live-evidence.json"

    if request_path.exists() or evidence_path.exists():
        raise ValueError("gate3_live_state_already_exists")
    if (root / "issuance").exists() or (root / "consumption").exists():
        raise ValueError("gate3_durable_state_already_exists")

    provider = snapshot_provider or (
        lambda: SystemdReadOnlyInspector().inspect(UNIT)
    )
    before = provider()
    if (
        type(before) is not SystemdUnitSnapshot
        or before.identity.component_id != COMPONENT
        or not before.identity.live_eligible
        or before.load_state != "loaded"
        or before.active_state != "active"
    ):
        raise ValueError("gate3_probe_not_ready")

    now = float(clock())
    request = Gate3LiveRequest(
        schema_version=1,
        request_id=uuid.uuid4().hex[:16],
        approval_id=APPROVAL_ID,
        created_at=now,
        expires_at=now + 120.0,
        component_id=COMPONENT,
        unit=UNIT,
        action=ACTION_RESTART,
        argv=ARGV,
        expected_pre_invocation_id=before.invocation_id,
    )
    payload = asdict(request)
    payload["argv"] = list(request.argv)
    atomic_write(root, request_path.name, payload)
    return request
