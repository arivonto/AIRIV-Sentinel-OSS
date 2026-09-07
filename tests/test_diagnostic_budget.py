from datetime import datetime, timedelta, timezone

import pytest

from sentinel.diagnostic.budget import BudgetManager
from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticBudget,
    Investigation,
    InvestigationState,
)


def make_investigation(
    *,
    created_at=None,
    max_actions=5,
    max_repeated_action=2,
    max_risk=5,
    max_duration_seconds=60,
):
    return Investigation(
        investigation_id="inv-budget-001",
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=max_duration_seconds,
            max_actions=max_actions,
            max_repeated_action=max_repeated_action,
            max_risk=max_risk,
            minimum_evidence=1,
        ),
        created_at=created_at or datetime.now(timezone.utc),
    )


def make_action(
    *,
    action_id="diag-001",
    classification=DiagnosticActionClassification.OBSERVE,
    command="tmux list-panes",
):
    return DiagnosticAction(
        diagnostic_action_id=action_id,
        investigation_id="inv-budget-001",
        incident_id="inc-001",
        classification=classification,
        command=command,
        rationale="inspect state",
        expected_information="current state",
    )


def test_available_budget_allows_diagnostic_action():
    investigation = make_investigation()
    action = make_action()

    decision = BudgetManager().check(investigation, action)

    assert decision.allowed is True
    assert decision.reason == "diagnostic_budget_available"


def test_action_budget_blocks_when_exhausted():
    investigation = make_investigation(max_actions=2)
    investigation.budget.consumed_actions = 2

    decision = BudgetManager().check(
        investigation,
        make_action(),
    )

    assert decision.allowed is False
    assert decision.reason == "action_budget_exhausted"


def test_risk_budget_blocks_when_exhausted():
    investigation = make_investigation(max_risk=3)
    investigation.budget.consumed_risk = 3

    decision = BudgetManager().check(
        investigation,
        make_action(),
    )

    assert decision.allowed is False
    assert decision.reason == "risk_budget_exhausted"


def test_repetition_budget_blocks_repeated_command():
    investigation = make_investigation(max_repeated_action=2)
    investigation.budget.repeated_actions["tmux list-panes"] = 2

    decision = BudgetManager().check(
        investigation,
        make_action(),
    )

    assert decision.allowed is False
    assert decision.reason == "repetition_budget_exhausted"


def test_time_budget_blocks_expired_investigation():
    created = datetime.now(timezone.utc) - timedelta(seconds=61)
    investigation = make_investigation(
        created_at=created,
        max_duration_seconds=60,
    )

    decision = BudgetManager().check(
        investigation,
        make_action(),
    )

    assert decision.allowed is False
    assert decision.reason == "time_budget_exhausted"


def test_consequential_action_is_not_allowed_by_budget_manager():
    investigation = make_investigation()

    decision = BudgetManager().check(
        investigation,
        make_action(
            classification=DiagnosticActionClassification.CONSEQUENTIAL,
        ),
    )

    assert decision.allowed is False
    assert decision.reason == "action_classification_not_diagnostic"


def test_prohibited_action_is_not_allowed_by_budget_manager():
    investigation = make_investigation()

    decision = BudgetManager().check(
        investigation,
        make_action(
            classification=DiagnosticActionClassification.PROHIBITED,
        ),
    )

    assert decision.allowed is False
    assert decision.reason == "action_classification_not_diagnostic"


def test_investigation_must_be_active():
    investigation = make_investigation()
    investigation.state = InvestigationState.COMPLETED

    decision = BudgetManager().check(
        investigation,
        make_action(),
    )

    assert decision.allowed is False
    assert decision.reason == "investigation_not_active"


def test_investigation_identity_is_enforced():
    investigation = make_investigation()

    action = make_action()
    action.investigation_id = "wrong-investigation"

    decision = BudgetManager().check(
        investigation,
        action,
    )

    assert decision.allowed is False
    assert decision.reason == "investigation_id_mismatch"


def test_incident_identity_is_enforced():
    investigation = make_investigation()

    action = make_action()
    action.incident_id = "wrong-incident"

    decision = BudgetManager().check(
        investigation,
        action,
    )

    assert decision.allowed is False
    assert decision.reason == "incident_id_mismatch"


def test_consume_increments_action_and_risk_budget():
    investigation = make_investigation()
    action = make_action()

    BudgetManager().consume(
        investigation,
        action,
        risk_cost=2,
    )

    assert investigation.budget.consumed_actions == 1
    assert investigation.budget.consumed_risk == 2
    assert investigation.budget.repeated_actions[
        "tmux list-panes"
    ] == 1


def test_consume_rejects_exhausted_budget():
    investigation = make_investigation(max_actions=1)
    investigation.budget.consumed_actions = 1

    with pytest.raises(ValueError, match="action_budget_exhausted"):
        BudgetManager().consume(
            investigation,
            make_action(),
        )


def test_consume_rejects_risk_overrun_without_partial_consumption():
    investigation = make_investigation(max_risk=2)
    action = make_action()

    with pytest.raises(ValueError, match="risk_budget_exhausted"):
        BudgetManager().consume(
            investigation,
            action,
            risk_cost=3,
        )

    assert investigation.budget.consumed_actions == 0
    assert investigation.budget.consumed_risk == 0
    assert investigation.budget.repeated_actions == {}


def test_negative_risk_cost_is_rejected():
    investigation = make_investigation()

    with pytest.raises(ValueError, match="must not be negative"):
        BudgetManager().consume(
            investigation,
            make_action(),
            risk_cost=-1,
        )


def test_budget_has_no_reset_or_extension_authority():
    manager = BudgetManager()

    assert not hasattr(manager, "reset")
    assert not hasattr(manager, "extend")
    assert not hasattr(manager, "authorize")
    assert not hasattr(manager, "execute")
    assert not hasattr(manager, "remediate")


def test_budget_manager_does_not_create_incident_lifecycle_authority():
    manager = BudgetManager()

    assert not hasattr(manager, "create_incident")
    assert not hasattr(manager, "resolve_incident")
