"""Provider-neutral AI agent execution boundary for AIRIV Sentinel.

AI agents are replaceable execution resources. This module deliberately owns no
Incident lifecycle, remediation policy, system command execution, contract
mutation, or Commander authority. Raw agent output remains untrusted until an
independent verifier accepts it.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Protocol


class AgentExecutionStatus:
    """V1 observable terminal status returned by an AI execution resource."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


_AGENT_EXECUTION_STATUSES = frozenset(
    {
        AgentExecutionStatus.SUCCEEDED,
        AgentExecutionStatus.FAILED,
        AgentExecutionStatus.TIMED_OUT,
        AgentExecutionStatus.CANCELLED,
    }
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)


def _validate_identity_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > 256:
        raise ValueError(f"{field} is too long")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} contains control characters")
    return normalized


def _validate_context(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return _freeze(dict(value))


def _parse_aware_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class AgentRequest:
    """Immutable canonical request identity supplied to an AI execution resource."""

    request_id: str
    agent_id: str
    task_id: str
    input_payload: Any
    requested_operation: str
    execution_context: Mapping[str, Any]
    authority_context: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identity_text(self.request_id, "request_id"),
        )
        object.__setattr__(
            self,
            "agent_id",
            _validate_identity_text(self.agent_id, "agent_id"),
        )
        object.__setattr__(
            self,
            "task_id",
            _validate_identity_text(self.task_id, "task_id"),
        )
        object.__setattr__(
            self,
            "requested_operation",
            _validate_identity_text(
                self.requested_operation,
                "requested_operation",
            ),
        )
        object.__setattr__(self, "input_payload", _freeze(self.input_payload))
        object.__setattr__(
            self,
            "execution_context",
            _validate_context(self.execution_context, "execution_context"),
        )
        object.__setattr__(
            self,
            "authority_context",
            _validate_context(self.authority_context, "authority_context"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "input_payload": _thaw(self.input_payload),
            "requested_operation": self.requested_operation,
            "execution_context": _thaw(self.execution_context),
            "authority_context": _thaw(self.authority_context),
        }


@dataclass(frozen=True, slots=True)
class RawAgentResult:
    """Observable but untrusted result returned by an AI execution resource."""

    request_id: str
    agent_id: str
    task_id: str
    started_at: str
    completed_at: str
    output: Any
    execution_status: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identity_text(self.request_id, "request_id"),
        )
        object.__setattr__(
            self,
            "agent_id",
            _validate_identity_text(self.agent_id, "agent_id"),
        )
        object.__setattr__(
            self,
            "task_id",
            _validate_identity_text(self.task_id, "task_id"),
        )
        started = _parse_aware_timestamp(self.started_at, "started_at")
        completed = _parse_aware_timestamp(self.completed_at, "completed_at")
        if completed < started:
            raise ValueError("completed_at must not precede started_at")
        if self.execution_status not in _AGENT_EXECUTION_STATUSES:
            raise ValueError(
                f"unsupported agent execution status: {self.execution_status}"
            )
        object.__setattr__(self, "output", _freeze(self.output))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": _thaw(self.output),
            "execution_status": self.execution_status,
        }


@dataclass(frozen=True, slots=True)
class AgentVerificationDecision:
    """Independent Sentinel acceptance/rejection of one raw agent result."""

    accepted: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be boolean")
        object.__setattr__(
            self,
            "reason_code",
            _validate_identity_text(self.reason_code, "reason_code"),
        )


class AgentExecutionAdapter(Protocol):
    """Replaceable AI execution resource. It owns no Sentinel authority."""

    name: str
    enabled: bool

    def execute(self, request: AgentRequest) -> RawAgentResult:
        ...


class AgentResultVerifier(Protocol):
    """Independent result verification boundary."""

    def verify(
        self,
        request: AgentRequest,
        result: RawAgentResult,
    ) -> AgentVerificationDecision:
        ...


class DisabledAgentExecutionAdapter:
    """Production-safe default: no provider, no network, no execution."""

    name = "DISABLED"
    enabled = False

    def execute(self, request: AgentRequest) -> RawAgentResult:
        raise RuntimeError("disabled AI agent adapter cannot execute")


class DenyAllAgentResultVerifier:
    """Fail-closed default verifier: agent self-report is never proof."""

    def verify(
        self,
        request: AgentRequest,
        result: RawAgentResult,
    ) -> AgentVerificationDecision:
        return AgentVerificationDecision(
            accepted=False,
            reason_code="NO_INDEPENDENT_VERIFIER",
        )


