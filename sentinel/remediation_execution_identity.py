"""AIRIV Sentinel durable remediation execution identity boundary."""

from __future__ import annotations

from sentinel.bound_effect_contract import (
    bound_effect_policy_run_id,
    bound_effect_target_fingerprint,
    validate_bound_effect_contract,
)


from dataclasses import asdict, dataclass
import errno
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from sentinel.execution import ExecutionBoundary, ExecutionResult
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationDecision,
)


class ExecutionIdentityState:
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


_TERMINAL_STATES = {
    ExecutionIdentityState.SUCCEEDED,
    ExecutionIdentityState.FAILED,
    ExecutionIdentityState.UNKNOWN,
}


@dataclass(frozen=True)
class ExecutionIdentityRecord:
    execution_id: str
    state: str
    incident_id: str
    component_id: str
    action: str
    command: str
    created_at: float
    updated_at: float
    execution: dict | None = None
    unknown_reason: str | None = None


@dataclass(frozen=True)
class IdentityClaim:
    claimed: bool
    replayed: bool
    record: ExecutionIdentityRecord


class RemediationExecutionIdentityJournal:
    """Durable filesystem journal for remediation execution identities."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = os.environ.get(
            "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR"
        )

        self.root = Path(
            root
            if root is not None
            else configured or "var/execution_identity"
        )

        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_execution_id(execution_id: str) -> str:
        if not execution_id or not execution_id.strip():
            raise ValueError("execution_id is required")

        execution_id = execution_id.strip()

        if execution_id in {".", ".."}:
            raise ValueError("invalid execution_id")

        if not re.fullmatch(r"[A-Za-z0-9._:-]+", execution_id):
            raise ValueError("execution_id contains invalid characters")

        return execution_id

    def _record_dir(self, execution_id: str) -> Path:
        execution_id = self._validate_execution_id(execution_id)
        return self.root / execution_id

    def _record_path(self, execution_id: str) -> Path:
        return self._record_dir(execution_id) / "record.json"

    @staticmethod
    def _load_path(path: Path) -> ExecutionIdentityRecord:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        return ExecutionIdentityRecord(**data)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _write_atomic(
        cls,
        path: Path,
        record: ExecutionIdentityRecord,
    ) -> None:
        payload = json.dumps(
            asdict(record),
            sort_keys=True,
            separators=(",", ":"),
        )

        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            text=True,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary, path)
            cls._fsync_directory(path.parent)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def claim(
        self,
        execution_id: str,
        incident_id: str,
        component_id: str,
        action: str,
        command: str,
    ) -> IdentityClaim:
        execution_id = self._validate_execution_id(execution_id)

        if not incident_id:
            raise ValueError("incident_id is required")

        if not component_id:
            raise ValueError("component_id is required")

        if not action or not action.strip():
            raise ValueError("action must not be empty")

        if not command or not command.strip():
            raise ValueError("command must not be empty")

        record_dir = self._record_dir(execution_id)
        record_path = record_dir / "record.json"
        now = time.time()

        record = ExecutionIdentityRecord(
            execution_id=execution_id,
            state=ExecutionIdentityState.CLAIMED,
            incident_id=incident_id,
            component_id=component_id,
            action=action,
            command=command,
            created_at=now,
            updated_at=now,
        )

        # Build the complete durable identity in a private temporary
        # directory first. The identity becomes visible only when the
        # complete record exists and has been fsynced.
        temporary_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{execution_id}.",
                dir=self.root,
            )
        )

        temporary_record = temporary_dir / "record.json"

        try:
            self._write_atomic(temporary_record, record)
            self._fsync_directory(temporary_dir)

            try:
                os.rename(temporary_dir, record_dir)
            except OSError as exc:
                # Concurrent publication of the same execution identity
                # may surface as EEXIST or ENOTEMPTY depending on the
                # filesystem/kernel behavior.
                #
                # Both mean another caller has already published the
                # canonical identity directory.
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise

                # Another caller won the atomic publication race.
                # The winning identity must be observed as a durable
                # record before replay is returned.
                deadline = time.monotonic() + 30.0

                while True:
                    try:
                        existing = self._load_path(record_path)
                    except FileNotFoundError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "execution identity exists but its durable "
                                "record was not published"
                            )

                        time.sleep(0.001)
                        continue

                    except (
                        OSError,
                        ValueError,
                        TypeError,
                        json.JSONDecodeError,
                    ) as exc:
                        raise RuntimeError(
                            "execution identity exists but its durable "
                            "record cannot be read"
                        ) from exc

                    if existing.state in _TERMINAL_STATES:
                        # This caller lost the atomic publication race.
                        # The temporary directory belongs exclusively to
                        # this caller and must be removed before returning
                        # the deterministic replay result.
                        shutil.rmtree(
                            temporary_dir,
                            ignore_errors=False,
                        )

                        return IdentityClaim(
                            claimed=False,
                            replayed=True,
                            record=existing,
                        )

                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "execution identity did not reach a terminal "
                            "state while waiting for replay"
                        )

                    time.sleep(0.001)

                # Unreachable: all successful paths return above.
                raise RuntimeError(
                    "execution identity replay resolution failed"
                )

            self._fsync_directory(self.root)

        except BaseException:
            if temporary_dir.exists():
                shutil.rmtree(
                    temporary_dir,
                    ignore_errors=True,
                )

            raise

        return IdentityClaim(
            claimed=True,
            replayed=False,
            record=record,
        )

    def transition(
        self,
        execution_id: str,
        state: str,
        execution: dict | None = None,
        unknown_reason: str | None = None,
    ) -> ExecutionIdentityRecord:
        if state not in {
            ExecutionIdentityState.CLAIMED,
            ExecutionIdentityState.RUNNING,
            ExecutionIdentityState.SUCCEEDED,
            ExecutionIdentityState.FAILED,
            ExecutionIdentityState.UNKNOWN,
        }:
            raise ValueError(f"invalid execution identity state: {state}")

        path = self._record_path(execution_id)
        current = self._load_path(path)

        if current.state in _TERMINAL_STATES:
            if current.state != state:
                raise RuntimeError(
                    "terminal execution identity cannot transition"
                )
            return current

        if state == ExecutionIdentityState.CLAIMED:
            raise RuntimeError(
                "execution identity cannot transition back to CLAIMED"
            )

        updated = ExecutionIdentityRecord(
            execution_id=current.execution_id,
            state=state,
            incident_id=current.incident_id,
            component_id=current.component_id,
            action=current.action,
            command=current.command,
            created_at=current.created_at,
            updated_at=time.time(),
            execution=(
                execution
                if execution is not None
                else current.execution
            ),
            unknown_reason=unknown_reason,
        )

        self._write_atomic(path, updated)
        return updated

    def get(
        self,
        execution_id: str,
    ) -> ExecutionIdentityRecord | None:
        record_dir = self._record_dir(execution_id)

        if not record_dir.exists():
            return None

        return self._load_path(record_dir / "record.json")

    def recover_interrupted(self) -> list[ExecutionIdentityRecord]:
        recovered: list[ExecutionIdentityRecord] = []

        for record_dir in sorted(self.root.iterdir()):
            if not record_dir.is_dir():
                continue

            path = record_dir / "record.json"

            try:
                current = self._load_path(path)
            except (
                OSError,
                ValueError,
                TypeError,
                json.JSONDecodeError,
            ):
                continue

            if current.state not in {
                ExecutionIdentityState.CLAIMED,
                ExecutionIdentityState.RUNNING,
            }:
                continue

            recovered.append(
                self.transition(
                    current.execution_id,
                    ExecutionIdentityState.UNKNOWN,
                    unknown_reason=(
                        "Sentinel restarted while remediation execution "
                        "outcome was indeterminate."
                    ),
                )
            )

        return recovered

    # PHASE_213C1B_ONE_RUN_PERMIT
    def claim_live_run_permit(
        self,
        *,
        effect,
        authorization,
    ):
        """Atomically claim one external-effect permit per run_id.

        This extends the existing execution-identity journal. It is not
        a separate deduplication authority.

        Exact replay returns replayed=True. Any changed execution ID,
        target, incident, action, permit, effect, or authorization under
        the same run_id fails closed.
        """

        import hashlib
        import json
        import os
        from pathlib import Path

        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
            BoundRemediationEffect,
            LiveRunPermitClaim,
            LiveRunPermitRecord,
        )

        validate_bound_effect_contract(
            effect
        )

        if not isinstance(
            authorization,
            BoundRemediationAuthorization,
        ):
            raise TypeError(
                "authorization must be a "
                "BoundRemediationAuthorization"
            )

        if not authorization.authorized:
            raise PermissionError(
                "bound remediation authorization is DENY"
            )

        if not authorization.matches(effect):
            raise PermissionError(
                "authorization_effect_binding_mismatch"
            )

        if not effect.target.live_eligible:
            raise PermissionError(
                "target_identity_not_live_eligible"
            )

        root = Path(getattr(self, 'root'))

        permit_root = root / "_live_run_permits"
        permit_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        run_key = hashlib.sha256(
            bound_effect_policy_run_id(effect).encode("utf-8")
        ).hexdigest()

        permit_path = permit_root / f"{run_key}.json"

        expected = LiveRunPermitRecord(
            run_id=bound_effect_policy_run_id(effect),
            permit_id=effect.permit_id,
            execution_id=effect.execution_id,
            incident_id=effect.incident_id,
            component_id=effect.component_id,
            action=effect.action,
            target_fingerprint=bound_effect_target_fingerprint(effect),
            effect_fingerprint=effect.fingerprint,
            authorization_fingerprint=authorization.fingerprint,
        )

        payload = expected.canonical_dict()

        encoded = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        # PHASE_213C1B_RACE_SAFE_PUBLICATION
        #
        # Never create the canonical permit path before its JSON is
        # complete. Otherwise a concurrent loser can observe the empty
        # O_EXCL-created file before the winner has written its record.
        #
        # Publish protocol:
        #   1. write/fsync a unique temp file in the same directory
        #   2. atomically hard-link it to the canonical run path
        #   3. fsync the containing directory
        #   4. remove the private temp name
        #
        # os.link() is the atomic one-winner claim. A losing claimant
        # only ever sees a fully written canonical record.

        import uuid

        temp_path = (
            permit_root
            / f".{run_key}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )

        fd = os.open(
            temp_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL,
            0o600,
        )

        try:
            with os.fdopen(
                fd,
                "wb",
                closefd=True,
            ) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                os.link(
                    temp_path,
                    permit_path,
                )

            except FileExistsError:
                existing_payload = json.loads(
                    permit_path.read_text(
                        encoding="utf-8"
                    )
                )

                existing = LiveRunPermitRecord(
                    **existing_payload
                )

                if existing != expected:
                    raise RuntimeError(
                        "live_run_permit_conflict"
                    )

                return LiveRunPermitClaim(
                    record=existing,
                    replayed=True,
                )

            # Persist the directory entry after the complete record
            # has been atomically published.
            directory_fd = os.open(
                permit_root,
                os.O_RDONLY,
            )

            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

            return LiveRunPermitClaim(
                record=expected,
                replayed=False,
            )

        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def get_live_run_permit(
        self,
        run_id: str,
    ):
        """Read a previously claimed live-run permit."""

        import hashlib
        import json
        from pathlib import Path

        from sentinel.live_remediation_safety import (
            LiveRunPermitRecord,
        )

        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id is required")

        root = Path(getattr(self, 'root'))

        run_key = hashlib.sha256(
            run_id.strip().encode("utf-8")
        ).hexdigest()

        path = (
            root
            / "_live_run_permits"
            / f"{run_key}.json"
        )

        if not path.exists():
            return None

        return LiveRunPermitRecord(
            **json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        )


class RemediationExecutionIdentityBoundary:
    """Durable identity gate around the canonical remediation gate."""

    def __init__(
        self,
        journal: RemediationExecutionIdentityJournal,
        gate: RemediationExecutionGate,
    ) -> None:
        if not isinstance(journal, RemediationExecutionIdentityJournal):
            raise TypeError(
                "journal must be a RemediationExecutionIdentityJournal"
            )

        if not isinstance(gate, RemediationExecutionGate):
            raise TypeError(
                "gate must be a RemediationExecutionGate"
            )

        self.journal = journal
        self.gate = gate

    @staticmethod
    def _execution_from_record(
        record: ExecutionIdentityRecord,
    ) -> ExecutionResult | None:
        if record.execution is None:
            return None

        data = record.execution

        return ExecutionResult(
            command=data["command"],
            stdout=data["stdout"],
            stderr=data["stderr"],
            exit_code=data["exit_code"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
        )

    def execute(
        self,
        execution_id: str,
        incident_id: str,
        component_id: str,
        action: str,
        command: str,
        decision: RemediationDecision,
    ) -> tuple[
        ExecutionResult | None,
        ExecutionIdentityRecord,
        bool,
    ]:
        if decision.decision is not PolicyDecision.ALLOW:
            raise ValueError(
                "identity boundary requires an authorized remediation"
            )

        claim = self.journal.claim(
            execution_id=execution_id,
            incident_id=incident_id,
            component_id=component_id,
            action=action,
            command=command,
        )

        if claim.replayed:
            return (
                self._execution_from_record(claim.record),
                claim.record,
                True,
            )

        self.journal.transition(
            execution_id,
            ExecutionIdentityState.RUNNING,
        )

        try:
            gate_result = self.gate.execute(
                decision,
                command,
            )

            result = gate_result.execution

            if result is None:
                self.journal.transition(
                    execution_id,
                    ExecutionIdentityState.UNKNOWN,
                    unknown_reason=(
                        "Remediation gate returned no execution result."
                    ),
                )
                record = self.journal.get(execution_id)
                if record is None:
                    raise RuntimeError(
                        "execution identity record disappeared"
                    )
                return None, record, False

            execution = {
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "success": result.success,
            }

            state = (
                ExecutionIdentityState.SUCCEEDED
                if result.success
                else ExecutionIdentityState.FAILED
            )

            record = self.journal.transition(
                execution_id,
                state,
                execution=execution,
            )

            return result, record, False

        except BaseException as exc:
            self.journal.transition(
                execution_id,
                ExecutionIdentityState.UNKNOWN,
                unknown_reason=(
                    "Execution raised an exception before a reliable "
                    "terminal outcome was recorded: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            raise

    # PHASE_213C1B2_BOUND_IDENTITY_EXECUTION
    @staticmethod
    def _bound_command(effect) -> str:
        import json

        return json.dumps(
            list(effect.argv),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _validate_bound_record(
        record,
        *,
        effect,
        command: str,
    ) -> None:
        if record.execution_id != effect.execution_id:
            raise RuntimeError(
                "bound_execution_identity_mismatch"
            )

        if record.incident_id != effect.incident_id:
            raise RuntimeError(
                "bound_incident_identity_mismatch"
            )

        if record.component_id != effect.component_id:
            raise RuntimeError(
                "bound_component_identity_mismatch"
            )

        if record.action != effect.action:
            raise RuntimeError(
                "bound_action_identity_mismatch"
            )

        if record.command != command:
            raise RuntimeError(
                "bound_effect_command_mismatch"
            )

    def execute_bound(
        self,
        *,
        effect,
        authorization,
        decision,
        timeout: float = 5.0,
    ):
        """Execute a live-bound effect only after durable permit claim."""

        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
            BoundRemediationEffect,
        )
        from sentinel.remediation_policy import PolicyDecision

        validate_bound_effect_contract(
            effect
        )

        if not isinstance(
            authorization,
            BoundRemediationAuthorization,
        ):
            raise TypeError(
                "authorization must be a "
                "BoundRemediationAuthorization"
            )

        if not authorization.authorized:
            raise PermissionError(
                "bound remediation authorization is DENY"
            )

        if not authorization.matches(effect):
            raise PermissionError(
                "authorization_effect_binding_mismatch"
            )

        if decision.decision is not PolicyDecision.ALLOW:
            raise PermissionError(
                "identity boundary requires ALLOW"
            )

        if decision.component_id != effect.component_id:
            raise PermissionError(
                "decision_component_binding_mismatch"
            )

        if decision.action != effect.action:
            raise PermissionError(
                "decision_action_binding_mismatch"
            )

        command = self._bound_command(effect)

        # ----------------------------------------------------
        # Durable one-run permit MUST precede any execution
        # identity claim or external effect.
        # ----------------------------------------------------

        permit_claim = self.journal.claim_live_run_permit(
            effect=effect,
            authorization=authorization,
        )

        if permit_claim.replayed:
            existing = self.journal.get(
                effect.execution_id
            )

            # A prior durable permit with no execution identity means
            # Sentinel cannot know whether an effect occurred before a
            # crash. Fail closed and NEVER blindly re-execute.
            if existing is None:
                raise RuntimeError(
                    "live_run_permit_replay_without_"
                    "execution_identity"
                )

            self._validate_bound_record(
                existing,
                effect=effect,
                command=command,
            )

            return (
                self._execution_from_record(existing),
                existing,
                True,
            )

        # ----------------------------------------------------
        # Existing canonical execution identity journal.
        # No second execution journal is introduced.
        # ----------------------------------------------------

        claim = self.journal.claim(
            execution_id=effect.execution_id,
            incident_id=effect.incident_id,
            component_id=effect.component_id,
            action=effect.action,
            command=command,
        )

        self._validate_bound_record(
            claim.record,
            effect=effect,
            command=command,
        )

        if claim.replayed:
            return (
                self._execution_from_record(claim.record),
                claim.record,
                True,
            )

        self.journal.transition(
            effect.execution_id,
            ExecutionIdentityState.RUNNING,
        )

        try:
            gate_result = self.gate.execute_bound(
                decision=decision,
                effect=effect,
                authorization=authorization,
                timeout=timeout,
            )

            result = gate_result.execution

            if result is None:
                self.journal.transition(
                    effect.execution_id,
                    ExecutionIdentityState.UNKNOWN,
                    unknown_reason=(
                        "Bound remediation gate returned no "
                        "execution result."
                    ),
                )

                record = self.journal.get(
                    effect.execution_id
                )

                if record is None:
                    raise RuntimeError(
                        "execution identity record disappeared"
                    )

                return None, record, False

            if result.command != command:
                self.journal.transition(
                    effect.execution_id,
                    ExecutionIdentityState.UNKNOWN,
                    unknown_reason=(
                        "Bound executor result did not preserve "
                        "the authorized argv binding."
                    ),
                )

                raise RuntimeError(
                    "bound_executor_result_mismatch"
                )

            execution = {
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "success": result.success,
            }

            state = (
                ExecutionIdentityState.SUCCEEDED
                if result.success
                else ExecutionIdentityState.FAILED
            )

            record = self.journal.transition(
                effect.execution_id,
                state,
                execution=execution,
            )

            return result, record, False

        except BaseException as exc:
            current = self.journal.get(
                effect.execution_id
            )

            if (
                current is not None
                and current.state
                not in {
                    ExecutionIdentityState.SUCCEEDED,
                    ExecutionIdentityState.FAILED,
                    ExecutionIdentityState.UNKNOWN,
                }
            ):
                self.journal.transition(
                    effect.execution_id,
                    ExecutionIdentityState.UNKNOWN,
                    unknown_reason=(
                        "Bound execution raised before a reliable "
                        "terminal outcome was recorded: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )

            raise
