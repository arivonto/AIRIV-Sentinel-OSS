from __future__ import annotations

import subprocess

import pytest

from sentinel.controlled_live_dry_run import (
    prepare_controlled_live_dry_run,
)
from sentinel.isolated_tmux_live_validation import (
    IsolatedTmuxValidationController,
    IsolatedTmuxValidationSpec,
)
from sentinel.remediation_action_catalog import (
    RemediationActionEntry,
)
from sentinel.runtime import SentinelRuntime
from sentinel.sensors.tmux.parser import (
    TmuxStateParserV11,
)


GEN = "uid=1000;pid=4321;start=987654"
ACTION = "phase213c1h_test_local"
TRIGGER = "PHASE_213C1H_TEST_LOCAL"


def make_runtime(
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


def make_spec(
    tmp_path,
):
    return (
        IsolatedTmuxValidationSpec
        .for_root(
            run_id="WORKLOAD-1H",
            root_dir=str(
                tmp_path
                / "isolated-workload"
            ),
            workload_argv=(
                "/usr/bin/sleep",
                "300",
            ),
        )
    )


def make_sensor_observation(
    monkeypatch,
    spec,
):
    parser = TmuxStateParserV11(
        server_socket=spec.server_socket,
    )

    raw = (
        "$1\t"
        f"{spec.session_name}\t"
        "@1\t"
        "0\t"
        f"{spec.window_name}\t"
        "0\t"
        "%1\t"
        "1\t"
        "1\t"
        "bash\t"
        "12345\n"
    )

    calls = []

    def list_panes(
        *,
        server_socket=None,
    ):
        calls.append(
            (
                "list",
                server_socket,
            )
        )
        return raw

    def resolve():
        calls.append(
            (
                "resolve",
                None,
            )
        )

        return (
            spec.server_socket,
            GEN,
        )

    monkeypatch.setattr(
        parser,
        "_list_panes",
        list_panes,
    )

    monkeypatch.setattr(
        parser,
        "_resolve_server_identity",
        resolve,
    )

    monkeypatch.setattr(
        parser,
        "_server_generation_matches",
        lambda socket, generation: (
            socket == spec.server_socket
            and generation == GEN
        ),
    )

    monkeypatch.setattr(
        parser,
        "capture_pane_content",
        lambda pane_id, *, server_socket=None: (
            "controlled-live dry-run evidence"
        ),
    )

    observations = parser.inspect_panes()

    assert len(observations) == 1

    observation = observations[0]

    assert calls[:3] == [
        (
            "list",
            spec.server_socket,
        ),
        (
            "resolve",
            None,
        ),
        (
            "list",
            spec.server_socket,
        ),
    ]

    assert observation["tmux_identity_valid"] is True
    assert "run_id" not in observation

    return observation


def make_entry():
    return RemediationActionEntry(
        action=ACTION,
        command="BOUND_EFFECT_ONLY_TEST_LOCAL",
        rationale=(
            "Phase 2.13C.1H controlled-live dry-run"
        ),
    )


def assert_activation_empty(
    runtime,
):
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()

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


def prepare(
    *,
    runtime,
    spec,
    observation,
):
    return prepare_controlled_live_dry_run(
        runtime=runtime,
        workload_spec=spec,
        sensor_observation=observation,
        run_id="REMEDIATION-RUN-1H",
        action=ACTION,
        argv=(
            "AIRIV_TEST_LOCAL_NO_EFFECT",
            "%1",
        ),
        execution_id="EXEC-1H",
        permit_id="PERMIT-1H",
        catalog_entry=make_entry(),
        trigger=TRIGGER,
    )


def test_complete_pre_effect_dry_run(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    result = prepare(
        runtime=runtime,
        spec=spec,
        observation=observation,
    )

    assert result.authorized

    assert (
        result.incident.component_id
        == "%1"
    )

    assert (
        result.investigation.component_id
        == "%1"
    )

    assert (
        result.plan.effect.component_id
        == "%1"
    )

    assert (
        result.plan.target.pane_id
        == "%1"
    )

    assert (
        result.plan.target.run_id
        == "REMEDIATION-RUN-1H"
    )

    assert (
        result.plan.target.server_socket
        == spec.server_socket
    )

    assert (
        result.plan.target.session_name
        == spec.session_name
    )

    assert (
        result.prepared.authorization
        .matches(
            result.plan.effect
        )
    )

    assert_activation_empty(
        runtime
    )


def test_sensor_run_id_is_external_to_observation(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    assert "run_id" not in observation

    result = prepare(
        runtime=runtime,
        spec=spec,
        observation=observation,
    )

    assert (
        result.plan.target.run_id
        == "REMEDIATION-RUN-1H"
    )


def test_strong_identity_survives_persistence(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    result = prepare(
        runtime=runtime,
        spec=spec,
        observation=observation,
    )

    raw = result.persisted_raw_evidence

    for key in (
        "server_socket",
        "server_generation",
        "session_id",
        "session_name",
        "window_id",
        "pane_id",
        "captured_at",
        "output_sha256",
        "tmux_identity",
        "tmux_identity_valid",
    ):
        assert key in raw

    assert raw["server_socket"] == spec.server_socket
    assert raw["server_generation"] == GEN
    assert raw["pane_id"] == "%1"

    assert (
        result.plan.target.fingerprint
        == result.prepared.authorization
        .target_fingerprint
    )


def test_workload_socket_mismatch_fails_before_incident(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    observation = dict(
        observation
    )

    observation[
        "server_socket"
    ] = "/tmp/FOREIGN/tmux.sock"

    called = []

    original = (
        runtime.incident_manager
        .evaluate_anomaly
    )

    def counted(*args, **kwargs):
        called.append(
            (
                args,
                kwargs,
            )
        )
        return original(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        runtime.incident_manager,
        "evaluate_anomaly",
        counted,
    )

    with pytest.raises(
        ValueError,
        match="workload_sensor_socket_mismatch",
    ):
        prepare(
            runtime=runtime,
            spec=spec,
            observation=observation,
        )

    assert called == []
    assert_activation_empty(runtime)


def test_weak_identity_fails_before_incident(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    observation = dict(
        observation
    )

    observation[
        "tmux_identity_valid"
    ] = False

    with pytest.raises(
        ValueError,
        match="strong_tmux_identity",
    ):
        prepare(
            runtime=runtime,
            spec=spec,
            observation=observation,
        )

    assert_activation_empty(runtime)


def test_sensor_owned_run_id_fails_closed(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    observation = dict(
        observation
    )

    observation["run_id"] = "ILLEGAL"

    with pytest.raises(
        ValueError,
        match="sensor_must_not_own_remediation_run_id",
    ):
        prepare(
            runtime=runtime,
            spec=spec,
            observation=observation,
        )


def test_dry_run_never_calls_remediate_bound_or_execution(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "dry-run crossed effect boundary"
        )

    monkeypatch.setattr(
        runtime.commander,
        "remediate_bound",
        forbidden,
    )

    monkeypatch.setattr(
        runtime.execution,
        "execute_argv",
        forbidden,
    )

    result = prepare(
        runtime=runtime,
        spec=spec,
        observation=observation,
    )

    assert result.authorized
    assert_activation_empty(runtime)


def test_dry_run_does_not_start_isolated_workload(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    calls = []

    controller = (
        IsolatedTmuxValidationController(
            spec,
            runner=lambda *args, **kwargs: (
                calls.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
        )
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    result = prepare(
        runtime=runtime,
        spec=spec,
        observation=observation,
    )

    assert result.authorized
    assert controller.active is False
    assert calls == []

    assert not (
        tmp_path
        / "isolated-workload"
    ).exists()


def test_no_real_subprocess_is_required(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "real subprocess forbidden in 1H"
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        forbidden,
    )

    result = prepare(
        runtime=runtime,
        spec=spec,
        observation=observation,
    )

    assert result.authorized


def test_temporary_activation_restored_after_authorization_exception(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    def fail(*args, **kwargs):
        raise RuntimeError(
            "forced-authorization-error"
        )

    monkeypatch.setattr(
        runtime.commander,
        "decide_bound_remediation",
        fail,
    )

    with pytest.raises(
        RuntimeError,
        match="forced-authorization-error",
    ):
        prepare(
            runtime=runtime,
            spec=spec,
            observation=observation,
        )

    assert_activation_empty(runtime)


def test_nonempty_production_activation_state_is_rejected(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    runtime.policy.allowed_actions.add(
        "foreign_action"
    )

    spec = make_spec(
        tmp_path
    )

    observation = (
        make_sensor_observation(
            monkeypatch,
            spec,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="dry_run_requires_empty_policy",
    ):
        prepare(
            runtime=runtime,
            spec=spec,
            observation=observation,
        )

    assert runtime.policy.allowed_actions == {
        "foreign_action"
    }
