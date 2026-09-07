"""Phase 2.13C findings, not live-safety certification or repair tests.

All effect tokens stay in memory; all evidence uses pytest temporary storage.
Characterization assertions must change when the separately approved repairs land.
"""

from dataclasses import fields
import os
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sentinel.execution import ExecutionResult
from sentinel.remediation_action_catalog import RemediationActionEntry
from sentinel.remediation_policy import RemediationRequest
from sentinel.runtime import SentinelRuntime
from sentinel.tmux_remediation_verifier import TmuxRemediationVerifier, TmuxVerificationTarget


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    for name in ("DIAGNOSTIC", "EXECUTION_IDENTITY", "RUNTIME"):
        monkeypatch.setenv(f"AIRIV_SENTINEL_{name}_DIR", str(tmp_path / name))
    forbidden = Mock(side_effect=AssertionError("Phase 2.13C forbids host effects"))
    for owner, names in ((subprocess, ("Popen", "run")),
                         (os, ("system", "popen")),
                         (socket, ("socket", "create_connection"))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    instance = SentinelRuntime()
    yield instance
    fresh = SentinelRuntime()
    assert fresh.diagnostic.commander_semantic_policy.list_triggers() == ()
    assert fresh.remediation_action_catalog.list_actions() == ()
    assert fresh.remediation_action_catalog.list_triggers() == ()
    assert fresh.policy.allowed_actions == set()
    forbidden.assert_not_called()


def test_fresh_defaults_disabled_and_legacy_action_allowance_removed(runtime):
    assert runtime.diagnostic.commander_semantic_policy.list_triggers() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()
    assert runtime.policy.allowed_actions == set()
    assert runtime.commander.remediation_orchestrator.verifier is None


def test_blocker_authorized_action_does_not_bind_command_or_incident(runtime, monkeypatch):
    catalog = runtime.remediation_action_catalog
    catalog.register(RemediationActionEntry("design_probe", "EXPECTED_TOKEN", "inert"))
    runtime.policy.allowed_actions = {"design_probe"}
    decision = runtime.policy.evaluate(RemediationRequest("OPEN", "%0", "design_probe"))
    orchestrator = runtime.commander.remediation_orchestrator
    seen = []

    def inert_effect(command):
        record = orchestrator.identity_boundary.journal.get("design-probe")
        assert record.state == "RUNNING"  # durable before the mocked effect
        seen.append(command)
        return ExecutionResult(command, "", "", 0, 1.0, 2.0)

    monkeypatch.setattr(runtime.execution, "execute", inert_effect)
    kwargs = dict(incident_state="OPEN", component_id="%0", action="design_probe",
                  command="SUBSTITUTED_TOKEN", execution_id="design-probe",
                  incident_id="not-bound-by-decision", authorized_decision=decision)
    result = orchestrator.handle(**kwargs)
    assert result.execution.command != catalog.get("design_probe").command
    assert seen == ["SUBSTITUTED_TOKEN"]
    replay = orchestrator.handle(**dict(kwargs, command="ANOTHER_TOKEN"))
    assert replay.replayed and replay.verification is None
    assert replay.execution == result.execution
    assert seen == ["SUBSTITUTED_TOKEN"]


def test_production_policy_default_denies_controlled_and_unrelated_components(runtime):
    controlled = runtime.policy.evaluate(RemediationRequest("OPEN", "%controlled", "restart_test"))
    unrelated = runtime.policy.evaluate(RemediationRequest("OPEN", "%unrelated", "restart_test"))
    assert controlled.decision.value == unrelated.decision.value == "DENY"
    # Resource-scoped authorization is still a later Phase 2.13C.1B repair.
    assert {f.name for f in fields(RemediationRequest)} == {"incident_state", "component_id", "action"}


def test_investigation_observation_preserves_session_identity(runtime):
    incident = runtime.incident_manager.evaluate_anomaly(
        observation=dict(source="TMUX", pane_id="%design", pane_dead=True,
                         session_name="airiv-validation-inert", window_index=0),
        anomaly_type="PANE_DEAD", reason="inert design observation")
    investigation = runtime.diagnostic.register_incident(incident)
    saved = runtime.diagnostic.store.get_investigation(investigation.investigation_id)
    observations = [runtime.diagnostic.store.get_observation(saved.investigation_id, oid)
                    for oid in saved.observation_ids]
    assert observations
    assert all(o.value == dict(pane_id="%design", pane_dead=True) for o in observations)
    assert all(
        o.raw_evidence.get("session_name") == "airiv-validation-inert"
        for o in observations
    )


def test_blocker_verifier_accepts_alive_pane_without_session_proof(monkeypatch):
    # A mock live pane can belong to any session or server generation. No real
    # TMUX process is invoked and no ExecutionResult is supplied to verification.
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="0\n", stderr=""))
    monkeypatch.setattr("sentinel.tmux_remediation_verifier.subprocess.run", run)
    verifier = TmuxRemediationVerifier(TmuxVerificationTarget("%0"))
    assert verifier.verify().verified
    assert run.call_args.args[0] == ["tmux", "display-message", "-p", "-t", "%0", "#{pane_dead}"]
    assert run.call_args.kwargs["timeout"] == 5.0
    run.return_value.stdout = "1\n"
    assert not verifier.verify().verified
