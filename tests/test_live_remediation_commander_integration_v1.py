from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sentinel.bound_tmux_exact_verifier import (
    BoundTmuxExactVerification,
)
from sentinel.execution import (
    ExecutionResult,
)
from sentinel.live_remediation_bound_composition import (
    build_bound_tmux_remediation_plan,
)
from sentinel.live_remediation_commander_integration import (
    execute_prepared_bound_tmux_remediation,
    prepare_bound_tmux_remediation,
)
from sentinel.runtime import SentinelRuntime
from sentinel.tmux_server_generation_verifier import (
    TmuxServerGenerationVerification,
)


GEN = "uid=1000;pid=321;start=654"
SOCKET = "/tmp/tmux-1000/default"
HASH = "c" * 64

ACTION = "phase213c1e_test_local"
RUN = "RUN-213C1E"
EXECUTION = "EXEC-213C1E"
PERMIT = "PERMIT-213C1E"


def strong_evidence(
    pane_id="%213c1e",
):
    return {
        "source": "TMUX",
        "captured_at":
            "2026-09-06T00:00:00+00:00",

        "server_socket":
            SOCKET,

        "server_generation":
            GEN,

        "session_id":
            "$1",

        "session_name":
            "airiv",

        "window_id":
            "@1",

        "pane_id":
            pane_id,

        "pane_dead":
            True,

        "output_sha256":
            HASH,

        "tmux_identity_valid":
            True,

        "tmux_identity": {
            "server_socket":
                SOCKET,

            "server_generation":
                GEN,

            "session_id":
                "$1",

            "session_name":
                "airiv",

            "window_id":
                "@1",

            "pane_id":
                pane_id,
        },
    }


def build_plan(
    incident_id,
    pane_id="%213c1e",
):
    return build_bound_tmux_remediation_plan(
        raw_evidence=strong_evidence(
            pane_id
        ),
        run_id=RUN,
        incident_id=incident_id,
        component_id=pane_id,
        action=ACTION,

        # Deliberately not a real executable.
        # ExecutionBoundary is replaced by a test-local effect adapter.
        argv=(
            "AIRIV_TEST_LOCAL_NO_EFFECT",
            pane_id,
        ),

        execution_id=EXECUTION,
        permit_id=PERMIT,

        expected_alive=True,
        timeout=5.0,
    )


def create_runtime(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "diagnostic"),
    )

    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "execution"),
    )

    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "runtime"),
    )

    return SentinelRuntime()


def create_incident(
    runtime,
    pane_id="%213c1e",
):
    return (
        runtime.incident_manager
        .evaluate_anomaly(
            observation={
                "source": "TMUX",
                "pane_id": pane_id,
                "pane_dead": True,
            },
            anomaly_type="PANE_DEAD",
            reason=(
                "Phase 2.13C.1E "
                "test-local integration"
            ),
        )
    )


class ExactVerifierStub:
    def __init__(
        self,
        plan,
        order,
        *,
        verified=True,
    ):
        self.plan = plan
        self.order = order
        self.verified = verified
        self.calls = 0

    def verify_exact(self):
        self.calls += 1
        self.order.append(
            "verify"
        )

        generation = (
            TmuxServerGenerationVerification(
                verified=self.verified,
                server_socket=SOCKET,
                expected_generation=GEN,
                observed_generation=(
                    GEN
                    if self.verified
                    else None
                ),
                reason=(
                    "verified"
                    if self.verified
                    else "test_failure"
                ),
            )
        )

        return BoundTmuxExactVerification(
            verified=self.verified,
            generation=generation,
            target_verification=(
                SimpleNamespace(
                    verified=self.verified
                )
            ),
            target_fingerprint=(
                self.plan.target_fingerprint
            ),
            reason=(
                "verified"
                if self.verified
                else "target_identity_not_verified"
            ),
        )


def install_test_local_effect(
    runtime,
    monkeypatch,
    order,
):
    calls = []

    def execute_argv(
        argv,
        timeout=5.0,
    ):
        immutable = tuple(
            argv
        )

        calls.append(
            (
                immutable,
                timeout,
            )
        )

        order.append(
            "execute"
        )

        return ExecutionResult(
            command=json.dumps(
                list(immutable),
                separators=(",", ":"),
            ),
            stdout="",
            stderr="",
            exit_code=0,
            started_at=1.0,
            finished_at=2.0,
        )

    monkeypatch.setattr(
        runtime.execution,
        "execute_argv",
        execute_argv,
    )

    return calls


def configure_test_local_policy(
    runtime,
    plan,
):
    # Explicitly test-local.
    # Fresh production runtime defaults remain empty.
    runtime.policy.allowed_actions = {
        ACTION
    }

    runtime.policy.configure_bound_effect(
        plan.effect
    )


def test_prepare_performs_exactly_one_policy_evaluation(
    tmp_path,
    monkeypatch,
):
    runtime = create_runtime(
        tmp_path,
        monkeypatch,
    )

    incident = create_incident(
        runtime
    )

    plan = build_plan(
        incident.incident_id
    )

    configure_test_local_policy(
        runtime,
        plan,
    )

    calls = []

    original = (
        runtime.policy.evaluate_bound
    )

    def counted(*args, **kwargs):
        calls.append(
            (
                args,
                dict(kwargs),
            )
        )

        return original(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_bound",
        counted,
    )

    prepared = (
        prepare_bound_tmux_remediation(
            commander=runtime.commander,
            incident=incident,
            plan=plan,
        )
    )

    assert len(calls) == 1

    call_args, call_kwargs = calls[0]

    observed_effect = (
        call_kwargs.get("effect")
        or call_kwargs.get("bound_effect")
        or next(
            (
                value
                for value in call_args
                if value is plan.effect
            ),
            None,
        )
    )

    assert observed_effect is plan.effect

    assert (
        prepared.authorization
        .matches(
            plan.effect
        )
    )


