import pytest

from sentinel.remediation_verifier import (
    RemediationVerifier,
    VerificationResult,
)


def test_verified_state_produces_verified_result():
    verifier = RemediationVerifier(lambda: True)

    result = verifier.verify()

    assert isinstance(result, VerificationResult)
    assert result.verified is True
    assert result.reason == "post_remediation_state_verified"


def test_unverified_state_does_not_produce_success():
    verifier = RemediationVerifier(lambda: False)

    result = verifier.verify()

    assert result.verified is False
    assert result.reason == "post_remediation_state_not_verified"


def test_verifier_preserves_observation():
    observation = {
        "component": "test-service",
        "state": "active",
    }

    verifier = RemediationVerifier(lambda: observation)

    result = verifier.verify()

    assert result.verified is False
    assert result.observation == observation


def test_verifier_failure_is_observable():
    def failing_verifier():
        raise RuntimeError("probe failed")

    verifier = RemediationVerifier(failing_verifier)

    result = verifier.verify()

    assert result.verified is False
    assert result.reason == "verification_error: probe failed"


def test_verifier_requires_callable():
    with pytest.raises(TypeError, match="callable"):
        RemediationVerifier(None)
