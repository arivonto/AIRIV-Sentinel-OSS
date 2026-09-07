from __future__ import annotations

from inspect import signature
from types import SimpleNamespace

import pytest

from sentinel.commander import CommanderOrchestrator
from sentinel.diagnostic.commander_handoff import CommanderHandoff
from sentinel.execution import ExecutionBoundary
from sentinel.live_remediation_safety import (
    BoundRemediationEffect,
    TmuxTargetIdentity,
)
from sentinel.remediation_execution_identity import (
    RemediationExecutionIdentityJournal,
)
from sentinel.remediation_policy import RemediationPolicy
from sentinel.runtime import SentinelRuntime


ACTION = "controlled_bound_effect"


def target(run_id="run-bound", pane_id="%213c"):
    return TmuxTargetIdentity(
        run_id=run_id,
        server_socket="/tmp/airiv-bound.sock",
        server_generation="uid=1000;pid=321;start=654",
        session_id="$213",
        session_name="airiv-bound",
        window_id="@213",
        pane_id=pane_id,
    )


def effect(
    *,
    run_id="run-bound",
    execution_id="EXEC-BOUND",
    permit_id="PERMIT-BOUND",
    incident_id="INC-BOUND",
    pane_id="%213c",
    argv=None,
):
    t = target(
        run_id=run_id,
        pane_id=pane_id,
    )

    return BoundRemediationEffect(
        incident_id=incident_id,
        component_id=pane_id,
        action=ACTION,
        argv=argv or (
            "tmux",
            "-S",
            t.server_socket,
            "display-message",
            "-p",
            "-t",
            pane_id,
            "#{pane_id}",
        ),
        target=t,
        execution_id=execution_id,
        permit_id=permit_id,
    )


def configure(policy, bound):
    policy.allowed_actions = {ACTION}
    policy.configure_bound_effect(bound)

    return policy.evaluate_bound(
        incident_state="INVESTIGATING",
        effect=bound,
    )


def build_incident(runtime, bound):
    incident = runtime.incident_manager.evaluate_anomaly(
        {
            "source": "TMUX",
            "pane_id": bound.component_id,
            "pane_dead": True,
        },
        "PANE_DEAD",
        "controlled bound wiring test",
    )

    assert incident.incident_id

    # Effect is immutable, so rebuild using canonical incident identity.
    rebound = BoundRemediationEffect(
        incident_id=incident.incident_id,
        component_id=bound.component_id,
        action=bound.action,
        argv=bound.argv,
        target=bound.target,
        execution_id=bound.execution_id,
        permit_id=bound.permit_id,
    )

    runtime.incident_manager.investigate(
        incident.component_id
    )

    return incident, rebound


def test_bound_commander_api_has_no_command_or_execution_substitution():
    params = signature(
        CommanderOrchestrator.remediate_bound
    ).parameters

    assert "command" not in params
    assert "execution_id" not in params
    assert "effect" in params
    assert "authorization" in params

    handoff_params = signature(
        CommanderHandoff.remediate_bound
    ).parameters

    assert "command" not in handoff_params
    assert "execution_id" not in handoff_params


def test_execute_argv_is_shell_free_and_bounded(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))

        return SimpleNamespace(
            stdout="ok",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(
        "sentinel.execution.subprocess.run",
        fake_run,
    )

    boundary = ExecutionBoundary()

    result = boundary.execute_argv(
        ("binary", "--flag", "value"),
        timeout=2.5,
    )

    assert result.success is True
    assert len(calls) == 1

    argv, kwargs = calls[0]

    assert argv == [
        "binary",
        "--flag",
        "value",
    ]

    assert kwargs == {
        "capture_output": True,
        "text": True,
        "timeout": 2.5,
        "check": False,
    }

    assert "shell" not in kwargs


def test_bound_commander_policy_is_evaluated_once_before_effect(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "IDENTITY"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "DIAGNOSTIC"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "RUNTIME"),
    )

    runtime = SentinelRuntime()

    seed = effect()
    incident, bound = build_incident(
        runtime,
        seed,
    )

    runtime.policy.allowed_actions = {ACTION}
    runtime.policy.configure_bound_effect(bound)

    policy_calls = 0
    original = runtime.policy.evaluate_bound

    def evaluate_bound(**kwargs):
        nonlocal policy_calls
        policy_calls += 1
        return original(**kwargs)

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_bound",
        evaluate_bound,
    )

    execution_calls = []

    def execute_argv(argv, *, timeout=5.0):
        from sentinel.execution import ExecutionResult
        import json

        execution_calls.append(
            (tuple(argv), timeout)
        )

        return ExecutionResult(
            command=json.dumps(
                list(argv),
                separators=(",", ":"),
            ),
            stdout="ok",
            stderr="",
            exit_code=0,
            started_at="start",
            finished_at="finish",
        )

    monkeypatch.setattr(
        runtime.execution,
        "execute_argv",
        execute_argv,
    )

    authorization = (
        runtime.commander.decide_bound_remediation(
            incident=incident,
            effect=bound,
        )
    )

    assert authorization.authorized
    assert policy_calls == 1

    result = runtime.commander.remediate_bound(
        incident=incident,
        effect=bound,
        authorization=authorization,
    )

    assert policy_calls == 1
    assert result.execution is not None
    assert result.execution.success
    assert len(execution_calls) == 1

    permit = (
        runtime.commander
        .remediation_orchestrator
        .identity_boundary
        .journal
        .get_live_run_permit(
            bound.target.run_id
        )
    )

    assert permit is not None
    assert permit.execution_id == bound.execution_id


