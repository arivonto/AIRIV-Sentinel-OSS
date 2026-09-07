"""Phase 2.13B: production orchestration, test-local external effects only.

Missing action is the explicit pre-policy error in
contracts/CONTROLLED_REMEDIATION_SAFETY_CONTRACT.md, not ALLOW with missing
execution. No authorization or terminal outcome is fabricated for that case.
"""

import ast
from dataclasses import FrozenInstanceError
import inspect
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import sentinel.execution as execution_module
from sentinel.commander_intent_assessment import CommanderIntentAssessment
from sentinel.commander_semantic_policy import CommanderSemanticRule
from sentinel.diagnostic.models import DiagnosisStatus
from sentinel.execution import ExecutionBoundary
from sentinel.final_outcome_mapper import FinalOutcomeMapper
from sentinel.incidents.manager import Incident
from sentinel.remediation_action_catalog import RemediationActionEntry
from sentinel.remediation_execution_identity import RemediationExecutionIdentityJournal
from sentinel.remediation_verifier import RemediationVerifier
from sentinel.runtime import SentinelRuntime


TRIGGER = "PHASE_213B_CONTROLLED_REMEDIATION"
ACTION = "phase_213b_inert_action"
TOKEN = "PHASE_213B_INERT_TOKEN"


class InProcessEffect:
    """Process-backend signature, with no process or other external operation."""

    def __init__(self):
        self.commands = []
        self.success = True

    def run(self, command, **options):
        assert command == TOKEN
        assert options == dict(shell=True, capture_output=True, text=True, check=False)
        self.commands.append(command)
        return SimpleNamespace(stdout="recorded", stderr="" if self.success else "controlled failure",
                               returncode=0 if self.success else 1)


@pytest.fixture
def integration(tmp_path, monkeypatch):
    for suffix in ("DIAGNOSTIC", "EXECUTION_IDENTITY", "RUNTIME"):
        monkeypatch.setenv(f"AIRIV_SENTINEL_{suffix}_DIR", str(tmp_path / suffix))
    forbidden = Mock(side_effect=AssertionError("external operation forbidden"))
    for owner, names in ((subprocess, ("Popen", "run")),
                         (socket, ("socket", "create_connection")),
                         (os, ("system", "popen"))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)

    runtime = SentinelRuntime()
    coordinator = runtime.diagnostic
    manager = runtime.incident_manager
    events, spies, results = [], {}, {}
    effect = InProcessEffect()

    def observe(name, owner, method):
        original = getattr(owner, method)

        def call(*args, **kwargs):
            result = original(*args, **kwargs)
            # Completion records semantic facts before the assessment DTO is
            # returned by the assessor (the DTO itself has no assess method).
            events.append(name)
            results[name] = result
            return result

        spy = Mock(side_effect=call)
        monkeypatch.setattr(owner, method, spy)
        spies[name] = spy

    observe("hypothesis", coordinator.engine.hypothesis_generator, "generate")
    observe("diagnosis", coordinator.diagnosis_evaluator, "evaluate")
    observe("semantic", coordinator.commander_semantic_policy, "assess")
    observe("assessment", coordinator.commander_intent_assessor, "assess")
    observe("intent", coordinator.commander_intent_decider, "decide")
    observe("policy", runtime.policy, "evaluate")
    observe("map", FinalOutcomeMapper, "map")
    observe("finalize", runtime.commander.remediation_flow, "finalize")
    orchestrator = runtime.commander.remediation_orchestrator
    observe("claim", orchestrator.identity_boundary.journal, "claim")

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
        assert events[-1] == "map"
        assert kwargs["final_outcome"] == results["map"]
        assert manager.get_active_incident(kwargs["component_id"]).final_outcome is None
        resolving = True
        try:
            result = original_resolve(*args, **kwargs)
        finally:
            resolving = False
        events.append("resolve")
        return result

    spies["resolve"] = Mock(side_effect=resolve)
    monkeypatch.setattr(manager, "resolve", spies["resolve"])

    original_execute = runtime.execution.execute

    def execute(command):
        assert events[-1] == "claim"
        record = results["claim"].record
        assert orchestrator.identity_boundary.journal.get(record.execution_id).state == "RUNNING"
        # Inject only around this test instance's real boundary invocation.
        # The module facade never calls subprocess; all real process APIs are
        # separately forbidden above. Production source remains untouched.
        with monkeypatch.context() as backend:
            backend.setattr(execution_module, "subprocess", effect)
            result = original_execute(command)
        events.append("execution")
        results["execution"] = result
        return result

    spies["execution"] = Mock(side_effect=execute)
    monkeypatch.setattr(runtime.execution, "execute", spies["execution"])
    monkeypatch.setattr(coordinator.executor, "execute", forbidden)
    monkeypatch.setattr(runtime.orchestrator, "handle", forbidden)
    monkeypatch.setattr(runtime.commander, "execute_system", forbidden)
    yield SimpleNamespace(runtime=runtime, coordinator=coordinator, manager=manager,
                          events=events, spies=spies, results=results, effect=effect,
                          observe=observe, tmp_path=tmp_path)
    # Explicit disposal followed by a new production composition, in the same
    # isolated evidence directories. The old instance's patches cannot leak.
    del runtime, coordinator, manager
    fresh = SentinelRuntime()
    assert fresh.diagnostic.commander_semantic_policy.list_triggers() == ()
    assert fresh.remediation_action_catalog.list_actions() == ()
    assert fresh.remediation_action_catalog.list_triggers() == ()
    assert ACTION not in fresh.policy.allowed_actions
    assert fresh.execution.execute.__func__ is ExecutionBoundary.execute
    forbidden.assert_not_called()


