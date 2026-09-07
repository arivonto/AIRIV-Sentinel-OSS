"""Phase 2.13A: real canonical authorities with inert test-only execution."""

import ast
import inspect
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sentinel.commander_semantic_policy import CommanderSemanticRule
from sentinel.diagnostic.models import DiagnosisStatus
from sentinel.final_outcome_mapper import FinalOutcomeMapper
from sentinel.incidents.manager import Incident
from sentinel.remediation_action_catalog import RemediationActionEntry
from sentinel.remediation_execution_identity import RemediationExecutionIdentityJournal
from sentinel.remediation_verifier import RemediationVerifier
from sentinel.runtime import SentinelRuntime
from test_remediation_execution_identity_concurrency_audit_v4 import CountingExecutor


TRIGGER = "TEST_ONLY_CONTROLLED_REMEDIATION_213A"
ACTION = "test_only_record_213a"
COMMAND = "TEST_ONLY_INERT_TOKEN_213A"


@pytest.fixture
def harness(tmp_path, monkeypatch):
    for suffix in ("DIAGNOSTIC", "EXECUTION_IDENTITY", "RUNTIME"):
        monkeypatch.setenv(f"AIRIV_SENTINEL_{suffix}_DIR", str(tmp_path / suffix))
    forbidden = Mock(side_effect=AssertionError("external operation forbidden"))
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    runtime = SentinelRuntime()
    coordinator = runtime.diagnostic
    manager = runtime.incident_manager
    events = []
    spies = {}

    def observe(name, owner, method):
        original = getattr(owner, method)

        def call(*args, **kwargs):
            events.append(name)
            return original(*args, **kwargs)

        spy = Mock(side_effect=call)
        monkeypatch.setattr(owner, method, spy)
        spies[name] = spy

    observe("semantic", coordinator.commander_semantic_policy, "assess")
    observe("assessment", coordinator.commander_intent_assessor, "assess")
    observe("intent", coordinator.commander_intent_decider, "decide")
    observe("policy", runtime.policy, "evaluate")
    observe("map", FinalOutcomeMapper, "map")
    observe("diagnosis", coordinator.diagnosis_evaluator, "evaluate")
    observe("finalize", runtime.commander.remediation_flow, "finalize")

    # Fail any lifecycle assignment outside the real resolve call, including
    # direct assignment that would evade an update_status spy.
    resolving = False
    original_setattr = Incident.__setattr__

    def guarded_setattr(self, name, value):
        if name in {"status", "lifecycle_state", "final_outcome"} and hasattr(self, name):
            assert resolving, f"lifecycle mutation outside resolve: {name}"
        original_setattr(self, name, value)

    monkeypatch.setattr(Incident, "__setattr__", guarded_setattr)
    original_resolve = manager.resolve

    def resolve(*args, **kwargs):
        nonlocal resolving
        events.append("resolve")
        assert events[-2] == "map"
        resolving = True
        try:
            return original_resolve(*args, **kwargs)
        finally:
            resolving = False

    spies["resolve"] = Mock(side_effect=resolve)
    monkeypatch.setattr(manager, "resolve", spies["resolve"])

    adapter = CountingExecutor(delay=0)

    def execute(command):
        assert command == COMMAND
        events.append("execution")
        return adapter.execute(command)

    spies["execution"] = Mock(side_effect=execute)
    monkeypatch.setattr(runtime.execution, "execute", spies["execution"])
    monkeypatch.setattr(coordinator.executor, "execute", forbidden)
    # Construction has finished: reject any second authority during processing.
    for owner in (type(runtime), type(manager), type(runtime.commander), type(coordinator)):
        monkeypatch.setattr(owner, "__init__", forbidden)
    yield SimpleNamespace(runtime=runtime, coordinator=coordinator, manager=manager,
                          events=events, spies=spies, adapter=adapter,
                          monkeypatch=monkeypatch, tmp_path=tmp_path)
    forbidden.assert_not_called()


def configure(h, *, semantic=True, allow=True, action=True, success=True, verified=True):
    if semantic:
        h.coordinator.commander_semantic_policy.register(
            CommanderSemanticRule(TRIGGER, True, False, "test-only controlled semantics"))
    h.runtime.policy.allowed_actions = {ACTION} if allow else set()
    if action:
        h.runtime.remediation_action_catalog.register(
            RemediationActionEntry(ACTION, COMMAND, "test-only recording adapter"),
            trigger=TRIGGER)
    h.adapter.fail = not success
    verification = Mock()
    if verified is not None:
        def independent_observation():
            assert h.adapter.count == 1 and not h.adapter.fail
            h.events.append("verification")
            return verified
        verifier = RemediationVerifier(independent_observation)
        verification = Mock(wraps=verifier.verify)
        h.monkeypatch.setattr(verifier, "verify", verification)
        h.runtime.commander.remediation_orchestrator.verifier = verifier
    h.spies["verification"] = verification