def test_tampered_effect_rejected_before_identity_or_effect(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "IDENTITY"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "DIAGNOSTIC"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "RUNTIME"),
    )

    runtime = SentinelRuntime()

    seed = effect()
    incident, bound = build_incident(
        runtime,
        seed,
    )

    runtime.policy.allowed_actions = {ACTION}
    runtime.policy.configure_bound_effect(bound)

    authorization = (
        runtime.commander.decide_bound_remediation(
            incident=incident,
            effect=bound,
        )
    )

    tampered = BoundRemediationEffect(
        incident_id=bound.incident_id,
        component_id=bound.component_id,
        action=bound.action,
        argv=bound.argv + ("TAMPERED",),
        target=bound.target,
        execution_id=bound.execution_id,
        permit_id=bound.permit_id,
    )

    effect_calls = []

    monkeypatch.setattr(
        runtime.execution,
        "execute_argv",
        lambda *a, **k: effect_calls.append(
            (a, k)
        ),
    )

    with pytest.raises(
        PermissionError,
        match="authorization_effect_binding_mismatch",
    ):
        runtime.commander.remediate_bound(
            incident=incident,
            effect=tampered,
            authorization=authorization,
        )

    assert effect_calls == []

    journal = (
        runtime.commander
        .remediation_orchestrator
        .identity_boundary
        .journal
    )

    assert (
        journal.get_live_run_permit(
            bound.target.run_id
        )
        is None
    )

    assert journal.get(
        bound.execution_id
    ) is None


def test_consumed_permit_without_execution_identity_fails_closed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "IDENTITY"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "DIAGNOSTIC"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "RUNTIME"),
    )

    runtime = SentinelRuntime()

    seed = effect()
    incident, bound = build_incident(
        runtime,
        seed,
    )

    runtime.policy.allowed_actions = {ACTION}
    runtime.policy.configure_bound_effect(bound)

    authorization = (
        runtime.commander.decide_bound_remediation(
            incident=incident,
            effect=bound,
        )
    )

    journal = (
        runtime.commander
        .remediation_orchestrator
        .identity_boundary
        .journal
    )

    first = journal.claim_live_run_permit(
        effect=bound,
        authorization=authorization,
    )

    assert not first.replayed
    assert journal.get(bound.execution_id) is None

    effect_calls = []

    monkeypatch.setattr(
        runtime.execution,
        "execute_argv",
        lambda *a, **k: effect_calls.append(
            (a, k)
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "live_run_permit_replay_without_"
            "execution_identity"
        ),
    ):
        runtime.commander.remediate_bound(
            incident=incident,
            effect=bound,
            authorization=authorization,
        )

    assert effect_calls == []
    assert journal.get(bound.execution_id) is None


def test_exact_replay_does_not_execute_second_effect(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "IDENTITY"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "DIAGNOSTIC"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "RUNTIME"),
    )

    runtime = SentinelRuntime()

    seed = effect()
    incident, bound = build_incident(
        runtime,
        seed,
    )

    runtime.policy.allowed_actions = {ACTION}
    runtime.policy.configure_bound_effect(bound)

    authorization = (
        runtime.commander.decide_bound_remediation(
            incident=incident,
            effect=bound,
        )
    )

    calls = []

    def execute_argv(argv, *, timeout=5.0):
        from sentinel.execution import ExecutionResult
        import json

        calls.append(tuple(argv))

        return ExecutionResult(
            command=json.dumps(
                list(argv),
                separators=(",", ":"),
            ),
            stdout="ok",
            stderr="",
            exit_code=0,
            started_at="start",
            finished_at="finish",
        )

    monkeypatch.setattr(
        runtime.execution,
        "execute_argv",
        execute_argv,
    )

    first = (
        runtime.commander
        .remediation_orchestrator
        .handle_bound_incident(
            incident=incident,
            effect=bound,
            authorization=authorization,
        )
    )

    replay = (
        runtime.commander
        .remediation_orchestrator
        .handle_bound_incident(
            incident=incident,
            effect=bound,
            authorization=authorization,
        )
    )

    assert not first.replayed
    assert replay.replayed
    assert len(calls) == 1
    assert replay.execution == first.execution
    assert replay.identity_record == first.identity_record


def test_bound_path_uses_same_identity_journal():
    runtime = SentinelRuntime()

    orchestrator = (
        runtime.commander.remediation_orchestrator
    )

    assert isinstance(
        orchestrator.identity_boundary.journal,
        RemediationExecutionIdentityJournal,
    )

    # The Runtime compatibility orchestrator and Commander orchestrator
    # are distinct composition objects. The safety invariant is shared
    # canonical policy/executor authority, not Python object identity
    # between their identity-boundary wrappers.
    assert orchestrator.policy is runtime.policy
    assert runtime.orchestrator.policy is runtime.policy

    assert orchestrator.gate.executor is runtime.execution
    assert runtime.orchestrator.gate.executor is runtime.execution

    assert (
        orchestrator.identity_boundary.journal.root
        == runtime.orchestrator.identity_boundary.journal.root
    )
