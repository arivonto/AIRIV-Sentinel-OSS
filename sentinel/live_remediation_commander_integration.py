"""Canonical strong-TMUX plan integration with Commander bound path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sentinel.bound_tmux_exact_verifier import (
    BoundTmuxExactVerifier,
)
from sentinel.live_remediation_bound_composition import (
    BoundTmuxRemediationPlan,
)


@dataclass(
    frozen=True,
    slots=True,
)
class PreparedBoundTmuxRemediation:
    """Immutable result of the single Commander authorization step."""

    plan: BoundTmuxRemediationPlan
    authorization: Any

    def __post_init__(self) -> None:
        matcher = getattr(
            self.authorization,
            "matches",
            None,
        )

        if not callable(matcher):
            raise TypeError(
                "authorization must expose matches(effect)"
            )

        if not matcher(
            self.plan.effect
        ):
            raise ValueError(
                "authorization_effect_mismatch"
            )


class BoundTmuxCommanderVerifier:
    """Adapter exposing existing verifier protocol.

    The Commander path may pass an execution result to ``verify``.
    Exact verification itself is target-bound and therefore does not
    accept caller-supplied target identity.
    """

    def __init__(
        self,
        plan: BoundTmuxRemediationPlan,
        *,
        exact_verifier=None,
    ) -> None:
        if not isinstance(
            plan,
            BoundTmuxRemediationPlan,
        ):
            raise TypeError(
                "plan must be BoundTmuxRemediationPlan"
            )

        self.plan = plan

        self._exact = (
            exact_verifier
            if exact_verifier is not None
            else BoundTmuxExactVerifier(
                plan
            )
        )

        self.calls = 0

    # PHASE_213C1E_CALLABLE_VERIFIER
    def __call__(
        self,
    ):
        return self.verify()

    def verify(
        self,
        *_args,
        **_kwargs,
    ):
        self.calls += 1

        if self.calls != 1:
            raise RuntimeError(
                "exact_verification_repeated"
            )

        result = (
            self._exact.verify_exact()
        )

        fingerprint = getattr(
            result,
            "target_fingerprint",
            None,
        )

        if (
            fingerprint
            != self.plan.target_fingerprint
        ):
            raise RuntimeError(
                "verification_target_fingerprint_mismatch"
            )

        return result


def prepare_bound_tmux_remediation(
    *,
    commander,
    incident,
    plan: BoundTmuxRemediationPlan,
) -> PreparedBoundTmuxRemediation:
    """Perform the one and only bound policy evaluation."""

    if not isinstance(
        plan,
        BoundTmuxRemediationPlan,
    ):
        raise TypeError(
            "plan must be BoundTmuxRemediationPlan"
        )

    if (
        getattr(
            incident,
            "incident_id",
            None,
        )
        != plan.effect.incident_id
    ):
        raise ValueError(
            "incident_id_plan_mismatch"
        )

    if (
        getattr(
            incident,
            "component_id",
            None,
        )
        != plan.effect.component_id
    ):
        raise ValueError(
            "component_id_plan_mismatch"
        )

    authorization = (
        commander.decide_bound_remediation(
            incident=incident,
            effect=plan.effect,
        )
    )

    return PreparedBoundTmuxRemediation(
        plan=plan,
        authorization=authorization,
    )


def execute_prepared_bound_tmux_remediation(
    *,
    commander,
    incident,
    prepared: PreparedBoundTmuxRemediation,
    exact_verifier=None,
):
    """Enter the existing canonical bound remediation path.

    No policy evaluation is performed here.
    No command/execution ID can be substituted by the caller.
    """

    if not isinstance(
        prepared,
        PreparedBoundTmuxRemediation,
    ):
        raise TypeError(
            "prepared must be PreparedBoundTmuxRemediation"
        )

    plan = prepared.plan

    if (
        incident.incident_id
        != plan.effect.incident_id
    ):
        raise ValueError(
            "incident_id_plan_mismatch"
        )

    if (
        incident.component_id
        != plan.effect.component_id
    ):
        raise ValueError(
            "component_id_plan_mismatch"
        )

    if not prepared.authorization.matches(
        plan.effect
    ):
        raise ValueError(
            "authorization_effect_mismatch"
        )

    verifier = BoundTmuxCommanderVerifier(
        plan,
        exact_verifier=exact_verifier,
    )

    result = commander.remediate_bound(
        incident=incident,
        effect=plan.effect,
        authorization=prepared.authorization,
        verifier=verifier,
        timeout=(
            plan.verification_target.timeout
        ),
    )

    if verifier.calls != 1:
        raise RuntimeError(
            "exact_verification_not_performed_once"
        )

    return result


def run_bound_tmux_remediation(
    *,
    commander,
    incident,
    plan: BoundTmuxRemediationPlan,
    exact_verifier=None,
):
    """Convenience composition preserving split decide/execute authority."""

    prepared = prepare_bound_tmux_remediation(
        commander=commander,
        incident=incident,
        plan=plan,
    )

    return execute_prepared_bound_tmux_remediation(
        commander=commander,
        incident=incident,
        prepared=prepared,
        exact_verifier=exact_verifier,
    )
