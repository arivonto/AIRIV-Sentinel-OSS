"""Side-effect-free bounded pilot readiness composition."""

from __future__ import annotations

from sentinel.bounded_pilot_bootstrap_executor import (
    BoundedPilotBootstrapResult,
)
from sentinel.bounded_pilot_helper_manifest import (
    BoundedPilotHelperReadiness,
)
from sentinel.bounded_pilot_readiness import (
    PILOT_ACTION,
    PILOT_HELPER_ID,
    PILOT_HELPER_SUBJECT,
    PILOT_UNIT,
    BoundedPilotApproval,
    BoundedPilotHelperFacts,
    BoundedPilotRuntimeFacts,
    BoundedPilotVerificationFacts,
    BoundedPilotReadinessAssessment,
    BoundedPilotReadinessState,
    assess_bounded_pilot_readiness,
)


def compose_bounded_pilot_readiness(
    *,
    helper_readiness: BoundedPilotHelperReadiness,
    bootstrap_result: BoundedPilotBootstrapResult,
    verification: BoundedPilotVerificationFacts,
    runtime: BoundedPilotRuntimeFacts,
    approval: BoundedPilotApproval | None = None,
) -> BoundedPilotReadinessAssessment:
    """Project installed-helper facts into the canonical readiness gate."""

    if type(helper_readiness) is not BoundedPilotHelperReadiness:
        raise TypeError("BoundedPilotHelperReadiness required")
    if type(bootstrap_result) is not BoundedPilotBootstrapResult:
        raise TypeError("BoundedPilotBootstrapResult required")

    helper = BoundedPilotHelperFacts(
        helper_id=PILOT_HELPER_ID,
        unit=PILOT_UNIT,
        action=PILOT_ACTION,
        subject_system_unit=PILOT_HELPER_SUBJECT,
        accepts_only_exact_unit=True,
        accepts_only_restart=True,
        no_shell=True,
        no_provider_calls=True,
        no_external_delivery=True,
        polkit_rule_present=(
            helper_readiness.polkit_content_matches
            and helper_readiness.polkit_rule_valid
        ),
        helper_installed=(
            helper_readiness.helper_content_matches
            and helper_readiness.helper_executable
            and bootstrap_result.succeeded
        ),
    )

    assessment = assess_bounded_pilot_readiness(
        approval=approval or BoundedPilotApproval(),
        helper=helper,
        verification=verification,
        runtime=runtime,
    )

    if (
        helper_readiness.activation_ready
        and bootstrap_result.succeeded
        and assessment.ready
    ):
        return assessment

    reasons = list(assessment.reasons)
    if not helper_readiness.activation_ready:
        reasons.append("helper_readiness_not_ready")
    if not bootstrap_result.succeeded:
        reasons.append("bootstrap_not_succeeded")

    return BoundedPilotReadinessAssessment(
        state=BoundedPilotReadinessState.ACTIVATION_BLOCKED,
        reasons=tuple(dict.fromkeys(reasons)),
    )
