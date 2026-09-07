from unittest.mock import patch

from sentinel.remediation_verifier import VerificationResult
from sentinel.tmux_remediation_verifier import (
    TmuxRemediationVerifier,
    TmuxVerificationTarget,
)


def test_alive_pane_is_verified():
    verifier = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%1",
            expected_alive=True,
        )
    )

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "0\n"
        run.return_value.stderr = ""

        result = verifier.verify()

    assert isinstance(result, VerificationResult)
    assert result.verified is True
    assert result.reason == "post_remediation_tmux_state_verified"


def test_dead_pane_fails_alive_expectation():
    verifier = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%1",
            expected_alive=True,
        )
    )

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "1\n"
        run.return_value.stderr = ""

        result = verifier.verify()

    assert result.verified is False
    assert result.reason == "post_remediation_tmux_state_not_verified"


def test_dead_pane_can_be_verified_when_expected():
    verifier = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%1",
            expected_alive=False,
        )
    )

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "1\n"
        run.return_value.stderr = ""

        result = verifier.verify()

    assert result.verified is True


def test_tmux_observation_error_is_not_verification_success():
    verifier = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%1",
            expected_alive=True,
        )
    )

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "no such pane"

        result = verifier.verify()

    assert result.verified is False
    assert result.reason.startswith("verification_error:")
    assert result.observation["capture_ok"] is False


def test_invalid_tmux_state_is_verification_error():
    verifier = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%1",
            expected_alive=True,
        )
    )

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "unknown\n"
        run.return_value.stderr = ""

        result = verifier.verify()

    assert result.verified is False
    assert result.reason.startswith("verification_error:")
