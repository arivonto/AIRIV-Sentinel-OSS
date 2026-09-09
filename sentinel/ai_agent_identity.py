"""Durable replay-safe AI agent execution identity for AIRIV Sentinel.

The ledger stores bounded execution metadata only. It never stores prompts,
raw agent output, credentials, system commands, or Incident state. Replays of an
incomplete execution are terminalized as UNKNOWN and are never auto-executed.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import tempfile
import time
from typing import Any

from sentinel.ai_agent_execution import (
    AgentExecutionBoundary,
    AgentExecutionOutcome,
    AgentExecutionStatus,
    AgentRequest,
)


class AgentExecutionIdentityState:
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


_TERMINAL_STATES = {
    AgentExecutionIdentityState.SUCCEEDED,
    AgentExecutionIdentityState.FAILED,
    AgentExecutionIdentityState.UNKNOWN,
}
_VALID_STATES = {
    AgentExecutionIdentityState.CLAIMED,
    AgentExecutionIdentityState.RUNNING,
    *_TERMINAL_STATES,
}


def fingerprint_agent_request(request: AgentRequest) -> str:
    """Return deterministic SHA-256 over the complete canonical request."""

    if not isinstance(request, AgentRequest):
        raise TypeError("request must be an AgentRequest")
    try:
        payload = json.dumps(
            request.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("AgentRequest must be deterministically JSON serializable") from exc
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentExecutionIdentityRecord:
    request_id: str
    state: str
    request_sha256: str
    agent_id: str
    task_id: str
    requested_operation: str
    created_at: float
    updated_at: float
    accepted: bool | None = None
    execution_status: str | None = None
    detail_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _VALID_STATES:
            raise ValueError("invalid AI execution identity state")
        if not isinstance(self.request_sha256, str) or len(self.request_sha256) != 64:
            raise ValueError("request_sha256 must be SHA-256 hex")
        try:
            int(self.request_sha256, 16)
        except ValueError as exc:
            raise ValueError("request_sha256 must be SHA-256 hex") from exc
        if self.accepted is not None and not isinstance(self.accepted, bool):
            raise TypeError("accepted must be boolean or null")
        if self.execution_status is not None and self.execution_status not in {
            AgentExecutionStatus.SUCCEEDED,
            AgentExecutionStatus.FAILED,
            AgentExecutionStatus.TIMED_OUT,
            AgentExecutionStatus.CANCELLED,
        }:
            raise ValueError("invalid AI execution status")


@dataclass(frozen=True, slots=True)
class AgentExecutionIdentityClaim:
    claimed: bool
    replayed: bool
    record: AgentExecutionIdentityRecord


@dataclass(frozen=True, slots=True)
class ReplaySafeAgentExecutionOutcome:
    replayed: bool
    executed: bool
    record: AgentExecutionIdentityRecord
    boundary_outcome: AgentExecutionOutcome | None


class AgentExecutionIdentityLedger:
    """Atomic durable request identity and replay boundary."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = os.environ.get("AIRIV_SENTINEL_AI_IDENTITY_DIR")
        self.root = Path(root if root is not None else configured or "var/ai_agent_identity")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _record_key(request_id: str) -> str:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id is required")
        return hashlib.sha256(request_id.encode("utf-8")).hexdigest()

    def _record_dir(self, request_id: str) -> Path:
        return self.root / self._record_key(request_id)

    def _record_path(self, request_id: str) -> Path:
        return self._record_dir(request_id) / "record.json"

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _write_atomic(cls, path: Path, record: AgentExecutionIdentityRecord) -> None:
        payload = json.dumps(asdict(record), sort_keys=True, separators=(",", ":"))
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
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

    @staticmethod
    def _load_path(path: Path) -> AgentExecutionIdentityRecord:
        try:
            with path.open("r", encoding="utf-8") as handle:
                data: Any = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("AI execution identity record is unreadable") from exc
        if not isinstance(data, dict):
            raise RuntimeError("AI execution identity record must be an object")
        try:
            return AgentExecutionIdentityRecord(**data)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("AI execution identity record is malformed") from exc

    @staticmethod
    def _assert_continuity(
        record: AgentExecutionIdentityRecord,
        request: AgentRequest,
        request_sha256: str,
    ) -> None:
        if (
            record.request_id != request.request_id
            or record.agent_id != request.agent_id
            or record.task_id != request.task_id
            or record.requested_operation != request.requested_operation
            or record.request_sha256 != request_sha256
        ):
            raise RuntimeError(
                "AI execution replay does not match original request identity"
            )

    def load(self, request_id: str) -> AgentExecutionIdentityRecord:
        path = self._record_path(request_id)
        if not path.is_file():
            raise FileNotFoundError("AI execution identity record does not exist")
        record = self._load_path(path)
        if record.request_id != request_id:
            raise RuntimeError("AI execution identity record request mismatch")
        return record

    def claim(self, request: AgentRequest) -> AgentExecutionIdentityClaim:
        request_sha256 = fingerprint_agent_request(request)
        record_dir = self._record_dir(request.request_id)
        record_path = record_dir / "record.json"
        now = time.time()
        initial = AgentExecutionIdentityRecord(
            request_id=request.request_id,
            state=AgentExecutionIdentityState.CLAIMED,
            request_sha256=request_sha256,
            agent_id=request.agent_id,
            task_id=request.task_id,
            requested_operation=request.requested_operation,
            created_at=now,
            updated_at=now,
        )

        try:
            record_dir.mkdir(mode=0o700)
        except FileExistsError:
            record = self._load_path(record_path)
            self._assert_continuity(record, request, request_sha256)
            if record.state in {
                AgentExecutionIdentityState.CLAIMED,
                AgentExecutionIdentityState.RUNNING,
            }:
                record = AgentExecutionIdentityRecord(
                    **{
                        **asdict(record),
                        "state": AgentExecutionIdentityState.UNKNOWN,
                        "updated_at": time.time(),
                        "detail_code": "REPLAY_AFTER_INCOMPLETE_ATTEMPT",
                    }
                )
                self._write_atomic(record_path, record)
            return AgentExecutionIdentityClaim(False, True, record)

        self._write_atomic(record_path, initial)
        self._fsync_directory(self.root)
        return AgentExecutionIdentityClaim(True, False, initial)

    def mark_running(self, request: AgentRequest) -> AgentExecutionIdentityRecord:
        record = self.load(request.request_id)
        self._assert_continuity(record, request, fingerprint_agent_request(request))
        if record.state != AgentExecutionIdentityState.CLAIMED:
            raise RuntimeError("AI execution identity is not CLAIMED")
        running = AgentExecutionIdentityRecord(
            **{
                **asdict(record),
                "state": AgentExecutionIdentityState.RUNNING,
                "updated_at": time.time(),
            }
        )
        self._write_atomic(self._record_path(request.request_id), running)
        return running

    def finalize(
        self,
        request: AgentRequest,
        outcome: AgentExecutionOutcome,
    ) -> AgentExecutionIdentityRecord:
        record = self.load(request.request_id)
        self._assert_continuity(record, request, fingerprint_agent_request(request))
        if record.state != AgentExecutionIdentityState.RUNNING:
            raise RuntimeError("AI execution identity is not RUNNING")

        execution_status = (
            outcome.raw_result.execution_status
            if outcome.raw_result is not None
            else None
        )
        if outcome.boundary_error_code and outcome.boundary_error_code.startswith(
            "adapter_exception:"
        ):
            state = AgentExecutionIdentityState.UNKNOWN
        elif outcome.accepted and execution_status == AgentExecutionStatus.SUCCEEDED:
            state = AgentExecutionIdentityState.SUCCEEDED
        else:
            state = AgentExecutionIdentityState.FAILED

        final = AgentExecutionIdentityRecord(
            **{
                **asdict(record),
                "state": state,
                "updated_at": time.time(),
                "accepted": outcome.accepted,
                "execution_status": execution_status,
                "detail_code": (
                    outcome.boundary_error_code
                    or outcome.verification.reason_code
                ),
            }
        )
        self._write_atomic(self._record_path(request.request_id), final)
        return final


