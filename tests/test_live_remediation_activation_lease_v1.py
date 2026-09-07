from __future__ import annotations

import subprocess

import pytest

from sentinel.live_remediation_activation_lease import (
    TemporaryLiveRemediationActivationLease,
)
from sentinel.live_remediation_bound_composition import (
    build_bound_tmux_remediation_plan,
)
from sentinel.remediation_action_catalog import (
    RemediationActionEntry,
)
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationRequest,
)
from sentinel.runtime import SentinelRuntime


ACTION = "phase213c1g_test_local"
TRIGGER = "PHASE_213C1G_TEST_LOCAL"
GEN = "uid=1000;pid=321;start=654"
HASH = "d" * 64


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


def make_plan():
    evidence = {
        "source": "TMUX",
        "captured_at": "2026-09-06T00:00:00+00:00",
        "server_socket": "/tmp/airiv-213c1g/tmux.sock",
        "server_generation": GEN,
        "session_id": "$1",
        "session_name": "airiv-sentinel-liveval-RUN-1G",
        "window_id": "@1",
        "pane_id": "%1",
        "pane_dead": True,
        "output_sha256": HASH,
        "tmux_identity_valid": True,
        "tmux_identity": {
            "server_socket": "/tmp/airiv-213c1g/tmux.sock",
            "server_generation": GEN,
            "session_id": "$1",
            "session_name": "airiv-sentinel-liveval-RUN-1G",
            "window_id": "@1",
            "pane_id": "%1",
        },
    }

    return build_bound_tmux_remediation_plan(
        raw_evidence=evidence,
        run_id="RUN-1G",
        incident_id="INC-1G",
        component_id="%1",
        action=ACTION,
        argv=("AIRIV_TEST_LOCAL_NO_EFFECT",),
        execution_id="EXEC-1G",
        permit_id="PERMIT-1G",
    )


def make_entry():
    return RemediationActionEntry(
        action=ACTION,
        command="TEST_LOCAL_ONLY_NOT_EXECUTABLE",
        rationale="Phase 2.13C.1G test-local activation lease",
    )


def make_lease(runtime):
    plan = make_plan()

    return (
        TemporaryLiveRemediationActivationLease(
            policy=runtime.policy,
            catalog=runtime.remediation_action_catalog,
            effect=plan.effect,
            entry=make_entry(),
            trigger=TRIGGER,
        ),
        plan,
    )


def assert_empty(runtime):
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()

    assert (
        runtime.remediation_action_catalog.list_actions()
        == ()
    )

    assert (
        runtime.remediation_action_catalog.list_triggers()
        == ()
    )


