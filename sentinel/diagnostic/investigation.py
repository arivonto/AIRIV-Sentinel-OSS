from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import (
    Diagnosis,
    DiagnosticAction,
    DiagnosticBudget,
    Hypothesis,
    Investigation,
    InvestigationState,
    Observation,
    utc_now,
)
from .store import InvestigationStore


class InvestigationManager:
    """
    Owns Diagnostic Engine investigation lifecycle.

    This class does not own Incident lifecycle, remediation authority,
    execution authority, or verification authority.
    """

    def __init__(self, store: InvestigationStore) -> None:
        self.store = store

    def start(
        self,
        incident_id: str,
        component_id: str,
        trigger: str,
        budget: Any,
        investigation_id: str | None = None,
    ) -> Investigation:
        if not incident_id:
            raise ValueError("incident_id is required")

        if not component_id:
            raise ValueError("component_id is required")

        if not trigger:
            raise ValueError("trigger is required")

        investigation_id = investigation_id or str(uuid4())

        if self.store.get_investigation(investigation_id) is not None:
            raise ValueError(
                f"investigation already exists: {investigation_id}"
            )

        investigation = Investigation(
            investigation_id=investigation_id,
            incident_id=incident_id,
            component_id=component_id,
            trigger=trigger,
            state=InvestigationState.ACTIVE,
            budget=budget,
        )

        self.store.save_investigation(investigation)
        self.store.append_history(
            investigation_id,
            {
                "event": "INVESTIGATION_CREATED",
                "investigation_id": investigation_id,
                "incident_id": incident_id,
                "component_id": component_id,
                "trigger": trigger,
                "occurred_at": utc_now(),
            },
        )

        return investigation

    def get(self, investigation_id: str) -> Investigation | None:
        return self.store.get_investigation(investigation_id)

    def record_action(
        self,
        investigation_id: str,
        action: DiagnosticAction,
        *,
        consumed_budget: DiagnosticBudget | None = None,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        if action.investigation_id != investigation_id:
            raise ValueError("action investigation_id mismatch")

        if action.incident_id != investigation.incident_id:
            raise ValueError("action incident_id mismatch")

        if action.diagnostic_action_id in investigation.action_ids:
            raise ValueError(
                f"diagnostic action already recorded: "
                f"{action.diagnostic_action_id}"
            )

        if consumed_budget is not None:
            investigation.budget = consumed_budget

        # Persist the reservation before execution; subsequent reloads must
        # retain all consumed counters even if execution or evidence fails.
        self.store.save_action(action)
        investigation.action_ids.append(action.diagnostic_action_id)
        self._touch(investigation)
        self.store.save_investigation(investigation)

        self.store.append_history(
            investigation_id,
            {
                "event": "DIAGNOSTIC_ACTION_RECORDED",
                "investigation_id": investigation_id,
                "diagnostic_action_id": action.diagnostic_action_id,
                "state": action.state,
                "occurred_at": utc_now(),
            },
        )

        return investigation

    def update_action(
        self,
        investigation_id: str,
        action: DiagnosticAction,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        if action.investigation_id != investigation_id:
            raise ValueError("action_investigation_id_mismatch")

        if action.diagnostic_action_id not in investigation.action_ids:
            raise ValueError("action_not_recorded")

        self.store.save_action(action)
        self.store.append_history(
            investigation_id,
            {
                "event": "ACTION_UPDATED",
                "investigation_id": investigation_id,
                "diagnostic_action_id": action.diagnostic_action_id,
                "state": action.state.value,
                "occurred_at": datetime.now(timezone.utc),
            },
        )

        investigation.updated_at = datetime.now(timezone.utc)
        self.store.save_investigation(investigation)

        return investigation

    def record_observation(
        self,
        investigation_id: str,
        observation: Observation,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        if observation.investigation_id != investigation_id:
            raise ValueError("observation investigation_id mismatch")

        if observation.component_id != investigation.component_id:
            raise ValueError("observation component_id mismatch")

        if observation.observation_id in investigation.observation_ids:
            raise ValueError(
                f"observation already recorded: "
                f"{observation.observation_id}"
            )

        self.store.save_observation(observation)
        investigation.observation_ids.append(observation.observation_id)
        self._touch(investigation)

        self.store.append_history(
            investigation_id,
            {
                "event": "OBSERVATION_RECORDED",
                "investigation_id": investigation_id,
                "observation_id": observation.observation_id,
                "diagnostic_action_id": observation.diagnostic_action_id,
                "occurred_at": utc_now(),
            },
        )

        self.store.save_investigation(investigation)
        return investigation

    def record_hypothesis(
        self,
        investigation_id: str,
        hypothesis: Hypothesis,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        if hypothesis.investigation_id != investigation_id:
            raise ValueError("hypothesis investigation_id mismatch")

        if hypothesis.hypothesis_id in investigation.current_hypothesis_ids:
            raise ValueError(
                f"hypothesis already recorded: {hypothesis.hypothesis_id}"
            )

        self.store.save_hypothesis(hypothesis)
        investigation.current_hypothesis_ids.append(
            hypothesis.hypothesis_id
        )
        self._touch(investigation)

        self.store.append_history(
            investigation_id,
            {
                "event": "HYPOTHESIS_RECORDED",
                "investigation_id": investigation_id,
                "hypothesis_id": hypothesis.hypothesis_id,
                "status": hypothesis.status,
                "occurred_at": utc_now(),
            },
        )

        self.store.save_investigation(investigation)
        return investigation

    def record_diagnosis(
        self,
        investigation_id: str,
        diagnosis: Diagnosis,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        if diagnosis.investigation_id != investigation_id:
            raise ValueError("diagnosis investigation_id mismatch")

        if investigation.diagnosis_id is not None:
            raise ValueError(
                f"diagnosis already recorded: {investigation.diagnosis_id}"
            )

        self.store.save_diagnosis(diagnosis)

        investigation.diagnosis_id = diagnosis.diagnosis_id
        self._touch(investigation)

        self.store.append_history(
            investigation_id,
            {
                "event": "DIAGNOSIS_RECORDED",
                "investigation_id": investigation_id,
                "diagnosis_id": diagnosis.diagnosis_id,
                "status": diagnosis.status,
                "occurred_at": utc_now(),
            },
        )

        self.store.save_investigation(investigation)
        return investigation

    def add_evidence_reference(
        self,
        investigation_id: str,
        evidence_id: str,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        if not evidence_id:
            raise ValueError("evidence_id is required")

        if evidence_id not in investigation.evidence_ids:
            investigation.evidence_ids.append(evidence_id)
            self._touch(investigation)

            self.store.append_history(
                investigation_id,
                {
                    "event": "EVIDENCE_REFERENCE_RECORDED",
                    "investigation_id": investigation_id,
                    "evidence_id": evidence_id,
                    "occurred_at": utc_now(),
                },
            )

            self.store.save_investigation(investigation)

        return investigation

    def complete(
        self,
        investigation_id: str,
    ) -> Investigation:
        return self._terminal_transition(
            investigation_id,
            InvestigationState.COMPLETED,
            "INVESTIGATION_COMPLETED",
        )

    def mark_insufficient_evidence(
        self,
        investigation_id: str,
    ) -> Investigation:
        return self._terminal_transition(
            investigation_id,
            InvestigationState.INSUFFICIENT_EVIDENCE,
            "INVESTIGATION_INSUFFICIENT_EVIDENCE",
        )

    def mark_budget_exhausted(
        self,
        investigation_id: str,
    ) -> Investigation:
        return self._terminal_transition(
            investigation_id,
            InvestigationState.BUDGET_EXHAUSTED,
            "INVESTIGATION_BUDGET_EXHAUSTED",
        )

    def escalate(
        self,
        investigation_id: str,
    ) -> Investigation:
        return self._terminal_transition(
            investigation_id,
            InvestigationState.ESCALATED,
            "INVESTIGATION_ESCALATED",
        )

    def recover(self) -> list[Investigation]:
        return self.store.recover()

    def _require_active(self, investigation_id: str) -> Investigation:
        investigation = self.store.get_investigation(investigation_id)

        if investigation is None:
            raise KeyError(f"investigation not found: {investigation_id}")

        if investigation.state is not InvestigationState.ACTIVE:
            raise ValueError(
                f"investigation is not active: {investigation.state.value}"
            )

        return investigation

    def _terminal_transition(
        self,
        investigation_id: str,
        state: InvestigationState,
        event: str,
    ) -> Investigation:
        investigation = self._require_active(investigation_id)

        now = utc_now()
        investigation.state = state
        investigation.updated_at = now
        investigation.completed_at = now

        self.store.append_history(
            investigation_id,
            {
                "event": event,
                "investigation_id": investigation_id,
                "occurred_at": now,
            },
        )

        self.store.save_investigation(investigation)
        return investigation

    def _touch(self, investigation: Investigation) -> None:
        investigation.updated_at = utc_now()
