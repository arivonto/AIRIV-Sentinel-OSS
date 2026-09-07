from dataclasses import FrozenInstanceError
import subprocess
from unittest.mock import Mock

import pytest

from sentinel.live_remediation_safety import (
    BoundRemediationEffect,
    TmuxTargetIdentity,
)
from sentinel.runtime import SentinelRuntime
from sentinel.tmux_remediation_verifier import (
    TmuxRemediationVerifier,
    TmuxVerificationTarget,
)


def identity(**changes):
    values = {
        "run_id": "run-213c1",
        "server_socket": "/tmp/airiv-213c1.sock",
        "server_generation": "uid=1000;pid=1234;start=5678",
        "session_id": "$42",
        "session_name": "airiv-validation-213c1",
        "window_id": "@9",
        "pane_id": "%7",
    }
    values.update(changes)
    return TmuxTargetIdentity(**values)


def effect(**changes):
    values = {
        "incident_id": "INC-213C1",
        "component_id": "%7",
        "action": "tmux_respawn_controlled",
        "argv": (
            "tmux",
            "-S",
            "/tmp/airiv-213c1.sock",
            "respawn-pane",
            "-t",
            "%7",
            "sleep",
            "30",
        ),
        "target": identity(),
        "execution_id": "EXEC-213C1",
        "permit_id": "PERMIT-213C1",
    }
    values.update(changes)
    return BoundRemediationEffect(**values)


def test_target_identity_is_immutable_and_fingerprinted():
    target = identity()
    assert target.live_eligible
    assert len(target.fingerprint) == 64

    with pytest.raises(FrozenInstanceError):
        target.pane_id = "%8"


def test_pane_id_alone_is_not_live_eligible():
    target = identity(server_generation=None)
    assert not target.live_eligible

    with pytest.raises(ValueError):
        TmuxVerificationTarget(
            pane_id=target.pane_id,
            identity=target,
            strong_identity=True,
        )


def test_same_pane_different_session_is_different_target():
    a = identity()
    b = identity(session_id="$99", session_name="other")

    assert a != b
    assert a.fingerprint != b.fingerprint


def test_bound_effect_is_immutable():
    bound = effect()

    with pytest.raises(FrozenInstanceError):
        bound.action = "different"


@pytest.mark.parametrize(
    "field,value",
    [
        ("incident_id", "INC-DIFFERENT"),
        ("component_id", "%8"),
        ("action", "other"),
        ("argv", ("tmux", "different")),
        ("target", identity(session_id="$99")),
        ("execution_id", "EXEC-DIFFERENT"),
        ("permit_id", "PERMIT-DIFFERENT"),
    ],
)
def test_bound_effect_tamper_changes_or_rejects_identity(field, value):
    original = effect()
    values = {
        "incident_id": original.incident_id,
        "component_id": original.component_id,
        "action": original.action,
        "argv": original.argv,
        "target": original.target,
        "execution_id": original.execution_id,
        "permit_id": original.permit_id,
    }
    values[field] = value

    if field in {"component_id", "target"}:
        try:
            changed = BoundRemediationEffect(**values)
        except ValueError:
            return
    else:
        changed = BoundRemediationEffect(**values)

    assert changed != original
    assert changed.fingerprint != original.fingerprint


def test_strong_verifier_checks_exact_tmux_identity(monkeypatch):
    target = identity()

    run = Mock()
    run.return_value.returncode = 0
    run.return_value.stdout = (
        "$42\tairiv-validation-213c1\t@9\t%7\t0\n"
    )
    run.return_value.stderr = ""

    monkeypatch.setattr(
        "sentinel.tmux_remediation_verifier.subprocess.run",
        run,
    )

    result = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%7",
            identity=target,
            strong_identity=True,
            timeout=5.0,
        )
    ).verify()

    assert result.verified
    assert result.observation["identity_match"] is True

    command = run.call_args.args[0]
    kwargs = run.call_args.kwargs

    assert command[:3] == [
        "tmux",
        "-S",
        "/tmp/airiv-213c1.sock",
    ]
    assert kwargs["timeout"] == 5.0
    assert kwargs["check"] is False


def test_same_pane_in_wrong_session_fails(monkeypatch):
    run = Mock()
    run.return_value.returncode = 0
    run.return_value.stdout = "$99\tunrelated\t@9\t%7\t0\n"
    run.return_value.stderr = ""

    monkeypatch.setattr(
        "sentinel.tmux_remediation_verifier.subprocess.run",
        run,
    )

    result = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%7",
            identity=identity(),
            strong_identity=True,
        )
    ).verify()

    assert not result.verified
    assert result.observation["identity_match"] is False


def test_dead_exact_target_fails_expected_alive(monkeypatch):
    run = Mock()
    run.return_value.returncode = 0
    run.return_value.stdout = (
        "$42\tairiv-validation-213c1\t@9\t%7\t1\n"
    )
    run.return_value.stderr = ""

    monkeypatch.setattr(
        "sentinel.tmux_remediation_verifier.subprocess.run",
        run,
    )

    result = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%7",
            identity=identity(),
            strong_identity=True,
        )
    ).verify()

    assert not result.verified


def test_verification_timeout_fails_closed(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(
        "sentinel.tmux_remediation_verifier.subprocess.run",
        timeout,
    )

    result = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%7",
            identity=identity(),
            strong_identity=True,
        )
    ).verify()

    assert not result.verified
    assert result.reason.startswith("verification_error:")


def test_malformed_identity_fails_closed(monkeypatch):
    run = Mock()
    run.return_value.returncode = 0
    run.return_value.stdout = "garbage\n"
    run.return_value.stderr = ""

    monkeypatch.setattr(
        "sentinel.tmux_remediation_verifier.subprocess.run",
        run,
    )

    result = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%7",
            identity=identity(),
            strong_identity=True,
        )
    ).verify()

    assert not result.verified
    assert result.reason.startswith("verification_error:")


def test_fresh_production_policy_has_no_allowed_actions(tmp_path, monkeypatch):
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

    assert runtime.policy.allowed_actions == set()
    assert (
        runtime.diagnostic.commander_semantic_policy.list_triggers()
        == ()
    )
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()
