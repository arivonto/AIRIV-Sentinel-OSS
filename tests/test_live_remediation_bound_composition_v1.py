from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sentinel.bound_tmux_exact_verifier import (
    BoundTmuxExactVerifier,
)
from sentinel.live_remediation_bound_composition import (
    build_bound_tmux_remediation_plan,
)
from sentinel.tmux_server_generation_verifier import (
    TmuxServerGenerationVerification,
    TmuxServerGenerationVerifier,
)


GEN = "uid=1000;pid=321;start=654"
HASH = "b" * 64
SOCKET = "/tmp/tmux-1000/default"


def evidence():
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
            "%1",
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
                "%1",
        },
    }


def plan():
    return build_bound_tmux_remediation_plan(
        raw_evidence=evidence(),
        run_id="RUN-1D",
        incident_id="INC-1D",
        component_id="%1",
        action="controlled_test_action",
        argv=(
            "/usr/bin/true",
        ),
        execution_id="EXEC-1D",
        permit_id="PERMIT-1D",
        expected_alive=True,
        timeout=5.0,
    )


def test_effect_and_verifier_share_exact_target():
    value = plan()

    assert (
        value.effect.target
        == value.target
    )

    assert (
        value.verification_target.identity
        == value.target
    )

    assert (
        value.effect.target
        is value.target
    )

    assert (
        value.verification_target.identity
        is value.target
    )

    assert (
        value.effect.component_id
        == value.target.pane_id
        == value.verification_target.pane_id
        == "%1"
    )

    assert (
        value.verification_target.strong_identity
        is True
    )

    assert value.target.live_eligible


def test_bound_plan_contains_immutable_argv():
    value = plan()

    assert value.effect.argv == (
        "/usr/bin/true",
    )

    assert isinstance(
        value.effect.argv,
        tuple,
    )


def test_component_substitution_fails_closed():
    with pytest.raises(
        ValueError,
        match="component_target_mismatch",
    ):
        build_bound_tmux_remediation_plan(
            raw_evidence=evidence(),
            run_id="RUN-X",
            incident_id="INC-X",
            component_id="%999",
            action="controlled_test_action",
            argv=("/usr/bin/true",),
            execution_id="EXEC-X",
            permit_id="PERMIT-X",
        )


def test_evidence_target_tamper_fails_closed():
    raw = evidence()

    raw["tmux_identity"] = dict(
        raw["tmux_identity"]
    )

    raw[
        "tmux_identity"
    ][
        "session_id"
    ] = "$OTHER"

    with pytest.raises(
        ValueError,
        match="tmux_identity_snapshot_mismatch",
    ):
        build_bound_tmux_remediation_plan(
            raw_evidence=raw,
            run_id="RUN-X",
            incident_id="INC-X",
            component_id="%1",
            action="controlled_test_action",
            argv=("/usr/bin/true",),
            execution_id="EXEC-X",
            permit_id="PERMIT-X",
        )


def test_plan_construction_executes_nothing(
    monkeypatch,
):
    called = []

    def forbidden(*args, **kwargs):
        called.append(
            (args, kwargs)
        )
        raise AssertionError(
            "plan construction must not execute subprocess"
        )

    monkeypatch.setattr(
        "subprocess.run",
        forbidden,
    )

    value = plan()

    assert value.effect.argv == (
        "/usr/bin/true",
    )

    assert called == []


def proc_stat(
    pid=321,
    start="654",
):
    # /proc/PID/stat:
    # field 1 PID
    # field 2 comm
    # remainder starts at field 3.
    # starttime is field 22 -> remainder index 19.
    remainder = [
        "S",
        "1",
        "1",
        "1",
        "0",
        "-1",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        start,
        "0",
        "0",
    ]

    return (
        f"{pid} (tmux: server) "
        + " ".join(remainder)
    )


def test_independent_generation_verification_success():
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,
            stdout="321\n",
            stderr="",
        )
    )

    def stat_fn(path):
        assert path in (
            SOCKET,
            "/proc/321",
        )
        return SimpleNamespace(
            st_uid=1000
        )

    verifier = TmuxServerGenerationVerifier(
        runner=run,
        stat_fn=stat_fn,
        proc_stat_reader=lambda pid: proc_stat(pid),
    )

    result = verifier.verify(
        plan().target,
        timeout=5.0,
    )

    assert result.verified
    assert result.observed_generation == GEN
    assert result.reason == "verified"

    assert run.call_args.args[0] == [
        "tmux",
        "-S",
        SOCKET,
        "display-message",
        "-p",
        "#{pid}",
    ]

    assert (
        run.call_args.kwargs["timeout"]
        == 5.0
    )

    assert (
        run.call_args.kwargs["check"]
        is False
    )

    assert "shell" not in run.call_args.kwargs


def test_server_pid_reuse_or_change_fails_closed():
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,
            stdout="999\n",
            stderr="",
        )
    )

    verifier = TmuxServerGenerationVerifier(
        runner=run,
        stat_fn=Mock(),
        proc_stat_reader=Mock(),
    )

    result = verifier.verify(
        plan().target
    )

    assert not result.verified
    assert (
        result.reason
        == "server_pid_mismatch"
    )


def test_server_start_generation_change_fails_closed():
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,
            stdout="321\n",
            stderr="",
        )
    )

    verifier = TmuxServerGenerationVerifier(
        runner=run,
        stat_fn=lambda path: SimpleNamespace(
            st_uid=1000
        ),
        proc_stat_reader=lambda pid: proc_stat(
            pid,
            start="DIFFERENT"
            if False
            else "999",
        ),
    )

    result = verifier.verify(
        plan().target
    )

    assert not result.verified
    assert (
        result.reason
        == "server_start_identity_mismatch"
    )


def test_socket_owner_mismatch_fails_closed():
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,
            stdout="321\n",
            stderr="",
        )
    )

    def stat_fn(path):
        if path == SOCKET:
            return SimpleNamespace(
                st_uid=2000
            )

        return SimpleNamespace(
            st_uid=1000
        )

    verifier = TmuxServerGenerationVerifier(
        runner=run,
        stat_fn=stat_fn,
        proc_stat_reader=lambda pid: proc_stat(pid),
    )

    result = verifier.verify(
        plan().target
    )

    assert not result.verified
    assert (
        result.reason
        == "socket_process_uid_mismatch"
    )


def test_exact_verifier_checks_generation_before_target():
    value = plan()

    generation = Mock()

    generation.verify.return_value = (
        TmuxServerGenerationVerification(
            verified=False,
            server_socket=SOCKET,
            expected_generation=GEN,
            observed_generation=None,
            reason="server_pid_mismatch",
        )
    )

    target = Mock()

    verifier = BoundTmuxExactVerifier(
        value,
        generation_verifier=generation,
        target_verifier=target,
    )

    result = verifier.verify_exact()

    assert not result.verified
    assert (
        result.reason
        == "server_generation_not_verified"
    )

    target.verify.assert_not_called()


def test_exact_verifier_requires_both_generation_and_target():
    value = plan()

    generation = Mock()

    generation.verify.return_value = (
        TmuxServerGenerationVerification(
            verified=True,
            server_socket=SOCKET,
            expected_generation=GEN,
            observed_generation=GEN,
            reason="verified",
        )
    )

    target = Mock()

    target.verify.return_value = (
        SimpleNamespace(
            verified=True
        )
    )

    verifier = BoundTmuxExactVerifier(
        value,
        generation_verifier=generation,
        target_verifier=target,
    )

    result = verifier.verify_exact()

    assert result.verified
    assert result.reason == "verified"

    generation.verify.assert_called_once()
    target.verify.assert_called_once_with()
