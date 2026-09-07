"""Phase 2.12A: isolated diagnostic repairs and passive Commander evidence."""
import ast
import inspect
import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from sentinel.runtime import SentinelRuntime
from sentinel.diagnostic.runtime_coordinator import RuntimeDiagnosticCoordinator, RuntimeDiagnosticConfig
from sentinel.diagnostic.store import InvestigationStore
from sentinel.diagnostic.executor import DiagnosticResult
from sentinel.diagnostic.models import Diagnosis, DiagnosisStatus, Hypothesis, HypothesisStatus, InvestigationState
from sentinel.worker import observability, composition, entrypoint


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv('AIRIV_SENTINEL_DIAGNOSTIC_DIR', str(tmp_path / 'diagnostic'))
    monkeypatch.setenv('AIRIV_SENTINEL_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setattr(observability, 'REPOSITORY_ROOT', tmp_path)
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
        monkeypatch.delenv(name, raising=False)
    return SentinelRuntime()


def register(runtime):
    incident = runtime.incident_manager.evaluate_anomaly(
        observation={'pane_id': '%7', 'component_id': '%7'},
        anomaly_type='UNKNOWN_DEAD_PANE', reason='controlled test')
    return incident, runtime.diagnostic.register_incident(incident)


def fake_execute(action):
    now = datetime.now(timezone.utc)
    return DiagnosticResult(diagnostic_action_id=action.diagnostic_action_id,
        command=action.command, started_at=now, finished_at=now,
        stdout='controlled observation', stderr='', exit_code=0,
        success=True, state='COMPLETED')


@pytest.mark.parametrize('limit,repeat,risk,expected', [(5,10,10,5), (5,2,5,4), (5,10,2,2)])
def test_persistent_budget_stops_56_cycles(runtime, limit, repeat, risk, expected):
    coordinator = runtime.diagnostic
    coordinator.config = RuntimeDiagnosticConfig(max_actions=limit,
        max_repeated_action=repeat, max_risk=risk)
    incident, investigation = register(runtime)
    coordinator.executor.execute = Mock(side_effect=fake_execute)
    for index in range(56):
        coordinator.run_cycle()
        # Read through a fresh store, never a shared in-memory budget.
        saved = InvestigationStore(coordinator.store.root).get_investigation(investigation.investigation_id)
        assert saved.budget.consumed_actions == len(saved.action_ids) == min(index + 1, expected)
        assert saved.budget.consumed_risk == saved.budget.consumed_actions
        assert sum(saved.budget.repeated_actions.values()) == saved.budget.consumed_actions
        assert max(saved.budget.repeated_actions.values()) <= repeat
        if index + 1 >= expected and (expected == limit or expected == risk):
            assert saved.state is InvestigationState.BUDGET_EXHAUSTED
    assert saved.state is InvestigationState.BUDGET_EXHAUSTED
    assert coordinator.executor.execute.call_count == expected
    assert saved.diagnosis_id is None
    directory = coordinator.store._investigation_dir(saved.investigation_id)
    assert not (directory / 'diagnosis.json').exists()
    assert len(list((directory / 'actions').glob('*.json'))) == expected
    history = (directory / 'history.jsonl').read_text()
    assert history.count('DIAGNOSTIC_ACTION_RECORDED') == expected
    assert history.count('INVESTIGATION_BUDGET_EXHAUSTED') == 1
    assert coordinator.run_cycle() == []


def test_reservation_survives_execution_failure(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    coordinator.executor.execute = Mock(side_effect=RuntimeError('controlled failure'))
    for _ in range(56):
        coordinator.run_cycle()
    saved = coordinator.store.get_investigation(investigation.investigation_id)
    assert saved.budget.consumed_actions == len(saved.action_ids) == 4
    assert saved.budget.consumed_risk == 4
    assert saved.state is InvestigationState.BUDGET_EXHAUSTED


@pytest.mark.parametrize('invocation', [None, '', 'environment-only-id'])
def test_canonical_lookup_and_safe_durable_decision(runtime, monkeypatch, invocation):
    if invocation is None:
        monkeypatch.delenv('INVOCATION_ID', raising=False)
    else:
        monkeypatch.setenv('INVOCATION_ID', invocation)
    monkeypatch.setattr(observability.os, 'getpid', lambda: 43210)
    bundle = composition.build_production_supervision(runtime, entrypoint.build_production_config())
    incident, investigation = register(runtime)
    manager, coordinator = runtime.incident_manager, runtime.diagnostic
    assert manager.get_active_incident(incident.component_id) is incident
    assert manager.get_active_incident(incident.incident_id) is None
    assert manager.get_incident_by_id(incident.incident_id) is incident
    assert manager.get_incident_by_id(incident.component_id) is None
    assert coordinator.incident_lookup.__self__ is manager
    assert coordinator.incident_manager is runtime.commander.incident_manager is manager
    assert bundle.runtime is bundle.capability_worker.runtime is runtime
    assert coordinator.commander_semantic_policy.list_triggers() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    # Existing evaluation receives caller-supplied hypotheses. This is not a generator.
    hypothesis = Hypothesis('controlled', investigation.investigation_id, 'controlled conclusion',
        status=HypothesisStatus.SUPPORTED, supporting_evidence_ids=['controlled-evidence'])
    investigation.current_hypothesis_ids = [hypothesis.hypothesis_id]
    investigation.evidence_ids = ['controlled-evidence']
    coordinator.store.save_investigation(investigation)
    coordinator.hypothesis_manager.get = Mock(return_value=hypothesis)
    coordinator.commander_semantic_policy.assess = Mock(wraps=coordinator.commander_semantic_policy.assess)
    coordinator.commander_intent_decider.decide = Mock(wraps=coordinator.commander_intent_decider.decide)
    coordinator.commander_handoff.decide = Mock(side_effect=AssertionError('no handoff'))
    runtime.execution.execute = Mock(side_effect=AssertionError('no remediation'))
    coordinator.executor.execute = Mock(side_effect=AssertionError('diagnosis already ready'))
    results = coordinator.run_cycle()
    assert results[0].diagnosis.status is DiagnosisStatus.ESTABLISHED
    assert results[0].diagnosis.conclusion == hypothesis.statement
    coordinator._handoff_diagnosis(results[0].investigation, results[0].diagnosis)
    assert coordinator.run_cycle() == []
    coordinator.commander_semantic_policy.assess.assert_called_once_with(incident.anomaly_type)
    coordinator.commander_intent_decider.decide.assert_called_once()
    coordinator.commander_handoff.decide.assert_not_called()
    runtime.execution.execute.assert_not_called()
    path = bundle.capability_worker._observability.root / 'commander_decisions.jsonl'
    record, = [json.loads(line) for line in path.read_text().splitlines()]
    assert record['pid'] == 43210
    assert record['invocation_id'] == invocation
    assert record['schema_version'] == 1 and record['timestamp']
    assert record['component_id'] == incident.component_id
    assert record['incident_id'] == incident.incident_id
    assert record['investigation_id'] == investigation.investigation_id
    assert record['diagnosis_id'] == results[0].diagnosis.diagnosis_id
    assert record['semantic_configured'] is False
    assert record['remediation_required'] is False
    assert record['commander_action_required'] is True
    assert record['semantic_reason'] == 'semantic_policy_unconfigured'
    assert record['commander_intent'] == 'NEED_COMMANDER'
    assert record['final_disposition'] == incident.final_outcome == 'ESCALATED'
    assert 'execution_id' not in record and 'remediation_policy_decision' not in record


@pytest.mark.parametrize('wrong_field', ['incident_id', 'component_id'])
def test_mismatched_lookup_rejected_before_assessment(runtime, wrong_field):
    from copy import copy
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    wrong = copy(incident)
    setattr(wrong, wrong_field, 'wrong')
    coordinator.incident_lookup = Mock(return_value=wrong)
    coordinator.commander_intent_assessor.assess = Mock()
    diagnosis = Diagnosis('diagnosis', investigation.investigation_id, 'test', DiagnosisStatus.ESTABLISHED)
    with pytest.raises(ValueError, match='identity mismatch'):
        coordinator._handoff_diagnosis(investigation, diagnosis)
    coordinator.incident_lookup.assert_called_once_with(investigation.incident_id)
    coordinator.commander_intent_assessor.assess.assert_not_called()


def test_structural_authorities_and_passive_observer():
    runtime_source = inspect.getsource(__import__('sentinel.runtime', fromlist=['SentinelRuntime']))
    tree = ast.parse(runtime_source)
    names = [node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    for authority in ('IncidentManager', 'CommanderOrchestrator', 'RuntimeDiagnosticCoordinator'):
        assert names.count(authority) == 1
    tree = ast.parse(inspect.getsource(__import__('sentinel.diagnostic.runtime_coordinator', fromlist=['RuntimeDiagnosticCoordinator'])))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert sum(isinstance(n.func, ast.Attribute) and n.func.attr == 'assess' for n in calls) == 1
    assert sum(isinstance(n.func, ast.Attribute) and n.func.attr == 'decide' and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == 'commander_intent_decider' for n in calls) == 1
    tree = ast.parse(inspect.getsource(observability))
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {'assess', 'decide', 'resolve', 'execute', 'remediate', 'verify', 'authorize'}


def test_nonunit_risk_and_repetitions_survive_reload(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    for count in (1, 2):
        current = coordinator.store.get_investigation(investigation.investigation_id)
        action = coordinator.planner.plan(current, 'tmux_pane_state')
        coordinator.budget_manager.consume(current, action, risk_cost=2)
        coordinator.investigation_manager.record_action(current.investigation_id, action,
                                                       consumed_budget=current.budget)
        saved = InvestigationStore(coordinator.store.root).get_investigation(current.investigation_id)
        assert saved.budget.consumed_actions == count
        assert saved.budget.consumed_risk == count * 2
        assert saved.budget.repeated_actions == {action.command.strip(): count}
    next_action = coordinator.planner.plan(saved, 'tmux_pane_state')
    assert coordinator.budget_manager.check(saved, next_action).reason == 'repetition_budget_exhausted'


def test_observer_failure_cannot_repeat_canonical_decisions(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    coordinator.decision_observer = Mock(side_effect=OSError('controlled failure'))
    coordinator.commander_intent_assessor.assess = Mock(wraps=coordinator.commander_intent_assessor.assess)
    diagnosis = Diagnosis('diagnosis', investigation.investigation_id, 'test', DiagnosisStatus.ESTABLISHED)
    coordinator._handoff_diagnosis(investigation, diagnosis)
    coordinator._handoff_diagnosis(investigation, diagnosis)
    assert incident.final_outcome == 'ESCALATED'
    coordinator.decision_observer.assert_called_once()
    coordinator.commander_intent_assessor.assess.assert_called_once()


def test_commander_journal_is_append_only_and_write_failure_is_passive(runtime, monkeypatch):
    writer = observability.LiveEvidenceObservability()
    writer.commander_decision({'investigation_id': 'first'})
    path = writer.root / 'commander_decisions.jsonl'
    original = path.read_bytes()
    writer.commander_decision({'investigation_id': 'second'})
    assert path.read_bytes().startswith(original)
    assert len(path.read_text().splitlines()) == 2
    monkeypatch.setattr(writer, '_prepare_directory', Mock(side_effect=OSError('unavailable')))
    writer.commander_decision({'investigation_id': 'unwritten'})
    assert len(path.read_text().splitlines()) == 2


def test_existing_overlimit_record_fails_closed_without_inventing_consumption(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    investigation.action_ids = [f'legacy-action-{index}' for index in range(56)]
    coordinator.store.save_investigation(investigation)
    coordinator.executor.execute = Mock(side_effect=AssertionError('budget exhausted'))
    for _ in range(3):
        coordinator.run_cycle()
    saved = coordinator.store.get_investigation(investigation.investigation_id)
    assert saved.state is InvestigationState.BUDGET_EXHAUSTED
    assert len(saved.action_ids) == 56
    assert saved.budget.consumed_actions == saved.budget.consumed_risk == 0
    coordinator.executor.execute.assert_not_called()


def test_budget_survives_coordinator_reconstruction(runtime):
    coordinator = runtime.diagnostic
    coordinator.config = RuntimeDiagnosticConfig(max_repeated_action=10)
    incident, investigation = register(runtime)
    coordinator.executor.execute = Mock(side_effect=fake_execute)
    coordinator.run_cycle()
    coordinator.run_cycle()

    # Re-registering with a fresh coordinator must reuse the durable budget.
    replacement = RuntimeDiagnosticCoordinator()
    recovered = replacement.register_incident(incident)
    assert recovered.investigation_id == investigation.investigation_id
    assert recovered.budget.consumed_actions == recovered.budget.consumed_risk == 2
    assert sum(recovered.budget.repeated_actions.values()) == 2
    replacement.executor.execute = Mock(side_effect=fake_execute)
    for _ in range(56):
        replacement.run_cycle()
    saved = replacement.store.get_investigation(investigation.investigation_id)
    assert saved.state is InvestigationState.BUDGET_EXHAUSTED
    assert len(saved.action_ids) == saved.budget.consumed_actions == 5
    assert saved.budget.consumed_risk == 5
    assert sum(saved.budget.repeated_actions.values()) == 5
    assert coordinator.executor.execute.call_count == 2
    assert replacement.executor.execute.call_count == 3


def test_component_lookup_cannot_substitute_for_diagnostic_lookup(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    coordinator.incident_lookup = runtime.incident_manager.get_active_incident
    coordinator.commander_intent_assessor.assess = Mock()
    diagnosis = Diagnosis('diagnosis', investigation.investigation_id,
                          'controlled', DiagnosisStatus.ESTABLISHED)
    with pytest.raises(RuntimeError, match='incident not found'):
        coordinator._handoff_diagnosis(investigation, diagnosis)
    coordinator.commander_intent_assessor.assess.assert_not_called()
    assert runtime.incident_manager.get_active_incident(incident.component_id) is incident
