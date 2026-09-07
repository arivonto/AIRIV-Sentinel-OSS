"""AIRIV Sentinel independent remediation verification boundary."""

from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class VerificationResult:
    """Result of independently verifying post-remediation state."""

    verified: bool
    reason: str
    observation: Any = None


class RemediationVerifier:
    """
    Independent post-remediation verification boundary.

    Execution success MUST NOT be treated as remediation success.
    The verifier independently observes the resulting system state.
    """

    def __init__(self, verifier: Callable[[], Any]) -> None:
        if not callable(verifier):
            raise TypeError("verifier must be callable")

        self._verifier = verifier

    def verify(self) -> VerificationResult:
        try:
            observation = self._verifier()
        except Exception as exc:
            return VerificationResult(
                verified=False,
                reason=f"verification_error: {exc}",
                observation=None,
            )

        # Preserve an already-normalized verification result.
        # This prevents double-wrapping when an upstream verifier
        # already implements the canonical VerificationResult contract.
        if isinstance(observation, VerificationResult):
            return observation

        if (
            hasattr(observation, "verified")
            and hasattr(observation, "reason")
            and hasattr(observation, "observation")
        ):
            return VerificationResult(
                verified=bool(observation.verified),
                reason=str(observation.reason),
                observation=observation.observation,
            )

        if observation is True:
            return VerificationResult(
                verified=True,
                reason="post_remediation_state_verified",
                observation=observation,
            )

        return VerificationResult(
            verified=False,
            reason="post_remediation_state_not_verified",
            observation=observation,
        )