def configure(h, *, semantic, allow, action, success, verified):
    if semantic:
        h.coordinator.commander_semantic_policy.register(
            CommanderSemanticRule(TRIGGER, True, False, "isolated integration semantics"))
    if action:
        h.runtime.remediation_action_catalog.register(
            RemediationActionEntry(ACTION, TOKEN, "inert integration effect"), trigger=TRIGGER)
    h.runtime.policy.allowed_actions = {ACTION} if allow else set()
    h.effect.success = success
    h.spies["verification"] = Mock()
    if verified is not None:
        def independent_observation():
            assert h.effect.commands == [TOKEN]
            assert h.results["execution"].success
            assert h.events[-1] == "execution"
            identity = h.results["claim"].record
            saved = h.runtime.commander.remediation_orchestrator.identity_boundary.journal.get(
                identity.execution_id)
            assert saved.state == "SUCCEEDED"
            # This independent fixture input is deliberately unrelated to the
            # backend's success flag; success can verify either true or false.
            return verified

        verifier = RemediationVerifier(independent_observation)
        h.runtime.commander.remediation_orchestrator.verifier = verifier
        h.observe("verification", verifier, "verify")


def submit_observation(h):
    incident = h.manager.evaluate_anomaly(
        observation={"source": "TMUX", "pane_id": "%213b", "pane_dead": True},
        anomaly_type=TRIGGER, reason="in-process canonical observation")
    h.coordinator.submit([incident])
    return incident


