from sentinel.diagnostic.investigation import InvestigationManager
from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    InvestigationState,
)
from sentinel.diagnostic.store import InvestigationStore


def make_budget():
    return DiagnosticBudget(
        max_duration_seconds=60,
        max_actions=5,
        max_repeated_action=2,
        max_risk=5,
        minimum_evidence=1,
    )


def test_start_creates_active_investigation(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    investigation = manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-001",
    )

    assert investigation.investigation_id == "inv-001"
    assert investigation.incident_id == "inc-001"
    assert investigation.component_id == "%2"
    assert investigation.state is InvestigationState.ACTIVE


def test_start_persists_investigation(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-002",
    )

    reloaded = InvestigationStore(tmp_path).get_investigation("inv-002")

    assert reloaded is not None
    assert reloaded.state is InvestigationState.ACTIVE


def test_duplicate_investigation_identity_is_rejected(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-003",
    )

    try:
        manager.start(
            incident_id="inc-002",
            component_id="%3",
            trigger="other",
            budget=make_budget(),
            investigation_id="inv-003",
        )
        assert False, "expected duplicate investigation rejection"
    except ValueError as exc:
        assert "already exists" in str(exc)


def test_record_action_updates_investigation(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    investigation = manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-004",
    )

    action = DiagnosticAction(
        diagnostic_action_id="diag-001",
        investigation_id="inv-004",
        incident_id="inc-001",
        classification=DiagnosticActionClassification.OBSERVE,
        command="tmux list-panes",
        rationale="inspect pane state",
        expected_information="pane liveness",
        state=DiagnosticActionState.PLANNED,
    )

    updated = manager.record_action("inv-004", action)

    assert updated.action_ids == ["diag-001"]

    reloaded = manager.get("inv-004")
    assert reloaded is not None
    assert reloaded.action_ids == ["diag-001"]


def test_action_identity_mismatch_is_rejected(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-005",
    )

    action = DiagnosticAction(
        diagnostic_action_id="diag-002",
        investigation_id="different-investigation",
        incident_id="inc-001",
        classification=DiagnosticActionClassification.OBSERVE,
        command="tmux list-panes",
        rationale="inspect pane state",
        expected_information="pane liveness",
    )

    try:
        manager.record_action("inv-005", action)
        assert False, "expected investigation mismatch"
    except ValueError as exc:
        assert "investigation_id mismatch" in str(exc)


def test_terminal_transition_is_durable(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-006",
    )

    completed = manager.complete("inv-006")

    assert completed.state is InvestigationState.COMPLETED
    assert completed.completed_at is not None

    reloaded = InvestigationStore(tmp_path).get_investigation("inv-006")

    assert reloaded is not None
    assert reloaded.state is InvestigationState.COMPLETED
    assert reloaded.completed_at is not None


def test_terminal_investigation_cannot_be_modified(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    manager.start(
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        budget=make_budget(),
        investigation_id="inv-007",
    )

    manager.mark_insufficient_evidence("inv-007")

    action = DiagnosticAction(
        diagnostic_action_id="diag-003",
        investigation_id="inv-007",
        incident_id="inc-001",
        classification=DiagnosticActionClassification.OBSERVE,
        command="tmux list-panes",
        rationale="inspect pane state",
        expected_information="pane liveness",
    )

    try:
        manager.record_action("inv-007", action)
        assert False, "expected terminal-state rejection"
    except ValueError as exc:
        assert "not active" in str(exc)


def test_all_terminal_states_are_available(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    manager.start(
        "inc-a", "%1", "test", make_budget(), "inv-a"
    )
    manager.start(
        "inc-b", "%2", "test", make_budget(), "inv-b"
    )
    manager.start(
        "inc-c", "%3", "test", make_budget(), "inv-c"
    )

    assert manager.complete("inv-a").state is InvestigationState.COMPLETED
    assert (
        manager.mark_insufficient_evidence("inv-b").state
        is InvestigationState.INSUFFICIENT_EVIDENCE
    )
    assert (
        manager.mark_budget_exhausted("inv-c").state
        is InvestigationState.BUDGET_EXHAUSTED
    )


def test_recover_discovers_investigation(tmp_path):
    store = InvestigationStore(tmp_path)
    manager = InvestigationManager(store)

    manager.start(
        incident_id="inc-009",
        component_id="%4",
        trigger="test",
        budget=make_budget(),
        investigation_id="inv-009",
    )

    recovered = InvestigationManager(
        InvestigationStore(tmp_path)
    ).recover()

    assert len(recovered) == 1
    assert recovered[0].investigation_id == "inv-009"


def test_manager_does_not_expose_incident_lifecycle_authority(tmp_path):
    manager = InvestigationManager(InvestigationStore(tmp_path))

    assert not hasattr(manager, "resolve_incident")
    assert not hasattr(manager, "create_incident")
    assert not hasattr(manager, "remediate")
    assert not hasattr(manager, "execute")