def diagnose(h):
    incident = h.manager.evaluate_anomaly(
        observation={"source": "TMUX", "pane_id": "%213a", "pane_dead": True},
        anomaly_type=TRIGGER, reason="synthetic observation; no live stimulus")
    investigation = h.coordinator.register_incident(incident)
    result = h.coordinator.engine.step(investigation.investigation_id)
    assert result.diagnosis.status is DiagnosisStatus.ESTABLISHED
    saved = h.coordinator.store.get_investigation(investigation.investigation_id)
    assert saved.diagnosis_id == result.diagnosis.diagnosis_id
    assert len(saved.current_hypothesis_ids) == 1
    assert saved.observation_ids and saved.evidence_ids
    return incident, result


@pytest.mark.parametrize("semantic,allow,success,verified,outcome", [
    pytest.param(False, True, True, True, "ESCALATED", id="A-unconfigured"),
    pytest.param(True, False, True, True, "ESCALATED", id="B-denied"),
    pytest.param(True, True, False, True, "UNRESOLVED", id="D-execution-failed"),
    pytest.param(True, True, True, None, "UNRESOLVED", id="E-verification-missing"),
    pytest.param(True, True, True, False, "UNRESOLVED", id="F-verification-failed"),
    pytest.param(True, True, True, True, "RECOVERED", id="G-verified"),
])
def test_canonical_matrix_and_completed_handoff_replay(harness, semantic, allow,
                                                      success, verified, outcome):
    h = harness
    configure(h, semantic=semantic, allow=allow, success=success, verified=verified)
    incident, result = diagnose(h)
    for _ in range(3):
        h.coordinator._handoff_diagnosis(result.investigation, result.diagnosis)
    assert h.coordinator.run_cycle() == []
    executed = int(semantic and allow)
    verified_count = int(bool(executed and success and verified is not None))
    expected = dict(semantic=1, assessment=1, intent=1, policy=int(semantic),
                    execution=executed, verification=verified_count, map=1,
                    resolve=1, diagnosis=1, finalize=executed)
    assert {name: spy.call_count for name, spy in h.spies.items()} == expected
    assert incident.final_outcome == outcome and incident.status == "TERMINAL"
    assert h.manager.get_active_incident(incident.component_id) is None
    snapshot, = h.manager.get_history()
    assert snapshot["final_outcome"] == outcome
    facts = h.spies["map"].call_args.kwargs
    assert facts["intent"].value == ("AUTONOMOUS_REMEDIATE" if semantic else "NEED_COMMANDER")
    assert h.events.index("semantic") < h.events.index("intent") < h.events.index("map")
    if semantic:
        assert h.events.index("intent") < h.events.index("policy")
    records = list((h.tmp_path / "EXECUTION_IDENTITY").glob("*/record.json"))
    assert len(records) == executed
    if not executed:
        assert not any(e["signal_type"].startswith("REMEDIATION_") for e in incident.evidence_trail)
        return
    assert h.events.index("policy") < h.events.index("execution") < h.events.index("map")
    orchestration = h.spies["finalize"].call_args.args[1]
    execution_id = orchestration.execution_id
    assert execution_id
    journal = RemediationExecutionIdentityJournal(h.tmp_path / "EXECUTION_IDENTITY")
    record = journal.get(execution_id)
    assert (record.incident_id, record.component_id, record.action, record.command) == (
        incident.incident_id, incident.component_id, ACTION, COMMAND)
    assert record.execution["success"] is success
    assert record.state == ("SUCCEEDED" if success else "FAILED")
    signal, = [e["signal_snapshot"] for e in snapshot["evidence_trail"]
               if e["signal_type"].startswith("REMEDIATION_")]
    assert signal["execution_id"] == record.execution_id
    assert signal["execution"]["exit_code"] == (0 if success else 1)
    if verified_count:
        assert h.events.index("execution") < h.events.index("verification") < h.events.index("map")
        assert signal["verification"]["verified"] is verified
    else:
        assert "verification" not in signal


def test_C_missing_action_fails_before_policy_and_identity(harness):
    h = harness
    configure(h, action=False)
    incident, result = diagnose(h)
    with pytest.raises(KeyError, match="no remediation action registered"):
        h.coordinator._handoff_diagnosis(result.investigation, result.diagnosis)
    assert h.spies["semantic"].call_count == h.spies["assessment"].call_count == 1
    for name in ("intent", "policy", "execution", "verification", "map", "resolve", "finalize"):
        h.spies[name].assert_not_called()
    assert incident.final_outcome is None and incident.status == "OPEN"
    assert h.manager.get_active_incident(incident.component_id) is incident
    assert list((h.tmp_path / "EXECUTION_IDENTITY").iterdir()) == []


