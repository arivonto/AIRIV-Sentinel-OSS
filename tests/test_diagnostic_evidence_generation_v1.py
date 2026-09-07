"""Phase 2.12B canonical persisted evidence and authority regressions."""
import ast
import inspect
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from sentinel.diagnostic import hypothesis_generator
from sentinel.diagnostic.evaluator import DiagnosisEvaluator
from sentinel.diagnostic.hypothesis import HypothesisManager
from sentinel.diagnostic.investigation import InvestigationManager
from sentinel.diagnostic.models import Hypothesis, HypothesisStatus, InvestigationState
from sentinel.diagnostic.runtime_coordinator import RuntimeDiagnosticConfig
from sentinel.diagnostic.store import InvestigationStore
from sentinel.runtime import SentinelRuntime
from test_diagnostic_path_repair_v1 import fake_execute


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv('AIRIV_SENTINEL_DIAGNOSTIC_DIR', str(tmp_path / 'diagnostic'))
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
        monkeypatch.delenv(key, raising=False)
    return SentinelRuntime()


def register(runtime, facts=None):
    incident = runtime.incident_manager.evaluate_anomaly(
        observation=facts or {'source': 'TMUX', 'pane_id': '%exact', 'pane_dead': True},
        anomaly_type='UNKNOWN_DEAD_PANE', reason='fixture')
    return incident, runtime.diagnostic.register_incident(incident)