def test_fresh_runtime_empty(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    assert_empty(runtime)


def test_exact_temporary_activation(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    lease, plan = make_lease(runtime)

    with lease:
        assert lease.active

        assert runtime.policy.allowed_actions == {
            ACTION
        }

        assert runtime.policy.list_bound_runs() == (
            "RUN-1G",
        )

        assert (
            runtime.remediation_action_catalog.list_actions()
            == (ACTION,)
        )

        assert (
            runtime.remediation_action_catalog.list_triggers()
            == (TRIGGER,)
        )

        base = runtime.policy.evaluate(
            RemediationRequest(
                "OPEN",
                "%1",
                ACTION,
            )
        )

        assert base.decision == PolicyDecision.ALLOW

        authorization = runtime.policy.evaluate_bound(
            incident_state="OPEN",
            effect=plan.effect,
        )

        assert authorization.authorized
        assert authorization.matches(plan.effect)

    assert_empty(runtime)


def test_normal_exit_restores_exact_container_identity(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    lease, _ = make_lease(runtime)

    allowed_ref = runtime.policy.allowed_actions

    entries_ref = (
        runtime.remediation_action_catalog._entries
    )

    trigger_ref = (
        runtime.remediation_action_catalog._trigger_map
    )

    with lease:
        assert lease.active

    assert_empty(runtime)

    assert runtime.policy.allowed_actions is allowed_ref

    assert (
        runtime.remediation_action_catalog._entries
        is entries_ref
    )

    assert (
        runtime.remediation_action_catalog._trigger_map
        is trigger_ref
    )

    assert not hasattr(
        runtime.policy,
        "_bound_effects_by_run",
    )


def test_exception_restores_exact_state(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    lease, _ = make_lease(runtime)

    with pytest.raises(
        RuntimeError,
        match="intentional-error",
    ):
        with lease:
            raise RuntimeError(
                "intentional-error"
            )

    assert_empty(runtime)
    assert not lease.active


def test_activation_failure_rolls_back(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    lease, _ = make_lease(runtime)

    def fail(*args, **kwargs):
        raise RuntimeError(
            "forced-register-failure"
        )

    monkeypatch.setattr(
        runtime.remediation_action_catalog,
        "register",
        fail,
    )

    with pytest.raises(
        RuntimeError,
        match="forced-register-failure",
    ):
        lease.activate()

    assert_empty(runtime)
    assert not lease.active


def test_existing_allowed_action_collision_fails_closed(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    runtime.policy.allowed_actions.add(
        ACTION
    )

    lease, _ = make_lease(runtime)

    before = set(
        runtime.policy.allowed_actions
    )

    with pytest.raises(
        RuntimeError,
        match="lease_action_already_allowed",
    ):
        lease.activate()

    assert runtime.policy.allowed_actions == before
    assert runtime.remediation_action_catalog.list_actions() == ()


def test_existing_bound_run_collision_fails_closed(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan()

    runtime.policy.allowed_actions.add(
        ACTION
    )

    runtime.policy.configure_bound_effect(
        plan.effect
    )

    runtime.policy.allowed_actions.remove(
        ACTION
    )

    lease, _ = make_lease(runtime)

    with pytest.raises(
        RuntimeError,
        match="lease_run_already_bound",
    ):
        lease.activate()

    assert runtime.policy.allowed_actions == set()

    assert runtime.policy.list_bound_runs() == (
        "RUN-1G",
    )


def test_overlapping_lease_blocked(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    first, _ = make_lease(runtime)
    second, _ = make_lease(runtime)

    with first:
        with pytest.raises(
            RuntimeError,
            match="activation_lease_already_held",
        ):
            second.activate()

    assert_empty(runtime)


def test_close_idempotent_after_restore(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    lease, _ = make_lease(runtime)

    lease.activate()

    assert lease.close()
    assert lease.close() is False

    assert_empty(runtime)


def test_lease_executes_no_subprocess(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    lease, _ = make_lease(runtime)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "lease must never execute subprocess"
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        forbidden,
    )

    with lease:
        assert lease.active

    assert_empty(runtime)


def test_nonempty_preexisting_snapshot_restored_exactly(
    tmp_path,
    monkeypatch,
):
    runtime = make_runtime(
        tmp_path,
        monkeypatch,
    )

    existing = RemediationActionEntry(
        action="existing_test_action",
        command="EXISTING_TEST_ONLY",
        rationale="Phase 2.13C.1G pre-existing test-local state",
    )

    runtime.policy.allowed_actions.add(
        "existing_test_action"
    )

    runtime.remediation_action_catalog.register(
        existing,
        trigger="EXISTING_TEST_TRIGGER",
    )

    allowed_before = set(
        runtime.policy.allowed_actions
    )

    entries_before = dict(
        runtime.remediation_action_catalog._entries
    )

    triggers_before = dict(
        runtime.remediation_action_catalog._trigger_map
    )

    lease, _ = make_lease(runtime)

    with lease:
        assert ACTION in runtime.policy.allowed_actions

        assert (
            "existing_test_action"
            in runtime.policy.allowed_actions
        )

    assert runtime.policy.allowed_actions == allowed_before

    assert (
        runtime.remediation_action_catalog._entries
        == entries_before
    )

    assert (
        runtime.remediation_action_catalog._trigger_map
        == triggers_before
    )


def test_separate_fresh_runtime_remains_empty(
    tmp_path,
    monkeypatch,
):
    first = make_runtime(
        tmp_path / "first",
        monkeypatch,
    )

    lease, _ = make_lease(first)

    with lease:
        assert lease.active

    assert_empty(first)

    second = make_runtime(
        tmp_path / "second",
        monkeypatch,
    )

    assert_empty(second)
