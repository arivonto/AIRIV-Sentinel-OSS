"""Exact bound TMUX verification composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sentinel.live_remediation_bound_composition import (
    BoundTmuxRemediationPlan,
)
from sentinel.tmux_remediation_verifier import (
    TmuxRemediationVerifier,
)
from sentinel.tmux_server_generation_verifier import (
    TmuxServerGenerationVerification,
    TmuxServerGenerationVerifier,
)


@dataclass(
    frozen=True,
    slots=True,
)
class BoundTmuxExactVerification:
    verified: bool
    generation: TmuxServerGenerationVerification
    target_verification: Any | None
    target_fingerprint: str
    reason: str


class BoundTmuxExactVerifier:
    """Independent exact verification for one immutable bound plan."""

    def __init__(
        self,
        plan: BoundTmuxRemediationPlan,
        *,
        generation_verifier: TmuxServerGenerationVerifier | None = None,
        target_verifier=None,
    ) -> None:
        if not isinstance(
            plan,
            BoundTmuxRemediationPlan,
        ):
            raise TypeError(
                "plan must be BoundTmuxRemediationPlan"
            )

        self.plan = plan

        self.generation_verifier = (
            generation_verifier
            or TmuxServerGenerationVerifier()
        )

        self.target_verifier = (
            target_verifier
            or TmuxRemediationVerifier(
                plan.verification_target
            )
        )

    def verify_exact(
        self,
    ) -> BoundTmuxExactVerification:
        generation = (
            self.generation_verifier
            .verify(
                self.plan.target,
                timeout=(
                    self.plan
                    .verification_target
                    .timeout
                ),
            )
        )

        if not generation.verified:
            return BoundTmuxExactVerification(
                verified=False,
                generation=generation,
                target_verification=None,
                target_fingerprint=(
                    self.plan.target_fingerprint
                ),
                reason=(
                    "server_generation_not_verified"
                ),
            )

        result = (
            self.target_verifier.verify()
        )

        verified = bool(
            getattr(
                result,
                "verified",
                False,
            )
        )

        return BoundTmuxExactVerification(
            verified=verified,
            generation=generation,
            target_verification=result,
            target_fingerprint=(
                self.plan.target_fingerprint
            ),
            reason=(
                "verified"
                if verified
                else "target_identity_not_verified"
            ),
        )