def test_persisted_tmux_provenance_and_loader(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    candidate, = coordinator.engine.hypothesis_generator.generate(investigation)
    original, = incident.get_evidence_records()
    assert candidate.supporting_evidence_ids == [original.evidence_id]
    assert candidate.investigation_id == investigation.investigation_id
    observation = coordinator.store.get_observation(investigation.investigation_id, original.evidence_id)
    assert observation.component_id == investigation.component_id == incident.component_id == '%exact'
    assert observation.value == {'pane_id': '%exact', 'pane_dead': True}
    assert observation.raw_evidence == {
        "source": "TMUX",
        "pane_id": "%exact",
        "pane_dead": True,
    }
    assert candidate.created_at == observation.observed_at
    coordinator.investigation_manager.record_hypothesis(investigation.investigation_id, candidate)
    store = InvestigationStore(coordinator.store.root)
    manager = HypothesisManager(InvestigationManager(store))
    assert manager.get(investigation.investigation_id, candidate.hypothesis_id) == candidate
    assert manager.get(investigation.investigation_id, 'missing') is None
    candidate.contradicting_evidence_ids = ['other-reference']
    store.save_hypothesis(candidate)
    assert store.get_hypothesis(investigation.investigation_id, candidate.hypothesis_id) == candidate
    assert store.get_hypothesis('missing', 'missing') is None


@pytest.mark.parametrize('facts', [
    {'pane_id': '%exact'},
    {'source': 'OTHER', 'pane_id': '%exact', 'pane_dead': True},
    {'source': 'TMUX', 'pane_id': '%exact', 'capture_ok': False},
    {'source': 'TMUX', 'pane_id': '%exact', 'current_command': 'bash', 'first_observation': True},
    *[{'source': 'TMUX', 'pane_id': '%exact', 'pane_dead': value}
      for value in (False, None, 'true', 1)],
])
def test_unsupported_facts(runtime, facts):
    _, investigation = register(runtime, facts)
    assert runtime.diagnostic.engine.hypothesis_generator.generate(investigation) == []


def test_missing_and_foreign_persisted_evidence(runtime):
    _, investigation = register(runtime)
    generator = runtime.diagnostic.engine.hypothesis_generator
    assert generator.generate(replace(investigation, observation_ids=[])) == []
    assert generator.generate(replace(investigation, evidence_ids=[])) == []
    reference, = investigation.observation_ids
    observation = runtime.diagnostic.store.get_observation(investigation.investigation_id, reference)
    for changes in ({'component_id': '%other'}, {'source': 'OTHER'}, {'value': {}},
                    {'value': 'unstructured'}, {'observation_id': 'different'}):
        # Write mismatching contents at the registered path to exercise validation.
        from sentinel.diagnostic.store import _write_atomic
        path = runtime.diagnostic.store.root / 'investigations' / investigation.investigation_id / 'observations' / f'{reference}.json'
        _write_atomic(path, asdict(replace(observation, **changes)))
        assert generator.generate(investigation) == []


def test_deterministic_duplicate_facts_and_mixed_liveness(runtime):
    incident, investigation = register(runtime)
    generator = runtime.diagnostic.engine.hypothesis_generator
    first = generator.generate(investigation)
    for _ in range(4):
        incident.add_evidence({'source': 'TMUX', 'pane_id': '%exact', 'pane_dead': True}, 'repeat')
        investigation = runtime.diagnostic.register_incident(incident)
        assert generator.generate(investigation) == first
    incident.add_evidence({'source': 'TMUX', 'pane_id': '%exact', 'pane_dead': False}, 'changed')
    investigation = runtime.diagnostic.register_incident(incident)
    assert generator.generate(investigation) == []


def test_real_evaluator_and_safe_existing_commander_path(runtime):
    incident, investigation = register(runtime)
    coordinator = runtime.diagnostic
    evaluator = coordinator.diagnosis_evaluator
    evaluator.evaluate = Mock(wraps=evaluator.evaluate)
    coordinator.commander_semantic_policy.assess = Mock(wraps=coordinator.commander_semantic_policy.assess)
    coordinator.commander_intent_decider.decide = Mock(wraps=coordinator.commander_intent_decider.decide)
    coordinator.executor.execute = Mock(side_effect=AssertionError('unneeded action'))
    runtime.execution.execute = Mock(side_effect=AssertionError('no remediation'))
    for _ in range(5):
        coordinator.run_cycle()
    saved = coordinator.store.get_investigation(investigation.investigation_id)
    assert saved.state is InvestigationState.COMPLETED
    assert saved.diagnosis_id
    assert len(saved.current_hypothesis_ids) == 1
    evaluator.evaluate.assert_called_once()
    coordinator.commander_semantic_policy.assess.assert_called_once()
    coordinator.commander_intent_decider.decide.assert_called_once()
    assert incident.final_outcome == 'ESCALATED'
    assert coordinator.commander_semantic_policy.list_triggers() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    # Inspect the real policy result independently without another runtime decision.
    from sentinel.commander_semantic_policy import CommanderSemanticPolicy
    facts = CommanderSemanticPolicy().assess(incident.anomaly_type)
    assert (facts.configured, facts.remediation_required, facts.commander_action_required,
            facts.reason) == (False, False, True, 'semantic_policy_unconfigured')
    coordinator.executor.execute.assert_not_called()
    runtime.execution.execute.assert_not_called()
    assert coordinator.incident_manager is runtime.incident_manager is runtime.commander.incident_manager


def test_threshold_unchanged_and_budget_reload(runtime):
    coordinator = runtime.diagnostic
    coordinator.config = RuntimeDiagnosticConfig(minimum_evidence=100, max_actions=3,
                                                max_repeated_action=10)
    _, investigation = register(runtime)
    candidate, = coordinator.engine.hypothesis_generator.generate(investigation)
    diagnosis = DiagnosisEvaluator().evaluate(investigation, [candidate])
    assert diagnosis.confidence_basis == ['minimum_evidence_not_met']
    coordinator.executor.execute = Mock(side_effect=fake_execute)
    for _ in range(10):
        coordinator.engine.step(investigation.investigation_id)
    saved = InvestigationStore(coordinator.store.root).get_investigation(investigation.investigation_id)
    assert saved.state is InvestigationState.BUDGET_EXHAUSTED
    assert len(saved.current_hypothesis_ids) == 1
    assert len(saved.action_ids) == saved.budget.consumed_actions == saved.budget.consumed_risk == 3
    assert sum(saved.budget.repeated_actions.values()) == 3
    assert saved.diagnosis_id is None
    assert coordinator.engine.hypothesis_generator.generate(saved) == []
    coordinator.executor.execute.assert_called()
    assert coordinator.executor.execute.call_count == 3


def test_exhausted_active_never_generates(runtime):
    _, investigation = register(runtime)
    investigation.budget.consumed_actions = investigation.budget.max_actions
    runtime.diagnostic.store.save_investigation(investigation)
    runtime.diagnostic.executor.execute = Mock(side_effect=AssertionError('exhausted'))
    result = runtime.diagnostic.engine.step(investigation.investigation_id)
    assert result.investigation.state is InvestigationState.BUDGET_EXHAUSTED
    assert result.investigation.current_hypothesis_ids == []


def test_generator_structural_authority_and_dependencies():
    tree = ast.parse(inspect.getsource(hypothesis_generator))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {'hashlib', 'models', 'store'}
    assert {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names} == {'json'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
             for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls & {'Diagnosis', 'DiagnosisEvaluator', 'evaluate', 'assess', 'decide',
                        'execute', 'resolve', 'authorize', 'verify', 'remediate',
                        'IncidentManager', 'CommanderOrchestrator',
                        'RuntimeDiagnosticCoordinator', 'SentinelRuntime'}


def test_headless_normalized_sensor_to_diagnosis_without_external_operations(runtime, monkeypatch):
    import socket
    import subprocess
    runtime.running = True
    runtime.sensor_adapter.parser.inspect_panes = Mock(return_value=[{
        'source': 'TMUX', 'pane_id': '%exact', 'pane_dead': True,
        'capture_ok': False, 'current_command': 'bash', 'first_observation': True,
    }])
    forbidden = Mock(side_effect=AssertionError('external operation or duplicate owner'))
    for owner in (type(runtime), type(runtime.incident_manager),
                  type(runtime.commander), type(runtime.diagnostic)):
        monkeypatch.setattr(owner, '__init__', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    incidents = runtime.run_once()
    runtime.diagnostic.run_cycle()
    investigation, = runtime.diagnostic.store.recover()
    assert investigation.diagnosis_id is not None
    assert investigation.component_id == '%exact'
    assert investigation.incident_id == incidents[0].incident_id
    assert incidents[0].final_outcome == 'ESCALATED'
    forbidden.assert_not_called()


def test_no_evidence_does_not_invoke_evaluator(runtime):
    _, investigation = register(runtime, {'pane_id': '%exact'})
    coordinator = runtime.diagnostic
    coordinator.diagnosis_evaluator.evaluate = Mock(side_effect=AssertionError('no hypotheses'))
    coordinator.executor.execute = Mock(side_effect=fake_execute)
    coordinator.engine.step(investigation.investigation_id)
    saved = coordinator.store.get_investigation(investigation.investigation_id)
    assert saved.current_hypothesis_ids == []
    assert saved.diagnosis_id is None
    coordinator.diagnosis_evaluator.evaluate.assert_not_called()


def test_legacy_payload_only_observation_is_not_provenance(runtime):
    _, investigation = register(runtime)
    reference, = investigation.observation_ids
    store = runtime.diagnostic.store
    path = store.root / 'investigations' / investigation.investigation_id / 'observations' / f'{reference}.json'
    path.write_text('{"pane_dead": true}')
    assert store.get_observation(investigation.investigation_id, reference) is None
    assert runtime.diagnostic.engine.hypothesis_generator.generate(investigation) == []
