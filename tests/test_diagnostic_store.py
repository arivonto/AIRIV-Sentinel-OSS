import json

from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    Investigation,
    InvestigationState,
)
from sentinel.diagnostic.store import InvestigationStore


def make_investigation() -> Investigation:
    return Investigation(
        investigation_id="inv-store-001",
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=5,
            max_repeated_action=2,
            max_risk=5,
            minimum_evidence=1,
        ),
    )


def make_action() -> DiagnosticAction:
    return DiagnosticAction(
        diagnostic_action_id="diag-store-001",
        investigation_id="inv-store-001",
        incident_id="inc-001",
        classification=DiagnosticActionClassification.OBSERVE,
        command="tmux list-panes",
        rationale="Inspect pane state",
        expected_information="Pane liveness",
    )


def test_investigation_survives_reload(tmp_path):
    store = InvestigationStore(tmp_path)
    original = make_investigation()

    store.save_investigation(original)

    reloaded = InvestigationStore(tmp_path).get_investigation(
        original.investigation_id
    )

    assert reloaded is not None
    assert reloaded.investigation_id == original.investigation_id
    assert reloaded.incident_id == original.incident_id
    assert reloaded.component_id == original.component_id
    assert reloaded.state is InvestigationState.ACTIVE
    assert reloaded.budget.max_actions == 5


def test_action_survives_reload(tmp_path):
    store = InvestigationStore(tmp_path)
    action = make_action()

    store.save_action(action)

    reloaded = InvestigationStore(tmp_path).get_action(
        action.investigation_id,
        action.diagnostic_action_id,
    )

    assert reloaded is not None
    assert reloaded.diagnostic_action_id == action.diagnostic_action_id
    assert reloaded.classification is DiagnosticActionClassification.OBSERVE
    assert reloaded.state is DiagnosticActionState.PLANNED


def test_missing_investigation_returns_none(tmp_path):
    store = InvestigationStore(tmp_path)

    assert store.get_investigation("does-not-exist") is None


def test_missing_action_returns_none(tmp_path):
    store = InvestigationStore(tmp_path)

    assert store.get_action("inv-none", "diag-none") is None


def test_history_is_append_oriented(tmp_path):
    store = InvestigationStore(tmp_path)

    store.append_history(
        "inv-history",
        {"event": "CREATED", "investigation_id": "inv-history"},
    )
    store.append_history(
        "inv-history",
        {"event": "ACTION_PLANNED", "action_id": "diag-001"},
    )

    history = (
        tmp_path
        / "investigations"
        / "inv-history"
        / "history.jsonl"
    )

    lines = history.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "CREATED"
    assert json.loads(lines[1])["event"] == "ACTION_PLANNED"


def test_recover_returns_persisted_investigations(tmp_path):
    store = InvestigationStore(tmp_path)

    first = make_investigation()
    second = Investigation(
        investigation_id="inv-store-002",
        incident_id="inc-002",
        component_id="%3",
        trigger="contract_violation",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=30,
            max_actions=3,
            max_repeated_action=1,
            max_risk=3,
            minimum_evidence=1,
        ),
    )

    store.save_investigation(first)
    store.save_investigation(second)

    recovered = InvestigationStore(tmp_path).recover()
    recovered_ids = {item.investigation_id for item in recovered}

    assert recovered_ids == {
        "inv-store-001",
        "inv-store-002",
    }


def test_atomic_write_leaves_no_tmp_file(tmp_path):
    store = InvestigationStore(tmp_path)
    investigation = make_investigation()

    store.save_investigation(investigation)

    directory = (
        tmp_path
        / "investigations"
        / investigation.investigation_id
    )

    temporary_files = list(directory.glob("*.tmp"))

    assert temporary_files == []
