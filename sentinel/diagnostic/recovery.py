from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import (
    DiagnosticAction,
    DiagnosticActionState,
)
from .store import InvestigationStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    investigation_id: str
    diagnostic_action_id: str
    previous_state: DiagnosticActionState
    resulting_state: DiagnosticActionState
    decision: str
    reason: str
    recovered_at: datetime


class RecoveryManager:
    """
    Reconciles durable diagnostic action state after interruption/restart.

    Authority boundary:
    - may reconcile durable diagnostic state
    - may transition RUNNING -> UNKNOWN
    - may identify reusable COMPLETED results
    - may preserve PLANNED actions for later explicit processing

    This manager does not:
    - execute commands
    - authorize actions
    - create diagnostic actions
    - retry UNKNOWN actions
    - reset budgets
    - create or resolve incidents
    - authorize remediation
    """

    def __init__(self, store: InvestigationStore) -> None:
        self.store = store

    def recover_investigation(
        self,
        investigation_id: str,
    ) -> list[RecoveryRecord]:
        investigation = self.store.get_investigation(
            investigation_id
        )

        if investigation is None:
            raise KeyError(
                f"investigation not found: {investigation_id}"
            )

        records: list[RecoveryRecord] = []

        for diagnostic_action_id in investigation.action_ids:
            action = self.store.get_action(
                investigation_id,
                diagnostic_action_id,
            )

            if action is None:
                continue

            record = self.reconcile_action(
                investigation_id,
                action,
            )

            records.append(record)

        return records

    def recover(self) -> list[RecoveryRecord]:
        records: list[RecoveryRecord] = []

        for investigation in self.store.recover():
            records.extend(
                self.recover_investigation(
                    investigation.investigation_id,
                )
            )

        return records

    def reconcile_action(
        self,
        investigation_id: str,
        action: DiagnosticAction,
    ) -> RecoveryRecord:
        if action.investigation_id != investigation_id:
            raise ValueError("investigation_id_mismatch")

        previous_state = action.state

        if action.state is DiagnosticActionState.PLANNED:
            decision = "RECONCILE_PLANNED"
            reason = (
                "execution_not_established; "
                "no automatic execution permitted"
            )
            resulting_state = DiagnosticActionState.PLANNED

        elif action.state is DiagnosticActionState.RUNNING:
            action.state = DiagnosticActionState.UNKNOWN
            self.store.save_action(action)

            self.store.append_history(
                investigation_id,
                {
                    "event": "DIAGNOSTIC_ACTION_RECOVERED_UNKNOWN",
                    "investigation_id": investigation_id,
                    "diagnostic_action_id": (
                        action.diagnostic_action_id
                    ),
                    "previous_state": previous_state.value,
                    "resulting_state": (
                        DiagnosticActionState.UNKNOWN.value
                    ),
                    "occurred_at": utc_now(),
                },
            )

            decision = "MARK_UNKNOWN"
            reason = (
                "execution_interrupted_or_not_established_after_restart; "
                "blind retry prohibited"
            )
            resulting_state = DiagnosticActionState.UNKNOWN

        elif action.state is DiagnosticActionState.COMPLETED:
            if action.result is None:
                decision = "RECONCILE_COMPLETED"
                reason = (
                    "completed action has no durable execution result; "
                    "result cannot be safely replayed"
                )
            else:
                decision = "REUSE_COMPLETED_RESULT"
                reason = (
                    "durable execution result is available; "
                    "execution must not be repeated"
                )

            resulting_state = DiagnosticActionState.COMPLETED

        elif action.state is DiagnosticActionState.UNKNOWN:
            decision = "PRESERVE_UNKNOWN"
            reason = (
                "execution outcome remains indeterminate; "
                "automatic retry prohibited"
            )
            resulting_state = DiagnosticActionState.UNKNOWN

        else:
            raise ValueError(
                f"unsupported diagnostic action state: "
                f"{action.state}"
            )

        return RecoveryRecord(
            investigation_id=investigation_id,
            diagnostic_action_id=action.diagnostic_action_id,
            previous_state=previous_state,
            resulting_state=resulting_state,
            decision=decision,
            reason=reason,
            recovered_at=utc_now(),
        )
