"""Commander consumed-activation to prepared-effect binding handoff.

D8.19 owns no consumed-activation binding construction, Commander
authorization, policy decision, execution, verification, or incident
lifecycle mutation.

It validates Commander-path continuity and delegates exactly one binding
request to D8.10C bind_consumed_activation_to_prepared_effect().

D8.10C remains the sole consumed-activation to prepared-effect binding
authority.
"""

import math

from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
    bind_consumed_activation_to_prepared_effect,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionRecord,
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


def bind_systemd_production_commander_consumption_to_prepared_effect(
    *,
    continuation,
    grant,
    consumption,
    now,
):
    """Delegate exact consumed activation to canonical D8.10C binding."""

    if (
        type(continuation)
        is not SystemdProductionCommanderIncidentContinuation
    ):
        raise TypeError(
            "canonical Commander incident continuation required"
        )

    if type(grant) is not SystemdProductionActivationGrant:
        raise TypeError(
            "canonical activation grant required"
        )

    if (
        type(consumption)
        is not SystemdProductionActivationConsumptionRecord
    ):
        raise TypeError(
            "canonical activation consumption record required"
        )

    # Revalidate immutable upstream facts before crossing the D8.10C
    # binding boundary.
    continuation.__post_init__()
    grant.__post_init__()
    consumption.__post_init__()

    current = _timestamp(
        now,
        "now",
    )

    continued_at = _timestamp(
        continuation.continued_at,
        "continued_at",
    )

    consumed_at = _timestamp(
        consumption.consumed_at,
        "consumed_at",
    )

    approval_expires_at = _timestamp(
        continuation.approval_expires_at,
        "approval_expires_at",
    )

    if current < continued_at:
        raise ValueError(
            "activation_binding_time_reversal"
        )

    if consumed_at < continued_at:
        raise ValueError(
            "consumption_precedes_commander_continuation"
        )

    if consumed_at > current:
        raise ValueError(
            "consumption_timestamp_in_future_at_commander_handoff"
        )

    if current >= approval_expires_at:
        raise ValueError(
            "commander_continuation_expired_before_binding"
        )

    if not grant.is_active(current):
        raise ValueError(
            "activation_not_active_at_commander_binding_handoff"
        )

    prepared = continuation.prepared
    approval = continuation.approval
    effect = prepared.plan.effect

    if grant.approval_id != continuation.approval_id:
        raise ValueError(
            "approval_id_continuity_mismatch"
        )

    if not grant.matches_effect(
        incident_id=continuation.incident_id,
        component_id=continuation.component_id,
        execution_id=continuation.execution_id,
        effect_fingerprint=grant.effect_fingerprint,
    ):
        raise ValueError(
            "activation_effect_continuity_mismatch"
        )

    if grant.incident_id != effect.incident_id:
        raise ValueError(
            "grant_prepared_incident_id_mismatch"
        )

    if grant.component_id != effect.component_id:
        raise ValueError(
            "grant_prepared_component_id_mismatch"
        )

    if grant.execution_id != effect.execution_id:
        raise ValueError(
            "grant_prepared_execution_id_mismatch"
        )

    if (
        grant.effect_fingerprint
        != effect.fingerprint
    ):
        raise ValueError(
            "grant_prepared_effect_fingerprint_mismatch"
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

    expected = (
        (
            consumption.activation_id,
            grant.activation_id,
            "activation_id",
        ),
        (
            consumption.approval_id,
            grant.approval_id,
            "approval_id",
        ),
        (
            consumption.incident_id,
            grant.incident_id,
            "incident_id",
        ),
        (
            consumption.component_id,
            grant.component_id,
            "component_id",
        ),
        (
            consumption.execution_id,
            grant.execution_id,
            "execution_id",
        ),
        (
            consumption.effect_fingerprint,
            grant.effect_fingerprint,
            "effect_fingerprint",
        ),
        (
            consumption.grant_fingerprint,
            grant.fingerprint,
            "grant_fingerprint",
        ),
    )

    for actual, wanted, field in expected:
        if actual != wanted:
            raise ValueError(
                f"commander_consumption_{field}_continuity_mismatch"
            )

    # D8.10C owns binding construction and all canonical binding semantics:
    # activation freshness, durable record continuity, prepared-effect
    # continuity, temporal validity, and trusted-evidence freshness.
    binding = bind_consumed_activation_to_prepared_effect(
        grant=grant,
        consumption=consumption,
        prepared=prepared,
        now=current,
    )

    if (
        type(binding)
        is not SystemdProductionConsumedActivationBinding
    ):
        raise TypeError(
            "canonical consumed activation binding required"
        )

    # The canonical D8.10C function already validates its object during
    # construction.  D8.19 checks only exact handoff identity here and does
    # not create a competing binding validator.
    if binding.grant is not grant:
        raise ValueError(
            "returned_binding_grant_identity_mismatch"
        )

    if binding.consumption is not consumption:
        raise ValueError(
            "returned_binding_consumption_identity_mismatch"
        )

    if binding.prepared is not prepared:
        raise ValueError(
            "returned_binding_prepared_identity_mismatch"
        )

    if float(binding.bound_at) != current:
        raise ValueError(
            "returned_binding_timestamp_mismatch"
        )

    return binding