@pytest.mark.parametrize("success", [False, True])
def test_H_consumed_identity_replay_does_not_execute_or_verify(harness, success):
    h = harness
    configure(h, success=success)
    incident, result = diagnose(h)
    h.coordinator._handoff_diagnosis(result.investigation, result.diagnosis)
    original = h.spies["finalize"].call_args.args[1]
    orchestrator = h.runtime.commander.remediation_orchestrator
    # Reuse the canonical authorized facts and identity, including original state.
    replay = orchestrator.handle(
        incident_state=original.decision.incident_state, component_id=incident.component_id,
        incident_id=incident.incident_id, action=ACTION, command=COMMAND,
        execution_id=original.execution_id, authorized_decision=original.decision)
    assert replay.replayed and replay.execution_id == original.execution_id
    assert replay.identity_record == original.identity_record
    assert replay.verification is None
    assert h.adapter.count == h.spies["execution"].call_count == 1
    assert h.spies["verification"].call_count == int(success)
    assert h.spies["policy"].call_count == h.spies["map"].call_count == h.spies["resolve"].call_count == 1


def test_production_defaults_and_shared_authorities(harness):
    h = harness
    from sentinel.worker import composition, entrypoint, observability
    h.monkeypatch.setattr(observability, "REPOSITORY_ROOT", h.tmp_path)
    bundle = composition.build_production_supervision(h.runtime, entrypoint.build_production_config())
    assert bundle.runtime is bundle.runtime_worker.runtime is bundle.capability_worker.runtime is h.runtime
    assert h.coordinator.commander_semantic_policy.list_triggers() == ()
    assert h.runtime.remediation_action_catalog.list_actions() == ()
    assert h.runtime.remediation_action_catalog.list_triggers() == ()
    assert ACTION not in h.runtime.policy.allowed_actions
    facts = h.coordinator.commander_semantic_policy.assess(TRIGGER)
    assert (facts.configured, facts.remediation_required, facts.commander_action_required) == (False, False, True)
    assert h.coordinator.incident_manager is h.runtime.commander.incident_manager is h.manager
    assert h.coordinator.commander_handoff.commander is h.runtime.commander
    assert h.coordinator.incident_lookup.__self__ is h.manager
    assert h.runtime.commander.execution is h.runtime.execution
    assert h.coordinator.remediation_action_catalog is h.runtime.remediation_action_catalog


def test_configuration_is_instance_local_and_does_not_leak(harness):
    from sentinel.commander_semantic_policy import CommanderSemanticPolicy
    from sentinel.remediation_action_catalog import RemediationActionCatalog
    configure(harness)
    assert harness.coordinator.commander_semantic_policy.list_triggers() == (TRIGGER,)
    assert harness.runtime.remediation_action_catalog.list_actions() == (ACTION,)
    assert CommanderSemanticPolicy().list_triggers() == ()
    assert RemediationActionCatalog().list_actions() == ()
    assert CommanderSemanticPolicy().assess(TRIGGER).commander_action_required is True


def test_structural_composition_and_inert_adapter():
    import sentinel.runtime as runtime_module
    tree = ast.parse(inspect.getsource(runtime_module))
    calls = [n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    for name in ("IncidentManager", "CommanderOrchestrator", "RuntimeDiagnosticCoordinator", "SentinelRuntime"):
        assert calls.count(name) == 1
    # Reused adapter has no shell, subprocess, network, privileged or lifecycle calls.
    tree = ast.parse(inspect.getsource(CountingExecutor))
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert calls <= {"Lock", "sleep", "time"}
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))


def test_canonical_source_authorities_and_no_production_registration():
    root = Path(__file__).resolve().parents[1] / "sentinel"
    authorities = {name: [] for name in (
        "IncidentManager", "CommanderOrchestrator", "RuntimeDiagnosticCoordinator", "SentinelRuntime")}
    # Exact .py suffix excludes historical .pre_/.bak/backup files and caches.
    for path in root.rglob("*.py"):
        source = path.read_text()
        assert TRIGGER not in source and ACTION not in source and COMMAND not in source
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name in authorities:
                authorities[node.name].append(path)
    assert all(len(paths) == 1 for paths in authorities.values())
    for relative in ("runtime.py", "diagnostic/runtime_coordinator.py", "worker/composition.py"):
        tree = ast.parse((root / relative).read_text())
        # Composition may register workers, but cannot install remediation entries/rules.
        constructors = {n.func.id for n in ast.walk(tree)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert not constructors & {"CommanderSemanticRule", "RemediationActionEntry"}
    for relative in ("commander.py", "remediation_orchestrator.py", "remediation_gate.py",
                     "remediation_evidence_flow.py", "diagnostic/commander_handoff.py",
                     "diagnostic/runtime_coordinator.py", "final_outcome_mapper.py"):
        tree = ast.parse((root / relative).read_text())
        mutations = {n.attr for n in ast.walk(tree)
                     if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)}
        assert not mutations & {"status", "lifecycle_state", "final_outcome"}