@pytest.mark.parametrize("semantic,allow,action,success,verified,outcome", [
    pytest.param(False, True, True, True, True, "ESCALATED", id="1-unconfigured"),
    pytest.param(True, False, True, True, True, "ESCALATED", id="2-policy-deny"),
    pytest.param(True, True, False, True, True, None, id="3-action-unavailable"),
    pytest.param(True, True, True, False, True, "UNRESOLVED", id="4-execution-failure"),
    pytest.param(True, True, True, True, None, "UNRESOLVED", id="5-verification-missing"),
    pytest.param(True, True, True, True, False, "UNRESOLVED", id="6-verification-failure"),
    pytest.param(True, True, True, True, True, "RECOVERED", id="7-full-success"),
])
def test_complete_canonical_pipeline(integration, semantic, allow, action, success,
                                     verified, outcome, capsys):
    h = integration
    configure(h, semantic=semantic, allow=allow, action=action, success=success, verified=verified)
    incident = submit_observation(h)
    cycle = h.coordinator.run_cycle()
    investigation_id = h.coordinator._investigation_by_incident[incident.incident_id]
    saved = h.coordinator.store.get_investigation(investigation_id)
    diagnosis = h.results["diagnosis"]
    assert diagnosis.status is DiagnosisStatus.ESTABLISHED
    assert saved.diagnosis_id == diagnosis.diagnosis_id
    hypothesis, = h.results["hypothesis"]
    assert saved.current_hypothesis_ids == [hypothesis.hypothesis_id]
    assert hypothesis.supporting_evidence_ids
    assert set(hypothesis.supporting_evidence_ids) <= set(saved.evidence_ids)
    observation = h.coordinator.store.get_observation(
        investigation_id, hypothesis.supporting_evidence_ids[0])
    assert observation.component_id == incident.component_id
    assert observation.source == "TMUX" and observation.value["pane_dead"] is True
    assert isinstance(h.results["assessment"], CommanderIntentAssessment)
    assert h.results["assessment"].semantic_configured is semantic

    completed = int(outcome is not None)
    policy_count = int(semantic and action)
    executed = int(policy_count and allow)
    verification_count = int(executed and success and verified is not None)
    expected = dict(hypothesis=1, diagnosis=1, semantic=1, assessment=1,
                    intent=completed, policy=policy_count, claim=executed,
                    execution=executed, verification=verification_count,
                    finalize=executed, map=completed, resolve=completed)
    assert {name: spy.call_count for name, spy in h.spies.items()} == expected
    expected_order = ["hypothesis", "diagnosis", "semantic", "assessment"]
    if completed:
        expected_order += ["intent"]
    if policy_count:
        expected_order += ["policy"]
    if executed:
        expected_order += ["claim", "execution"]
    if verification_count:
        expected_order += ["verification"]
    if executed:
        expected_order += ["finalize"]
    if completed:
        expected_order += ["map", "resolve"]
    assert h.events == expected_order
    records = list((h.tmp_path / "EXECUTION_IDENTITY").glob("*/record.json"))
    assert len(records) == executed
    assert h.effect.commands == [TOKEN] * executed

    if not completed:
        assert cycle == []
        assert "no remediation action registered for trigger" in capsys.readouterr().out
        assert incident.status == "OPEN" and incident.final_outcome is None
        assert h.manager.get_active_incident(incident.component_id) is incident
        assert h.manager.get_history() == []
        assert not any(r.evidence_type.startswith("REMEDIATION_")
                       for r in incident.get_evidence_records())
        return

    assert len(cycle) == 1
    assert incident.status == incident.lifecycle_state == "TERMINAL"
    assert incident.final_outcome == outcome
    assert h.manager.get_active_incident(incident.component_id) is None
    assert h.manager.get_incident_by_id(incident.incident_id) is None
    snapshot, = h.manager.get_history()
    assert (snapshot["incident_id"], snapshot["component_id"], snapshot["final_outcome"]) == (
        incident.incident_id, incident.component_id, outcome)
    snapshot["final_outcome"] = "tampered copy"
    snapshot["evidence_trail"].clear()
    assert h.manager.get_history()[0] == incident.to_dict()
    facts = h.spies["map"].call_args.kwargs
    assert facts["intent"].value == ("AUTONOMOUS_REMEDIATE" if semantic else "NEED_COMMANDER")
    assert (facts["policy_decision"].value if policy_count else facts["policy_decision"]) == (
        ("ALLOW" if allow else "DENY") if policy_count else None)
    assert facts["execution_succeeded"] is (success if executed else None)
    assert facts["verification_succeeded"] is (verified if verification_count else None)
    for _ in range(3):
        h.coordinator._handoff_diagnosis(saved, diagnosis)
    assert h.coordinator.run_cycle() == []
    assert h.events == expected_order
    assert {name: spy.call_count for name, spy in h.spies.items()} == expected

    evidence = [r for r in incident.get_evidence_records()
                if r.evidence_type.startswith("REMEDIATION_")]
    assert len(evidence) == executed
    if not executed:
        return
    orchestration = h.spies["finalize"].call_args.args[1]
    journal = RemediationExecutionIdentityJournal(h.tmp_path / "EXECUTION_IDENTITY")
    record = journal.get(orchestration.execution_id)
    assert record == orchestration.identity_record
    assert (record.incident_id, record.component_id, record.action, record.command) == (
        incident.incident_id, incident.component_id, ACTION, TOKEN)
    assert record.state == ("SUCCEEDED" if success else "FAILED")
    assert record.execution["success"] is success
    assert record.execution["exit_code"] == (0 if success else 1)
    assert json.loads(records[0].read_text())["execution_id"] == record.execution_id
    item, = evidence
    assert (item.incident_id, item.component_id) == (record.incident_id, record.component_id)
    signal = item.signal_snapshot
    assert signal["execution_id"] == record.execution_id
    assert signal["execution"] == record.execution
    assert signal["action"] == ACTION
    if verification_count:
        assert orchestration.verification is h.results["verification"]
        assert orchestration.verification.observation is verified
        assert orchestration.verification.reason == (
            "post_remediation_state_verified" if verified
            else "post_remediation_state_not_verified")
        assert signal["verification"]["verified"] is verified
    else:
        assert orchestration.verification is None and "verification" not in signal
    history_signal, = [e["signal_snapshot"] for e in h.manager.get_history()[0]["evidence_trail"]
                      if e["signal_type"].startswith("REMEDIATION_")]
    assert history_signal == signal
    with pytest.raises(FrozenInstanceError):
        item.reason = "cannot rewrite evidence"

    persisted_before = records[0].read_bytes()
    replay = h.runtime.commander.remediation_orchestrator.handle(
        incident_state=orchestration.decision.incident_state,
        component_id=record.component_id, incident_id=record.incident_id,
        action=record.action, command=record.command, execution_id=record.execution_id,
        authorized_decision=orchestration.decision)
    assert replay.replayed and replay.identity_record == record
    assert replay.verification is None
    assert replay.execution == orchestration.execution
    assert records[0].read_bytes() == persisted_before
    assert list((h.tmp_path / "EXECUTION_IDENTITY").glob("*/record.json")) == records
    expected["claim"] += 1  # replay lookup, not a second identity or execution
    assert {name: spy.call_count for name, spy in h.spies.items()} == expected
    assert h.effect.commands == [TOKEN]


