"""Deterministic incident/workflow lifecycle projection for Sentinel S1.

This module intentionally does not replace or mutate the canonical Incident
lifecycle owned by IncidentManager. It tracks Lane-4 orchestration state bound
to one canonical incident identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


class IncidentWorkflowState(str, Enum):
    OPEN = "OPEN"
    REMEDIATING = "REMEDIATING"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"


class LifecycleFailureReason(str, Enum):
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    REMEDIATION_INELIGIBLE = "REMEDIATION_INELIGIBLE"
    REMEDIATION_FAILED = "REMEDIATION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class LifecycleEventKind(str, Enum):
    DIAGNOSTICS_RECORDED = "DIAGNOSTICS_RECORDED"
    AUTHORIZATION_RECORDED = "AUTHORIZATION_RECORDED"
    REMEDIATION_ELIGIBILITY_RECORDED = "REMEDIATION_ELIGIBILITY_RECORDED"
    REMEDIATION_STARTED = "REMEDIATION_STARTED"
    REMEDIATION_RESULT_RECORDED = "REMEDIATION_RESULT_RECORDED"
    VERIFICATION_RECORDED = "VERIFICATION_RECORDED"
    TIMEOUT_RECORDED = "TIMEOUT_RECORDED"
    CANCELLATION_RECORDED = "CANCELLATION_RECORDED"
    RETRY_EXHAUSTED_RECORDED = "RETRY_EXHAUSTED_RECORDED"


class LifecycleInvariantError(RuntimeError):
    """Raised when an event would violate lifecycle invariants."""


class DuplicateEventConflict(LifecycleInvariantError):
    """Raised when one event_id is reused for different content."""


class DuplicateExecutionConflict(LifecycleInvariantError):
    """Raised when one execution_id gets contradictory outcomes."""


@dataclass(frozen=True)
class LifecycleEvent:
    event_id: str
    kind: LifecycleEventKind
    fingerprint: str
    state_before: IncidentWorkflowState
    state_after: IncidentWorkflowState


@dataclass(frozen=True)
class IncidentWorkflowSnapshot:
    workflow_id: str
    incident_id: str
    component_id: str
    state: IncidentWorkflowState
    failure_reason: LifecycleFailureReason | None
    failure_detail: str | None
    diagnostics_recorded: bool
    authorization_decision: str | None
    remediation_eligible: bool | None
    execution_id: str | None
    remediation_succeeded: bool | None
    verification_passed: bool | None
    version: int
    event_count: int


@dataclass(frozen=True)
class _RestoredAuthorizationDecision:
    decision: str
    component_id: str | None


@dataclass(frozen=True)
class _RestoredVerification:
    verified: bool
    reason: str | None


class IncidentWorkflowLifecycle:
    """Deterministic Lane-4 orchestration lifecycle.

    Exact event replays are idempotent. Reuse of an event identity with
    changed semantic content is rejected. RECOVERED and FAILED are terminal
    and cannot be overwritten by later success-looking or failure-looking
    events.
    """

    SNAPSHOT_VERSION = 1

    TERMINAL_STATES = {
        IncidentWorkflowState.RECOVERED,
        IncidentWorkflowState.FAILED,
    }

    def __init__(
        self,
        *,
        workflow_id: str,
        incident_id: str,
        component_id: str,
    ) -> None:
        for name, value in (
            ("workflow_id", workflow_id),
            ("incident_id", incident_id),
            ("component_id", component_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")

        self.workflow_id = workflow_id
        self.incident_id = incident_id
        self.component_id = component_id

        self.state = IncidentWorkflowState.OPEN
        self.failure_reason: LifecycleFailureReason | None = None
        self.failure_detail: str | None = None

        self.diagnostics_recorded = False
        self.authorization_decision: str | None = None
        self.remediation_eligible: bool | None = None
        self.execution_id: str | None = None
        self.remediation_succeeded: bool | None = None
        self.verification_passed: bool | None = None

        self._events: dict[str, LifecycleEvent] = {}
        self._history: list[LifecycleEvent] = []
        self._execution_results: dict[str, bool] = {}
        self._event_payloads: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _canonical_value(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {
                str(key): IncidentWorkflowLifecycle._canonical_value(item)
                for key, item in sorted(
                    value.items(),
                    key=lambda pair: str(pair[0]),
                )
            }
        if isinstance(value, (list, tuple)):
            return [
                IncidentWorkflowLifecycle._canonical_value(item)
                for item in value
            ]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @classmethod
    def _fingerprint(
        cls,
        kind: LifecycleEventKind,
        payload: dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            {
                "kind": kind.value,
                "payload": cls._canonical_value(payload),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _prepare_event(
        self,
        event_id: str,
        kind: LifecycleEventKind,
        payload: dict[str, Any],
    ) -> tuple[LifecycleEvent | None, str]:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")

        fingerprint = self._fingerprint(kind, payload)
        existing = self._events.get(event_id)

        if existing is None:
            return None, fingerprint

        if existing.kind is kind and existing.fingerprint == fingerprint:
            return existing, fingerprint

        raise DuplicateEventConflict(
            f"event_id reused with different content: {event_id}"
        )

    def _assert_nonterminal(self) -> None:
        if self.state in self.TERMINAL_STATES:
            raise LifecycleInvariantError(
                "terminal lifecycle state cannot transition: "
                f"{self.state.value}"
            )

    def _commit(
        self,
        *,
        event_id: str,
        kind: LifecycleEventKind,
        fingerprint: str,
        state_before: IncidentWorkflowState,
        payload: dict[str, Any],
    ) -> LifecycleEvent:
        event = LifecycleEvent(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=state_before,
            state_after=self.state,
        )
        canonical_payload = self._canonical_value(payload)
        if not isinstance(canonical_payload, dict):
            raise LifecycleInvariantError("event payload must canonicalize to mapping")
        self._events[event_id] = event
        self._history.append(event)
        self._event_payloads[event_id] = canonical_payload
        return event

    @staticmethod
    def _normalize_decision(decision: Any) -> tuple[str, str | None]:
        component_id = getattr(decision, "component_id", None)
        raw = getattr(decision, "decision", decision)
        raw = getattr(raw, "value", raw)
        normalized = str(raw).upper()
        if normalized not in {"ALLOW", "DENY"}:
            raise ValueError(
                "authorization decision must be ALLOW or DENY"
            )
        return normalized, component_id

    def record_diagnostics(
        self,
        *,
        event_id: str,
        diagnostics_ref: str,
    ) -> LifecycleEvent:
        if not isinstance(diagnostics_ref, str) or not diagnostics_ref.strip():
            raise ValueError("diagnostics_ref is required")

        kind = LifecycleEventKind.DIAGNOSTICS_RECORDED
        payload = {"diagnostics_ref": diagnostics_ref}
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()
        before = self.state
        self.diagnostics_recorded = True
        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def record_authorization(
        self,
        *,
        event_id: str,
        decision: Any,
    ) -> LifecycleEvent:
        normalized, decision_component = self._normalize_decision(decision)
        payload = {
            "decision": normalized,
            "decision_component_id": decision_component,
        }
        kind = LifecycleEventKind.AUTHORIZATION_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()

        if not self.diagnostics_recorded:
            raise LifecycleInvariantError(
                "authorization requires recorded diagnostics"
            )

        if (
            decision_component is not None
            and decision_component != self.component_id
        ):
            raise LifecycleInvariantError(
                "authorization decision component_id mismatch"
            )

        if (
            self.authorization_decision is not None
            and self.authorization_decision != normalized
        ):
            raise LifecycleInvariantError(
                "authorization decision cannot be rewritten"
            )

        before = self.state
        self.authorization_decision = normalized

        if normalized == "DENY":
            self.state = IncidentWorkflowState.FAILED
            self.failure_reason = LifecycleFailureReason.AUTHORIZATION_DENIED
            self.failure_detail = (
                "canonical authorization denied remediation"
            )

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def record_remediation_eligibility(
        self,
        *,
        event_id: str,
        eligible: bool,
        reason_ref: str | None = None,
    ) -> LifecycleEvent:
        if not isinstance(eligible, bool):
            raise TypeError("eligible must be bool")

        payload = {"eligible": eligible, "reason_ref": reason_ref}
        kind = LifecycleEventKind.REMEDIATION_ELIGIBILITY_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()

        if self.authorization_decision != "ALLOW":
            raise LifecycleInvariantError(
                "remediation eligibility requires ALLOW authorization"
            )

        if (
            self.remediation_eligible is not None
            and self.remediation_eligible != eligible
        ):
            raise LifecycleInvariantError(
                "remediation eligibility cannot be rewritten"
            )

        before = self.state
        self.remediation_eligible = eligible

        if not eligible:
            self.state = IncidentWorkflowState.FAILED
            self.failure_reason = (
                LifecycleFailureReason.REMEDIATION_INELIGIBLE
            )
            self.failure_detail = (
                reason_ref or "remediation marked ineligible"
            )

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def mark_remediating(
        self,
        *,
        event_id: str,
        execution_id: str,
    ) -> LifecycleEvent:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id is required")

        payload = {"execution_id": execution_id}
        kind = LifecycleEventKind.REMEDIATION_STARTED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()

        if not self.diagnostics_recorded:
            raise LifecycleInvariantError(
                "remediation requires recorded diagnostics"
            )
        if self.authorization_decision != "ALLOW":
            raise LifecycleInvariantError(
                "remediation requires ALLOW authorization"
            )
        if self.remediation_eligible is not True:
            raise LifecycleInvariantError(
                "remediation requires explicit eligibility"
            )
        if self.state is not IncidentWorkflowState.OPEN:
            raise LifecycleInvariantError(
                f"cannot start remediation from {self.state.value}"
            )

        before = self.state
        self.execution_id = execution_id
        self.state = IncidentWorkflowState.REMEDIATING

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def record_remediation_result(
        self,
        *,
        event_id: str,
        execution_id: str,
        success: bool,
        replayed: bool = False,
    ) -> LifecycleEvent:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id is required")
        if not isinstance(success, bool):
            raise TypeError("success must be bool")
        if not isinstance(replayed, bool):
            raise TypeError("replayed must be bool")

        payload = {
            "execution_id": execution_id,
            "success": success,
            "replayed": replayed,
        }
        kind = LifecycleEventKind.REMEDIATION_RESULT_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()

        if self.state is not IncidentWorkflowState.REMEDIATING:
            raise LifecycleInvariantError(
                "remediation result requires REMEDIATING state"
            )
        if self.execution_id != execution_id:
            raise LifecycleInvariantError(
                "remediation result execution_id mismatch"
            )

        previous = self._execution_results.get(execution_id)
        if previous is not None and previous != success:
            raise DuplicateExecutionConflict(
                "execution_id reported with contradictory outcomes"
            )

        before = self.state

        if previous is None:
            self._execution_results[execution_id] = success
            self.remediation_succeeded = success

            if not success:
                self.state = IncidentWorkflowState.FAILED
                self.failure_reason = (
                    LifecycleFailureReason.REMEDIATION_FAILED
                )
                self.failure_detail = (
                    "canonical remediation execution reported failure"
                )

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def record_canonical_remediation_result(
        self,
        *,
        event_id: str,
        result: Any,
    ) -> LifecycleEvent:
        execution_id = getattr(result, "execution_id", None)
        execution = getattr(result, "execution", None)
        replayed = bool(getattr(result, "replayed", False))

        if execution is None:
            raise LifecycleInvariantError(
                "canonical remediation result has no execution outcome"
            )

        return self.record_remediation_result(
            event_id=event_id,
            execution_id=execution_id,
            success=bool(execution.success),
            replayed=replayed,
        )

    @staticmethod
    def _normalize_verification(
        verification: Any,
    ) -> tuple[bool, str | None]:
        if isinstance(verification, bool):
            return verification, None

        if not hasattr(verification, "verified"):
            raise TypeError(
                "verification must be bool or expose canonical verified"
            )

        verified = verification.verified
        if not isinstance(verified, bool):
            raise TypeError("verification.verified must be bool")

        reason = getattr(verification, "reason", None)
        return verified, None if reason is None else str(reason)

    def record_verification(
        self,
        *,
        event_id: str,
        verification: Any,
    ) -> LifecycleEvent:
        verified, reason = self._normalize_verification(verification)
        payload = {"verified": verified, "reason": reason}
        kind = LifecycleEventKind.VERIFICATION_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()

        if self.state is not IncidentWorkflowState.REMEDIATING:
            raise LifecycleInvariantError(
                "verification requires REMEDIATING state"
            )
        if self.remediation_succeeded is not True:
            raise LifecycleInvariantError(
                "verification requires a successful remediation result"
            )

        before = self.state
        self.verification_passed = verified

        if verified:
            self.state = IncidentWorkflowState.RECOVERED
        else:
            self.state = IncidentWorkflowState.FAILED
            self.failure_reason = (
                LifecycleFailureReason.VERIFICATION_FAILED
            )
            self.failure_detail = (
                reason or "post-remediation verification failed"
            )

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def mark_timeout(
        self,
        *,
        event_id: str,
        stage: str,
    ) -> LifecycleEvent:
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("stage is required")

        payload = {"stage": stage}
        kind = LifecycleEventKind.TIMEOUT_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()
        before = self.state
        self.state = IncidentWorkflowState.FAILED
        self.failure_reason = LifecycleFailureReason.TIMEOUT
        self.failure_detail = stage

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def cancel(
        self,
        *,
        event_id: str,
        reason: str,
    ) -> LifecycleEvent:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason is required")

        payload = {"reason": reason}
        kind = LifecycleEventKind.CANCELLATION_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()
        before = self.state
        self.state = IncidentWorkflowState.FAILED
        self.failure_reason = LifecycleFailureReason.CANCELLED
        self.failure_detail = reason

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    def mark_retry_exhausted(
        self,
        *,
        event_id: str,
        attempts: int,
        detail: str | None = None,
    ) -> LifecycleEvent:
        if (
            isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or attempts < 1
        ):
            raise ValueError("attempts must be a positive integer")

        payload = {"attempts": attempts, "detail": detail}
        kind = LifecycleEventKind.RETRY_EXHAUSTED_RECORDED
        existing, fingerprint = self._prepare_event(
            event_id,
            kind,
            payload,
        )
        if existing is not None:
            return existing

        self._assert_nonterminal()
        before = self.state
        self.state = IncidentWorkflowState.FAILED
        self.failure_reason = LifecycleFailureReason.RETRY_EXHAUSTED
        self.failure_detail = (
            detail or f"retry attempts exhausted: {attempts}"
        )

        return self._commit(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            state_before=before,
            payload=payload,
        )

    @property
    def history(self) -> tuple[LifecycleEvent, ...]:
        return tuple(self._history)

    def snapshot(self) -> IncidentWorkflowSnapshot:
        return IncidentWorkflowSnapshot(
            workflow_id=self.workflow_id,
            incident_id=self.incident_id,
            component_id=self.component_id,
            state=self.state,
            failure_reason=self.failure_reason,
            failure_detail=self.failure_detail,
            diagnostics_recorded=self.diagnostics_recorded,
            authorization_decision=self.authorization_decision,
            remediation_eligible=self.remediation_eligible,
            execution_id=self.execution_id,
            remediation_succeeded=self.remediation_succeeded,
            verification_passed=self.verification_passed,
            version=len(self._history),
            event_count=len(self._history),
        )

    def _projection_record(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "workflow_id": snapshot.workflow_id,
            "incident_id": snapshot.incident_id,
            "component_id": snapshot.component_id,
            "state": snapshot.state.value,
            "failure_reason": (
                None
                if snapshot.failure_reason is None
                else snapshot.failure_reason.value
            ),
            "failure_detail": snapshot.failure_detail,
            "diagnostics_recorded": snapshot.diagnostics_recorded,
            "authorization_decision": snapshot.authorization_decision,
            "remediation_eligible": snapshot.remediation_eligible,
            "execution_id": snapshot.execution_id,
            "remediation_succeeded": snapshot.remediation_succeeded,
            "verification_passed": snapshot.verification_passed,
            "version": snapshot.version,
            "event_count": snapshot.event_count,
        }

    def to_replay_snapshot(self) -> dict[str, Any]:
        """Serialize deterministic lifecycle history for invariant-safe replay."""
        events: list[dict[str, Any]] = []
        for event in self._history:
            payload = self._event_payloads.get(event.event_id)
            if payload is None:
                raise LifecycleInvariantError(
                    f"event payload missing from lifecycle history: {event.event_id}"
                )
            events.append(
                {
                    "event_id": event.event_id,
                    "kind": event.kind.value,
                    "payload": self._canonical_value(payload),
                    "fingerprint": event.fingerprint,
                    "state_before": event.state_before.value,
                    "state_after": event.state_after.value,
                }
            )

        return {
            "version": self.SNAPSHOT_VERSION,
            "workflow_id": self.workflow_id,
            "incident_id": self.incident_id,
            "component_id": self.component_id,
            "events": events,
            "projection": self._projection_record(),
        }

    @staticmethod
    def _require_snapshot_payload_keys(
        payload: Mapping[str, Any],
        expected: set[str],
    ) -> None:
        if set(payload) != expected:
            raise LifecycleInvariantError(
                "lifecycle replay payload fields do not match event kind"
            )

    def _replay_snapshot_event(
        self,
        *,
        event_id: str,
        kind: LifecycleEventKind,
        payload: Mapping[str, Any],
    ) -> LifecycleEvent:
        if kind is LifecycleEventKind.DIAGNOSTICS_RECORDED:
            self._require_snapshot_payload_keys(payload, {"diagnostics_ref"})
            diagnostics_ref = payload["diagnostics_ref"]
            if not isinstance(diagnostics_ref, str):
                raise LifecycleInvariantError("invalid diagnostics replay payload")
            return self.record_diagnostics(
                event_id=event_id,
                diagnostics_ref=diagnostics_ref,
            )

        if kind is LifecycleEventKind.AUTHORIZATION_RECORDED:
            self._require_snapshot_payload_keys(
                payload,
                {"decision", "decision_component_id"},
            )
            decision = payload["decision"]
            component_id = payload["decision_component_id"]
            if not isinstance(decision, str):
                raise LifecycleInvariantError("invalid authorization replay payload")
            if component_id is not None and not isinstance(component_id, str):
                raise LifecycleInvariantError("invalid authorization component replay")
            return self.record_authorization(
                event_id=event_id,
                decision=_RestoredAuthorizationDecision(
                    decision=decision,
                    component_id=component_id,
                ),
            )

        if kind is LifecycleEventKind.REMEDIATION_ELIGIBILITY_RECORDED:
            self._require_snapshot_payload_keys(
                payload,
                {"eligible", "reason_ref"},
            )
            eligible = payload["eligible"]
            reason_ref = payload["reason_ref"]
            if not isinstance(eligible, bool):
                raise LifecycleInvariantError("invalid eligibility replay payload")
            if reason_ref is not None and not isinstance(reason_ref, str):
                raise LifecycleInvariantError("invalid eligibility reason replay")
            return self.record_remediation_eligibility(
                event_id=event_id,
                eligible=eligible,
                reason_ref=reason_ref,
            )

        if kind is LifecycleEventKind.REMEDIATION_STARTED:
            self._require_snapshot_payload_keys(payload, {"execution_id"})
            execution_id = payload["execution_id"]
            if not isinstance(execution_id, str):
                raise LifecycleInvariantError("invalid remediation start replay")
            return self.mark_remediating(
                event_id=event_id,
                execution_id=execution_id,
            )

        if kind is LifecycleEventKind.REMEDIATION_RESULT_RECORDED:
            self._require_snapshot_payload_keys(
                payload,
                {"execution_id", "success", "replayed"},
            )
            execution_id = payload["execution_id"]
            success = payload["success"]
            replayed = payload["replayed"]
            if not isinstance(execution_id, str):
                raise LifecycleInvariantError("invalid remediation result execution")
            if not isinstance(success, bool) or not isinstance(replayed, bool):
                raise LifecycleInvariantError("invalid remediation result replay")
            return self.record_remediation_result(
                event_id=event_id,
                execution_id=execution_id,
                success=success,
                replayed=replayed,
            )

        if kind is LifecycleEventKind.VERIFICATION_RECORDED:
            self._require_snapshot_payload_keys(payload, {"verified", "reason"})
            verified = payload["verified"]
            reason = payload["reason"]
            if not isinstance(verified, bool):
                raise LifecycleInvariantError("invalid verification replay payload")
            if reason is not None and not isinstance(reason, str):
                raise LifecycleInvariantError("invalid verification reason replay")
            return self.record_verification(
                event_id=event_id,
                verification=_RestoredVerification(
                    verified=verified,
                    reason=reason,
                ),
            )

        if kind is LifecycleEventKind.TIMEOUT_RECORDED:
            self._require_snapshot_payload_keys(payload, {"stage"})
            stage = payload["stage"]
            if not isinstance(stage, str):
                raise LifecycleInvariantError("invalid timeout replay payload")
            return self.mark_timeout(event_id=event_id, stage=stage)

        if kind is LifecycleEventKind.CANCELLATION_RECORDED:
            self._require_snapshot_payload_keys(payload, {"reason"})
            reason = payload["reason"]
            if not isinstance(reason, str):
                raise LifecycleInvariantError("invalid cancellation replay payload")
            return self.cancel(event_id=event_id, reason=reason)

        if kind is LifecycleEventKind.RETRY_EXHAUSTED_RECORDED:
            self._require_snapshot_payload_keys(payload, {"attempts", "detail"})
            attempts = payload["attempts"]
            detail = payload["detail"]
            if isinstance(attempts, bool) or not isinstance(attempts, int):
                raise LifecycleInvariantError("invalid retry replay attempts")
            if detail is not None and not isinstance(detail, str):
                raise LifecycleInvariantError("invalid retry replay detail")
            return self.mark_retry_exhausted(
                event_id=event_id,
                attempts=attempts,
                detail=detail,
            )

        raise LifecycleInvariantError(f"unsupported lifecycle replay event: {kind}")

    @classmethod
    def from_replay_snapshot(
        cls,
        snapshot: Mapping[str, Any],
    ) -> "IncidentWorkflowLifecycle":
        """Reconstruct lifecycle solely by replaying validated historical events."""
        if not isinstance(snapshot, Mapping):
            raise TypeError("lifecycle replay snapshot must be a mapping")

        expected_top_keys = {
            "version",
            "workflow_id",
            "incident_id",
            "component_id",
            "events",
            "projection",
        }
        if set(snapshot) != expected_top_keys:
            raise LifecycleInvariantError("invalid lifecycle replay snapshot fields")
        if snapshot.get("version") != cls.SNAPSHOT_VERSION:
            raise LifecycleInvariantError("unsupported lifecycle replay snapshot version")

        workflow_id = snapshot.get("workflow_id")
        incident_id = snapshot.get("incident_id")
        component_id = snapshot.get("component_id")
        for name, value in (
            ("workflow_id", workflow_id),
            ("incident_id", incident_id),
            ("component_id", component_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise LifecycleInvariantError(
                    f"lifecycle replay {name} is required"
                )

        events = snapshot.get("events")
        projection = snapshot.get("projection")
        if not isinstance(events, list):
            raise LifecycleInvariantError("lifecycle replay events must be a list")
        if not isinstance(projection, Mapping):
            raise LifecycleInvariantError("lifecycle replay projection must be a mapping")

        lifecycle = cls(
            workflow_id=workflow_id,
            incident_id=incident_id,
            component_id=component_id,
        )
        seen_event_ids: set[str] = set()
        expected_entry_keys = {
            "event_id",
            "kind",
            "payload",
            "fingerprint",
            "state_before",
            "state_after",
        }

        for entry in events:
            if not isinstance(entry, Mapping):
                raise LifecycleInvariantError("lifecycle replay event must be a mapping")
            if set(entry) != expected_entry_keys:
                raise LifecycleInvariantError("invalid lifecycle replay event fields")

            event_id = entry.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip():
                raise LifecycleInvariantError("lifecycle replay event_id is required")
            if event_id in seen_event_ids:
                raise DuplicateEventConflict(
                    f"duplicate lifecycle event in replay history: {event_id}"
                )
            seen_event_ids.add(event_id)

            try:
                kind = LifecycleEventKind(entry.get("kind"))
                state_before = IncidentWorkflowState(entry.get("state_before"))
                state_after = IncidentWorkflowState(entry.get("state_after"))
            except (TypeError, ValueError) as exc:
                raise LifecycleInvariantError(
                    "invalid lifecycle replay enum value"
                ) from exc

            payload = entry.get("payload")
            fingerprint = entry.get("fingerprint")
            if not isinstance(payload, Mapping):
                raise LifecycleInvariantError("lifecycle replay payload must be a mapping")
            if not all(isinstance(key, str) for key in payload):
                raise LifecycleInvariantError("lifecycle replay payload keys must be strings")
            if not isinstance(fingerprint, str) or not fingerprint:
                raise LifecycleInvariantError("lifecycle replay fingerprint is required")

            generated = lifecycle._replay_snapshot_event(
                event_id=event_id,
                kind=kind,
                payload=payload,
            )
            if generated.fingerprint != fingerprint:
                raise LifecycleInvariantError(
                    f"lifecycle replay fingerprint mismatch: {event_id}"
                )
            if generated.state_before is not state_before:
                raise LifecycleInvariantError(
                    f"lifecycle replay state_before mismatch: {event_id}"
                )
            if generated.state_after is not state_after:
                raise LifecycleInvariantError(
                    f"lifecycle replay state_after mismatch: {event_id}"
                )

        expected_projection = lifecycle._projection_record()
        if dict(projection) != expected_projection:
            raise LifecycleInvariantError(
                "lifecycle replay projection does not match replayed history"
            )

        return lifecycle