class ReplaySafeAgentExecutionOrchestrator:
    """Compose durable identity around the canonical AI execution boundary."""

    def __init__(
        self,
        *,
        boundary: AgentExecutionBoundary,
        ledger: AgentExecutionIdentityLedger,
    ) -> None:
        if not isinstance(boundary, AgentExecutionBoundary):
            raise TypeError("boundary must be an AgentExecutionBoundary")
        if not isinstance(ledger, AgentExecutionIdentityLedger):
            raise TypeError("ledger must be an AgentExecutionIdentityLedger")
        self.boundary = boundary
        self.ledger = ledger

    def execute(self, request: AgentRequest) -> ReplaySafeAgentExecutionOutcome:
        claim = self.ledger.claim(request)
        if claim.replayed:
            return ReplaySafeAgentExecutionOutcome(
                replayed=True,
                executed=False,
                record=claim.record,
                boundary_outcome=None,
            )

        self.ledger.mark_running(request)
        outcome = self.boundary.execute(request)
        try:
            record = self.ledger.finalize(request, outcome)
        except RuntimeError:
            # A concurrent replay may conservatively terminalize an in-flight
            # identity as UNKNOWN. Never overwrite that uncertainty with success.
            record = self.ledger.load(request.request_id)
            if record.state != AgentExecutionIdentityState.UNKNOWN:
                raise
        return ReplaySafeAgentExecutionOutcome(
            replayed=False,
            executed=outcome.attempted,
            record=record,
            boundary_outcome=outcome,
        )
