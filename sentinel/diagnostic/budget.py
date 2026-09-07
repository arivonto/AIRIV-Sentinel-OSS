from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticBudget,
    Investigation,
)


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    reason: str


class BudgetManager:
    """
    Hard safety boundary for autonomous diagnostic investigation.

    BudgetManager does not execute actions, authorize remediation,
    alter Incident lifecycle, or reset/extend exhausted budgets.
    """

    def __init__(self, clock=None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def check(
        self,
        investigation: Investigation,
        action: DiagnosticAction,
    ) -> BudgetDecision:
        budget = investigation.budget

        if investigation.state.value != "ACTIVE":
            return BudgetDecision(False, "investigation_not_active")

        if action.investigation_id != investigation.investigation_id:
            return BudgetDecision(False, "investigation_id_mismatch")

        if action.incident_id != investigation.incident_id:
            return BudgetDecision(False, "incident_id_mismatch")

        if action.classification in {
            DiagnosticActionClassification.CONSEQUENTIAL,
            DiagnosticActionClassification.PROHIBITED,
        }:
            return BudgetDecision(
                False,
                "action_classification_not_diagnostic",
            )

        if budget.consumed_actions >= budget.max_actions:
            return BudgetDecision(False, "action_budget_exhausted")

        if budget.consumed_risk >= budget.max_risk:
            return BudgetDecision(False, "risk_budget_exhausted")

        action_key = action.command.strip()
        repetitions = budget.repeated_actions.get(action_key, 0)

        if repetitions >= budget.max_repeated_action:
            return BudgetDecision(
                False,
                "repetition_budget_exhausted",
            )

        elapsed = (
            self._clock() - investigation.created_at
        ).total_seconds()

        if elapsed >= budget.max_duration_seconds:
            return BudgetDecision(False, "time_budget_exhausted")

        return BudgetDecision(True, "diagnostic_budget_available")

    def consume(
        self,
        investigation: Investigation,
        action: DiagnosticAction,
        risk_cost: int = 1,
    ) -> None:
        decision = self.check(investigation, action)

        if not decision.allowed:
            raise ValueError(decision.reason)

        if risk_cost < 0:
            raise ValueError("risk_cost must not be negative")

        if budget_would_exceed_risk(
            investigation.budget,
            risk_cost,
        ):
            raise ValueError("risk_budget_exhausted")

        command_key = action.command.strip()

        investigation.budget.consumed_actions += 1
        investigation.budget.consumed_risk += risk_cost
        investigation.budget.repeated_actions[command_key] = (
            investigation.budget.repeated_actions.get(command_key, 0) + 1
        )


def budget_would_exceed_risk(
    budget: DiagnosticBudget,
    risk_cost: int,
) -> bool:
    return (
        budget.consumed_risk + risk_cost
        > budget.max_risk
    )
