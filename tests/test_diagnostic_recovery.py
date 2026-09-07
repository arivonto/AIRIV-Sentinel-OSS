from datetime import datetime, timezone

from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    DiagnosticResult,
    Investigation,
    InvestigationState,
)
from sentinel.diagnostic.recovery import RecoveryManager
from sentinel.diagnostic.store import InvestigationStore


def make_investigation(tmp_path):
    store = InvestigationStore(tmp_path)

    investigation = Investigation(
        investigation_id="inv-recovery",
        incident_id="inc-001",
        component_id="pane-1",
        trigger="recovery test",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=10,
            max_repeated_action=3,
            max_risk=10,
            minimum_evidence=1,
        ),
        action_ids=[],
    )

    store.save_investigation(investigation)

    return store, investigation


def make_action(
    investigation_id,
    state,
    result=None,
):
    return DiagnosticAction(
        diagnostic_action_id=f"action-{state.value.lower()}",
        investigation_id=investigation_id,
        incident_id="inc-001",
        classification=DiagnosticActionClassification.OBSERVE,
        command="printf diagnostic",
        rationale="recovery test",
        expected_information="diagnostic output",
        state=state,
        result=result,
    )


def test_planned_action_is_not_executed_or_changed(tmp_path):
    store, investigation = make_investigation(tmp_path)

    action = make_action(
        investigation.investigation_id,
        DiagnosticActionState.PLANNED,
    )

    store.save_action(action)
    investigation.action_ids.append(action.diagnostic_action_id)
    store.save_investigation(investigation)

    record = RecoveryManager(store).reconcile_action(
        investigation.investigation_id,
        action,
    )

    assert record.previous_state is DiagnosticActionState.PLANNED
    assert record.resulting_state is DiagnosticActionState.PLANNED
    assert record.decision == "RECONCILE_PLANNED"

    persisted = store.get_action(
        investigation.investigation_id,
        action.diagnostic_action_id,
    )
    assert persisted.state is DiagnosticActionState.PLANNED


def test_running_action_becomes_unknown(tmp_path):
    store, investigation = make_investigation(tmp_path)

    action = make_action(
        investigation.investigation_id,
        DiagnosticActionState.RUNNING,
    )

    store.save_action(action)
    investigation.action_ids.append(action.diagnostic_action_id)
    store.save_investigation(investigation)

    record = RecoveryManager(store).reconcile_action(
        investigation.investigation_id,
        action,
    )

    assert record.previous_state is DiagnosticActionState.RUNNING
    assert record.resulting_state is DiagnosticActionState.UNKNOWN
    assert record.decision == "MARK_UNKNOWN"

    persisted = store.get_action(
        investigation.investigation_id,
        action.diagnostic_action_id,
    )
    assert persisted.state is DiagnosticActionState.UNKNOWN


def test_unknown_action_is_preserved_without_retry(tmp_path):
    store, investigation = make_investigation(tmp_path)

    action = make_action(
        investigation.investigation_id,
        DiagnosticActionState.UNKNOWN,
    )

    store.save_action(action)
    investigation.action_ids.append(action.diagnostic_action_id)
    store.save_investigation(investigation)

    record = RecoveryManager(store).reconcile_action(
        investigation.investigation_id,
        action,
    )

    assert record.previous_state is DiagnosticActionState.UNKNOWN
    assert record.resulting_state is DiagnosticActionState.UNKNOWN
    assert record.decision == "PRESERVE_UNKNOWN"

    persisted = store.get_action(
        investigation.investigation_id,
        action.diagnostic_action_id,
    )
    assert persisted.state is DiagnosticActionState.UNKNOWN


def test_completed_action_reuses_durable_result(tmp_path):
    store, investigation = make_investigation(tmp_path)

    now = datetime.now(timezone.utc)

    result = DiagnosticResult(
        success=True,
        stdout="healthy",
        stderr="",
        exit_code=0,
        started_at=now,
        finished_at=now,
        observation={},
    )

    action = make_action(
        investigation.investigation_id,
        DiagnosticActionState.COMPLETED,
        result=result,
    )

    store.save_action(action)
    investigation.action_ids.append(action.diagnostic_action_id)
    store.save_investigation(investigation)

    record = RecoveryManager(store).reconcile_action(
        investigation.investigation_id,
        action,
    )

    assert record.previous_state is DiagnosticActionState.COMPLETED
    assert record.resulting_state is DiagnosticActionState.COMPLETED
    assert record.decision == "REUSE_COMPLETED_RESULT"

    persisted = store.get_action(
        investigation.investigation_id,
        action.diagnostic_action_id,
    )
    assert persisted.state is DiagnosticActionState.COMPLETED
    assert persisted.result is not None
    assert persisted.result.stdout == "healthy"


def test_completed_without_result_is_not_reexecuted(tmp_path):
    store, investigation = make_investigation(tmp_path)

    action = make_action(
        investigation.investigation_id,
        DiagnosticActionState.COMPLETED,
        result=None,
    )

    store.save_action(action)
    investigation.action_ids.append(action.diagnostic_action_id)
    store.save_investigation(investigation)

    record = RecoveryManager(store).reconcile_action(
        investigation.investigation_id,
        action,
    )

    assert record.resulting_state is DiagnosticActionState.COMPLETED
    assert record.decision == "RECONCILE_COMPLETED"


def test_investigation_recovery_reconciles_all_actions(tmp_path):
    store, investigation = make_investigation(tmp_path)

    running = make_action(
        investigation.investigation_id,
        DiagnosticActionState.RUNNING,
    )

    unknown = make_action(
        investigation.investigation_id,
        DiagnosticActionState.UNKNOWN,
    )

    store.save_action(running)
    store.save_action(unknown)

    investigation.action_ids.extend(
        [
            running.diagnostic_action_id,
            unknown.diagnostic_action_id,
        ]
    )
    store.save_investigation(investigation)

    records = RecoveryManager(store).recover_investigation(
        investigation.investigation_id,
    )

    assert len(records) == 2

    states = {
        record.diagnostic_action_id: record.resulting_state
        for record in records
    }

    assert states[running.diagnostic_action_id] is (
        DiagnosticActionState.UNKNOWN
    )
    assert states[unknown.diagnostic_action_id] is (
        DiagnosticActionState.UNKNOWN
    )


def test_recovery_does_not_expose_execution_authority(tmp_path):
    manager = RecoveryManager(
        InvestigationStore(tmp_path)
    )

    public_methods = {
        name
        for name in dir(manager)
        if not name.startswith("_")
    }

    assert public_methods == {
        "reconcile_action",
        "recover_investigation",
        "recover",
        "store",
    }


def test_identity_mismatch_is_rejected(tmp_path):
    store, investigation = make_investigation(tmp_path)

    action = make_action(
        "different-investigation",
        DiagnosticActionState.RUNNING,
    )

    try:
        RecoveryManager(store).reconcile_action(
            investigation.investigation_id,
            action,
        )
    except ValueError as exc:
        assert str(exc) == "investigation_id_mismatch"
    else:
        raise AssertionError(
            "identity mismatch must be rejected"
        )
