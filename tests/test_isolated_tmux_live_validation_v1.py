from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentinel.isolated_tmux_live_validation import (
    IsolatedTmuxValidationController,
    IsolatedTmuxValidationSpec,
)
from sentinel.runtime import SentinelRuntime


def success():
    return SimpleNamespace(
        returncode=0,
        stdout="",
        stderr="",
    )


def spec(
    tmp_path,
):
    return (
        IsolatedTmuxValidationSpec
        .for_root(
            run_id="RUN-1F",
            root_dir=str(
                tmp_path
                / "isolated-liveval"
            ),
        )
    )


def test_spec_requires_socket_inside_owned_root(
    tmp_path,
):
    root = tmp_path / "owned"

    with pytest.raises(
        ValueError,
        match="inside root_dir",
    ):
        IsolatedTmuxValidationSpec(
            run_id="RUN-X",
            root_dir=str(root),
            server_socket=str(
                tmp_path
                / "outside.sock"
            ),
            session_name=(
                "airiv-sentinel-liveval-RUN-X"
            ),
        )


def test_spec_never_uses_default_tmux_endpoint(
    tmp_path,
):
    value = spec(
        tmp_path
    )

    assert value.server_socket
    assert (
        Path(
            value.server_socket
        ).parent
        == Path(
            value.root_dir
        )
    )

    assert value.session_name.startswith(
        "airiv-sentinel-liveval-"
    )


def test_activation_uses_exact_isolated_socket_and_no_shell(
    tmp_path,
):
    calls = []

    def runner(
        command,
        **kwargs,
    ):
        calls.append(
            (
                command,
                kwargs,
            )
        )
        return success()

    value = spec(
        tmp_path
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=runner,
        )
    )

    activation = (
        controller.activate()
    )

    assert activation.run_id == "RUN-1F"
    assert controller.active

    assert calls[0][0] == [
        "tmux",
        "-S",
        value.server_socket,
        "new-session",
        "-d",
        "-s",
        value.session_name,
        "-n",
        value.window_name,
        "/usr/bin/sleep",
        "300",
    ]

    assert calls[1][0] == [
        "tmux",
        "-S",
        value.server_socket,
        "set-option",
        "-t",
        value.session_name,
        "remain-on-exit",
        "on",
    ]

    for _, kwargs in calls:
        assert kwargs["timeout"] == 5.0
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert "shell" not in kwargs

    marker = Path(
        value.marker_path
    )

    assert marker.exists()

    payload = json.loads(
        marker.read_text()
    )

    assert payload["run_id"] == "RUN-1F"
    assert (
        payload["server_socket"]
        == value.server_socket
    )

    controller.teardown()


def test_teardown_targets_only_exact_isolated_server(
    tmp_path,
):
    calls = []

    def runner(
        command,
        **kwargs,
    ):
        calls.append(
            command
        )
        return success()

    value = spec(
        tmp_path
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=runner,
        )
    )

    controller.activate()

    assert controller.teardown()

    assert calls[-1] == [
        "tmux",
        "-S",
        value.server_socket,
        "kill-server",
    ]

    assert not controller.active

    assert not Path(
        value.marker_path
    ).exists()

    assert not Path(
        value.root_dir
    ).exists()


def test_teardown_is_idempotent(
    tmp_path,
):
    value = spec(
        tmp_path
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=lambda *a, **k: success(),
        )
    )

    controller.activate()

    assert controller.teardown()
    assert controller.teardown() is False


def test_activation_failure_cleans_owned_state(
    tmp_path,
):
    calls = []

    def runner(
        command,
        **kwargs,
    ):
        calls.append(
            command
        )

        if "new-session" in command:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="failed",
            )

        return success()

    value = spec(
        tmp_path
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=runner,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="activation_failed",
    ):
        controller.activate()

    assert not controller.active

    assert not Path(
        value.root_dir
    ).exists()


def test_remain_on_exit_failure_runs_teardown(
    tmp_path,
):
    calls = []

    def runner(
        command,
        **kwargs,
    ):
        calls.append(
            command
        )

        if "set-option" in command:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="failed",
            )

        return success()

    value = spec(
        tmp_path
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=runner,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="remain_on_exit_failed",
    ):
        controller.activate()

    assert any(
        "kill-server" in command
        for command in calls
    )

    assert not Path(
        value.root_dir
    ).exists()


def test_context_manager_tears_down_after_exception(
    tmp_path,
):
    calls = []

    def runner(
        command,
        **kwargs,
    ):
        calls.append(
            command
        )
        return success()

    value = spec(
        tmp_path
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=runner,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="test-error",
    ):
        with controller:
            raise RuntimeError(
                "test-error"
            )

    assert any(
        "kill-server" in command
        for command in calls
    )

    assert not controller.active
    assert not Path(
        value.root_dir
    ).exists()


def test_foreign_marker_fails_closed_without_kill(
    tmp_path,
):
    calls = []

    def runner(
        command,
        **kwargs,
    ):
        calls.append(
            command
        )
        return success()

    value = spec(
        tmp_path
    )

    root = Path(
        value.root_dir
    )

    root.mkdir(
        parents=True
    )

    marker = Path(
        value.marker_path
    )

    marker.write_text(
        json.dumps(
            {
                "kind": "FOREIGN",
                "run_id": "OTHER",
            }
        )
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=runner,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="ownership_mismatch",
    ):
        controller.teardown()

    assert calls == []
    assert root.exists()
    assert marker.exists()


def test_existing_unowned_root_blocks_activation(
    tmp_path,
):
    value = spec(
        tmp_path
    )

    root = Path(
        value.root_dir
    )

    root.mkdir(
        parents=True
    )

    controller = (
        IsolatedTmuxValidationController(
            value,
            runner=lambda *a, **k: success(),
        )
    )

    with pytest.raises(
        RuntimeError,
        match="root_already_exists",
    ):
        controller.activate()


def test_tests_never_invoke_real_subprocess(
    tmp_path,
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "real subprocess must not execute"
        )

    monkeypatch.setattr(
        "subprocess.run",
        forbidden,
    )

    calls = []

    controller = (
        IsolatedTmuxValidationController(
            spec(tmp_path),
            runner=lambda *a, **k: (
                calls.append(
                    (a, k)
                )
                or success()
            ),
        )
    )

    controller.activate()
    controller.teardown()

    assert calls


def test_production_defaults_remain_empty(
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

    runtime = SentinelRuntime()

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