def test_structural_authorities_and_effect_safety():
    root = Path(__file__).resolve().parents[1] / "sentinel"
    authorities = {name: [] for name in ("IncidentManager", "CommanderOrchestrator",
                   "RuntimeDiagnosticCoordinator", "SentinelRuntime", "FinalOutcomeMapper")}
    for path in root.rglob("*.py"):
        source = path.read_text()
        assert all(identifier not in source for identifier in (TRIGGER, ACTION, TOKEN))
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name in authorities:
                authorities[node.name].append(str(path.relative_to(root)))
    assert all(len(paths) == 1 for paths in authorities.values()), authorities
    for relative in ("commander.py", "remediation_orchestrator.py", "remediation_gate.py",
                     "remediation_evidence_flow.py", "diagnostic/commander_handoff.py",
                     "diagnostic/runtime_coordinator.py", "diagnostic/hypothesis_generator.py",
                     "final_outcome_mapper.py"):
        tree = ast.parse((root / relative).read_text())
        stores = {n.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)}
        assert not stores & {"status", "lifecycle_state", "final_outcome"}
    generator = ast.parse((root / "diagnostic/hypothesis_generator.py").read_text())
    calls = {n.func.attr for n in ast.walk(generator)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"execute", "remediate", "evaluate", "resolve", "verify"}
    tree = ast.parse(inspect.getsource(InProcessEffect))
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert calls == {"append", "dict", "SimpleNamespace"}
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))


def test_real_shared_composition(integration):
    from sentinel.commander import CommanderOrchestrator
    from sentinel.diagnostic.engine import DiagnosticEngine
    from sentinel.diagnostic.evaluator import DiagnosisEvaluator
    from sentinel.diagnostic.hypothesis_generator import EvidenceHypothesisGenerator
    from sentinel.diagnostic.runtime_coordinator import RuntimeDiagnosticCoordinator
    from sentinel.incidents.manager import IncidentManager
    from sentinel.remediation_orchestrator import RemediationOrchestrator
    from sentinel.remediation_policy import RemediationPolicy

    h = integration
    assert type(h.runtime) is SentinelRuntime
    assert type(h.manager) is IncidentManager
    assert type(h.coordinator) is RuntimeDiagnosticCoordinator
    assert type(h.coordinator.engine) is DiagnosticEngine
    assert type(h.coordinator.engine.hypothesis_generator) is EvidenceHypothesisGenerator
    assert type(h.coordinator.diagnosis_evaluator) is DiagnosisEvaluator
    assert type(h.runtime.commander) is CommanderOrchestrator
    assert type(h.runtime.commander.remediation_orchestrator) is RemediationOrchestrator
    assert type(h.runtime.policy) is RemediationPolicy
    assert type(h.runtime.execution) is ExecutionBoundary
    assert h.coordinator.incident_manager is h.runtime.commander.incident_manager is h.manager
    assert h.coordinator.incident_lookup.__self__ is h.manager
    assert h.coordinator.commander_handoff.commander is h.runtime.commander
    assert h.coordinator.remediation_action_catalog is h.runtime.remediation_action_catalog
    orchestrator = h.runtime.commander.remediation_orchestrator
    assert orchestrator.policy is h.runtime.commander.remediation_policy is h.runtime.policy
    assert orchestrator.identity_boundary.gate is orchestrator.gate
    assert orchestrator.gate.executor is h.runtime.commander.execution is h.runtime.execution