def test_execute_prepared_does_not_reevaluate_policy(
    tmp_path,
    monkeypatch,
):
    runtime = create_runtime(
        tmp_path,
        monkeypatch,
    )

    incident = create_incident(
        runtime
    )

    plan = build_plan(
        incident.incident_id
    )

    configure_test_local_policy(
        runtime,
        plan,
    )

    prepared = (
        prepare_bound_tmux_remediation(
            commander=runtime.commander,
            incident=incident,
            plan=plan,
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "policy must not be reevaluated "
            "during prepared execution"
        )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_bound",
        forbidden,
    )

    order = []

    effect_calls = (
        install_test_local_effect(
            runtime,
            monkeypatch,
            order,
        )
    )

    exact = ExactVerifierStub(
        plan,
        order,
    )

    result = (
        execute_prepared_bound_tmux_remediation(
            commander=runtime.commander,
            incident=incident,
            prepared=prepared,
            exact_verifier=exact,
        )
    )

    assert result is not None

    assert len(
        effect_calls
    ) == 1

    assert (
        effect_calls[0][0]
        == plan.effect.argv
    )

    assert exact.calls == 1

    assert order == [
        "execute",
        "verify",
    ]


def test_canonical_path_cannot_substitute_command_or_execution_id(
    tmp_path,
    monkeypatch,
):
    runtime = create_runtime(
        tmp_path,
        monkeypatch,
    )

    incident = create_incident(
        runtime
    )

    plan = build_plan(
        incident.incident_id
    )

    configure_test_local_policy(
        runtime,
        plan,
    )

    prepared = (
        prepare_bound_tmux_remediation(
            commander=runtime.commander,
            incident=incident,
            plan=plan,
        )
    )

    order = []

    calls = install_test_local_effect(
        runtime,
        monkeypatch,
        order,
    )

    exact = ExactVerifierStub(
        plan,
        order,
    )

    execute_prepared_bound_tmux_remediation(
        commander=runtime.commander,
        incident=incident,
        prepared=prepared,
        exact_verifier=exact,
    )

    assert calls == [
        (
            plan.effect.argv,
            5.0,
        )
    ]

    assert (
        plan.effect.execution_id
        == EXECUTION
    )

    assert (
        plan.effect.permit_id
        == PERMIT
    )


def test_incident_substitution_is_blocked_before_execution(
    tmp_path,
    monkeypatch,
):
    runtime = create_runtime(
        tmp_path,
        monkeypatch,
    )

    incident = create_incident(
        runtime
    )

    plan = build_plan(
        incident.incident_id
    )

    other = create_incident(
        runtime,
        pane_id="%OTHER",
    )

    with pytest.raises(
        ValueError,
        match=(
            "incident_id_plan_mismatch|"
            "component_id_plan_mismatch"
        ),
    ):
        prepare_bound_tmux_remediation(
            commander=runtime.commander,
            incident=other,
            plan=plan,
        )


def test_exact_verification_failure_does_not_become_recovered(
    tmp_path,
    monkeypatch,
):
    runtime = create_runtime(
        tmp_path,
        monkeypatch,
    )

    incident = create_incident(
        runtime
    )

    plan = build_plan(
        incident.incident_id
    )

    configure_test_local_policy(
        runtime,
        plan,
    )

    prepared = (
        prepare_bound_tmux_remediation(
            commander=runtime.commander,
            incident=incident,
            plan=plan,
        )
    )

    order = []

    install_test_local_effect(
        runtime,
        monkeypatch,
        order,
    )

    exact = ExactVerifierStub(
        plan,
        order,
        verified=False,
    )

    result = (
        execute_prepared_bound_tmux_remediation(
            commander=runtime.commander,
            incident=incident,
            prepared=prepared,
            exact_verifier=exact,
        )
    )

    assert result is not None
    assert exact.calls == 1

    # Existing canonical outcome mapping must not classify
    # failed verification as RECOVERED.
    outcome = getattr(
        result,
        "final_outcome",
        None,
    )

    if outcome is None:
        outcome = getattr(
            incident,
            "final_outcome",
            None,
        )

    if hasattr(
        outcome,
        "value",
    ):
        outcome = outcome.value

    assert outcome != "RECOVERED"


def test_production_runtime_still_has_empty_activation(
    tmp_path,
    monkeypatch,
):
    runtime = create_runtime(
        tmp_path,
        monkeypatch,
    )

    assert (
        runtime.policy.allowed_actions
        == set()
    )

    assert (
        runtime.policy.list_bound_runs()
        == ()
    )

    assert (
        runtime.diagnostic
        .commander_semantic_policy
        .list_triggers()
        == ()
    )

    assert (
        runtime.remediation_action_catalog
        .list_actions()
        == ()
    )

    assert (
        runtime.remediation_action_catalog
        .list_triggers()
        == ()
    )