@dataclass(frozen=True, slots=True)
class AgentExecutionEvidence:
    """Immutable append-oriented evidence for one attempted AI execution."""

    sequence: int
    request_id: str
    agent_id: str
    task_id: str
    adapter_name: str
    attempted: bool
    result_returned: bool
    execution_status: str | None
    result_snapshot: Mapping[str, Any] | None
    verification_accepted: bool
    verification_reason_code: str
    boundary_error_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        for field_name in ("request_id", "agent_id", "task_id", "adapter_name"):
            object.__setattr__(
                self,
                field_name,
                _validate_identity_text(getattr(self, field_name), field_name),
            )
        if not isinstance(self.attempted, bool):
            raise TypeError("attempted must be boolean")
        if not isinstance(self.result_returned, bool):
            raise TypeError("result_returned must be boolean")
        if self.execution_status is not None:
            if self.execution_status not in _AGENT_EXECUTION_STATUSES:
                raise ValueError("evidence execution_status is invalid")
        if self.result_snapshot is not None:
            if not isinstance(self.result_snapshot, Mapping):
                raise TypeError("result_snapshot must be a mapping")
            object.__setattr__(
                self,
                "result_snapshot",
                _freeze(dict(self.result_snapshot)),
            )
        if not isinstance(self.verification_accepted, bool):
            raise TypeError("verification_accepted must be boolean")
        object.__setattr__(
            self,
            "verification_reason_code",
            _validate_identity_text(
                self.verification_reason_code,
                "verification_reason_code",
            ),
        )
        if self.boundary_error_code is not None:
            object.__setattr__(
                self,
                "boundary_error_code",
                _validate_identity_text(
                    self.boundary_error_code,
                    "boundary_error_code",
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "adapter_name": self.adapter_name,
            "attempted": self.attempted,
            "result_returned": self.result_returned,
            "execution_status": self.execution_status,
            "result_snapshot": (
                _thaw(self.result_snapshot)
                if self.result_snapshot is not None
                else None
            ),
            "verification_accepted": self.verification_accepted,
            "verification_reason_code": self.verification_reason_code,
            "boundary_error_code": self.boundary_error_code,
        }


class AgentExecutionEvidenceTrail:
    """Append-only in-memory V1 evidence surface with no rewrite/delete API."""

    def __init__(self) -> None:
        self._records: list[AgentExecutionEvidence] = []

    @property
    def records(self) -> tuple[AgentExecutionEvidence, ...]:
        return tuple(self._records)

    def append(
        self,
        *,
        request: AgentRequest,
        adapter_name: str,
        attempted: bool,
        result: RawAgentResult | None,
        verification: AgentVerificationDecision,
        boundary_error_code: str | None = None,
    ) -> AgentExecutionEvidence:
        record = AgentExecutionEvidence(
            sequence=len(self._records) + 1,
            request_id=request.request_id,
            agent_id=request.agent_id,
            task_id=request.task_id,
            adapter_name=adapter_name,
            attempted=attempted,
            result_returned=result is not None,
            execution_status=(
                result.execution_status if result is not None else None
            ),
            result_snapshot=(result.to_dict() if result is not None else None),
            verification_accepted=verification.accepted,
            verification_reason_code=verification.reason_code,
            boundary_error_code=boundary_error_code,
        )
        self._records.append(record)
        return record


@dataclass(frozen=True, slots=True)
class AgentExecutionOutcome:
    """Observable boundary result. Acceptance is independent of agent success."""

    request_id: str
    agent_id: str
    task_id: str
    adapter_name: str
    attempted: bool
    accepted: bool
    raw_result: RawAgentResult | None
    verification: AgentVerificationDecision
    evidence: AgentExecutionEvidence | None
    boundary_error_code: str | None = None


class AgentExecutionBoundary:
    """Canonical provider-neutral AI execution boundary.

    The boundary only invokes an explicitly composed AI resource, validates
    identity continuity, calls an independent verifier, and appends evidence.
    It cannot authorize remediation or mutate canonical Sentinel lifecycle.
    """

    def __init__(
        self,
        *,
        adapter: AgentExecutionAdapter | None = None,
        verifier: AgentResultVerifier | None = None,
        evidence_trail: AgentExecutionEvidenceTrail | None = None,
    ) -> None:
        self.adapter = adapter or DisabledAgentExecutionAdapter()
        self.verifier = verifier or DenyAllAgentResultVerifier()
        self.evidence_trail = evidence_trail or AgentExecutionEvidenceTrail()

    @staticmethod
    def _validate_result_identity(
        request: AgentRequest,
        result: RawAgentResult,
    ) -> str | None:
        if result.request_id != request.request_id:
            return "RESULT_REQUEST_ID_MISMATCH"
        if result.agent_id != request.agent_id:
            return "RESULT_AGENT_ID_MISMATCH"
        if result.task_id != request.task_id:
            return "RESULT_TASK_ID_MISMATCH"
        return None

    def execute(self, request: AgentRequest) -> AgentExecutionOutcome:
        if not isinstance(request, AgentRequest):
            raise TypeError("request must be an AgentRequest")

        adapter_name = _validate_identity_text(self.adapter.name, "adapter_name")
        if self.adapter.enabled is not True:
            verification = AgentVerificationDecision(
                accepted=False,
                reason_code="ADAPTER_DISABLED",
            )
            return AgentExecutionOutcome(
                request_id=request.request_id,
                agent_id=request.agent_id,
                task_id=request.task_id,
                adapter_name=adapter_name,
                attempted=False,
                accepted=False,
                raw_result=None,
                verification=verification,
                evidence=None,
                boundary_error_code="ADAPTER_DISABLED",
            )

        try:
            result = self.adapter.execute(request)
        except Exception as exc:
            verification = AgentVerificationDecision(
                accepted=False,
                reason_code="ADAPTER_EXCEPTION",
            )
            error_code = f"adapter_exception:{type(exc).__name__}"
            evidence = self.evidence_trail.append(
                request=request,
                adapter_name=adapter_name,
                attempted=True,
                result=None,
                verification=verification,
                boundary_error_code=error_code,
            )
            return AgentExecutionOutcome(
                request_id=request.request_id,
                agent_id=request.agent_id,
                task_id=request.task_id,
                adapter_name=adapter_name,
                attempted=True,
                accepted=False,
                raw_result=None,
                verification=verification,
                evidence=evidence,
                boundary_error_code=error_code,
            )

        if not isinstance(result, RawAgentResult):
            verification = AgentVerificationDecision(
                accepted=False,
                reason_code="INVALID_RAW_RESULT_TYPE",
            )
            evidence = self.evidence_trail.append(
                request=request,
                adapter_name=adapter_name,
                attempted=True,
                result=None,
                verification=verification,
                boundary_error_code="INVALID_RAW_RESULT_TYPE",
            )
            return AgentExecutionOutcome(
                request_id=request.request_id,
                agent_id=request.agent_id,
                task_id=request.task_id,
                adapter_name=adapter_name,
                attempted=True,
                accepted=False,
                raw_result=None,
                verification=verification,
                evidence=evidence,
                boundary_error_code="INVALID_RAW_RESULT_TYPE",
            )

        identity_error = self._validate_result_identity(request, result)
        if identity_error is not None:
            verification = AgentVerificationDecision(
                accepted=False,
                reason_code=identity_error,
            )
            evidence = self.evidence_trail.append(
                request=request,
                adapter_name=adapter_name,
                attempted=True,
                result=result,
                verification=verification,
                boundary_error_code=identity_error,
            )
            return AgentExecutionOutcome(
                request_id=request.request_id,
                agent_id=request.agent_id,
                task_id=request.task_id,
                adapter_name=adapter_name,
                attempted=True,
                accepted=False,
                raw_result=result,
                verification=verification,
                evidence=evidence,
                boundary_error_code=identity_error,
            )

        if result.execution_status != AgentExecutionStatus.SUCCEEDED:
            verification = AgentVerificationDecision(
                accepted=False,
                reason_code=f"AGENT_{result.execution_status}",
            )
            evidence = self.evidence_trail.append(
                request=request,
                adapter_name=adapter_name,
                attempted=True,
                result=result,
                verification=verification,
            )
            return AgentExecutionOutcome(
                request_id=request.request_id,
                agent_id=request.agent_id,
                task_id=request.task_id,
                adapter_name=adapter_name,
                attempted=True,
                accepted=False,
                raw_result=result,
                verification=verification,
                evidence=evidence,
            )

        try:
            verification = self.verifier.verify(request, result)
            if not isinstance(verification, AgentVerificationDecision):
                raise TypeError(
                    "verifier must return AgentVerificationDecision"
                )
        except Exception as exc:
            verification = AgentVerificationDecision(
                accepted=False,
                reason_code="VERIFIER_EXCEPTION",
            )
            error_code = f"verifier_exception:{type(exc).__name__}"
            evidence = self.evidence_trail.append(
                request=request,
                adapter_name=adapter_name,
                attempted=True,
                result=result,
                verification=verification,
                boundary_error_code=error_code,
            )
            return AgentExecutionOutcome(
                request_id=request.request_id,
                agent_id=request.agent_id,
                task_id=request.task_id,
                adapter_name=adapter_name,
                attempted=True,
                accepted=False,
                raw_result=result,
                verification=verification,
                evidence=evidence,
                boundary_error_code=error_code,
            )

        evidence = self.evidence_trail.append(
            request=request,
            adapter_name=adapter_name,
            attempted=True,
            result=result,
            verification=verification,
        )
        return AgentExecutionOutcome(
            request_id=request.request_id,
            agent_id=request.agent_id,
            task_id=request.task_id,
            adapter_name=adapter_name,
            attempted=True,
            accepted=verification.accepted,
            raw_result=result,
            verification=verification,
            evidence=evidence,
        )
