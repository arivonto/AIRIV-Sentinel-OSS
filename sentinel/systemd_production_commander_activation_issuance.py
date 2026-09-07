"""Commander-only continuation to durable activation issuance.

D8.17 owns no activation-grant construction, policy decision, activation
consumption, execution, verification, or incident lifecycle mutation.

Its sole responsibility is to validate temporal continuity from the inert
D8.16 Commander incident continuation and delegate exactly one durable
issuance request to the existing D8.14 issuer.

D8.14 remains the sole durable approval-level single-use issuer and the sole
production construction path for SystemdProductionActivationGrant.
"""

import math

from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer,
)
from sentinel.systemd_production_commander_incident_continuation import (
    SystemdProductionCommanderIncidentContinuation,
)


def _timestamp(value, field):
    if type(value) not in (int, float):
        raise TypeError(
            f"{field} must be numeric"
        )

    value = float(value)

    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"{field} must be finite and non-negative"
        )

    return value


def issue_systemd_production_activation_from_commander_continuation(
    *,
    continuation,
    issuer,
    activation_id,
    now,
):
    """Delegate one exact continuation to the canonical D8.14 issuer."""

    if (
        type(continuation)
        is not SystemdProductionCommanderIncidentContinuation
    ):
        raise TypeError(
            "canonical Commander incident continuation required"
        )

    if (
        type(issuer)
        is not SystemdProductionCommanderApprovalIssuer
    ):
        raise TypeError(
            "canonical Commander approval issuer required"
        )

    # Revalidate the immutable D8.16 fact before crossing into durable
    # issuance.  This does not create new semantic ownership.
    continuation.__post_init__()

    current = _timestamp(
        now,
        "now",
    )

    continued_at = _timestamp(
        continuation.continued_at,
        "continued_at",
    )

    expires_at = _timestamp(
        continuation.approval_expires_at,
        "approval_expires_at",
    )

    if current < continued_at:
        raise ValueError(
            "continuation_time_reversal"
        )

    if current >= expires_at:
        raise ValueError(
            "commander_continuation_expired"
        )

    approval = continuation.approval
    prepared = continuation.prepared

    # D8.14 owns durable reservation, approval-level single use,
    # persistence, and SystemdProductionActivationGrant construction.
    grant = issuer.issue(
        approval=approval,
        prepared=prepared,
        activation_id=activation_id,
        now=current,
    )

    if type(grant) is not SystemdProductionActivationGrant:
        raise TypeError(
            "canonical activation grant required"
        )

    grant.__post_init__()

    effect = prepared.plan.effect

    if grant.activation_id != activation_id:
        raise ValueError(
            "activation_id_continuity_mismatch"
        )

    if grant.approval_id != continuation.approval_id:
        raise ValueError(
            "approval_id_continuity_mismatch"
        )

    if not grant.matches_effect(
        incident_id=continuation.incident_id,
        component_id=continuation.component_id,
        execution_id=continuation.execution_id,
        effect_fingerprint=effect.effect_fingerprint,
    ):
        raise ValueError(
            "activation_effect_continuity_mismatch"
        )

    if (
        float(grant.issued_at)
        != float(approval.issued_at)
    ):
        raise ValueError(
            "activation_issued_at_continuity_mismatch"
        )

    if (
        float(grant.expires_at)
        != float(approval.expires_at)
    ):
        raise ValueError(
            "activation_expiry_continuity_mismatch"
        )

    return grant
