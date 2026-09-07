"""Commander activation grant to durable single-use consumption handoff.

D8.18 owns no consumption-record construction, policy decision, consumed
activation binding, Commander authorization, execution, verification, or
incident lifecycle mutation.

Its sole responsibility is to revalidate exact D8.16/D8.17 continuity and
delegate exactly one irreversible consumption request to the existing D8.10B
SystemdProductionActivationConsumptionStore.

D8.10B remains the sole durable single-use consumption authority.
D8.10C binding is intentionally not performed here.
"""

import math

from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionRecord,
    SystemdProductionActivationConsumptionStore,
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


def consume_systemd_production_activation_from_commander_continuation(
    *,
    continuation,
    grant,
    consumption_store,
    now,
):
    """Delegate one exact activation to canonical durable D8.10B consumption."""

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
        type(consumption_store)
        is not SystemdProductionActivationConsumptionStore
    ):
        raise TypeError(
            "canonical activation consumption store required"
        )

    # Revalidate the immutable upstream facts before crossing the irreversible
    # D8.10B consumption boundary.
    continuation.__post_init__()
    grant.__post_init__()

    current = _timestamp(
        now,
        "now",
    )

    continued_at = _timestamp(
        continuation.continued_at,
        "continued_at",
    )

    approval_expires_at = _timestamp(
        continuation.approval_expires_at,
        "approval_expires_at",
    )

    if current < continued_at:
        raise ValueError(
            "activation_consumption_time_reversal"
        )

    if current >= approval_expires_at:
        raise ValueError(
            "commander_continuation_expired_before_consumption"
        )

    if not grant.is_active(current):
        raise ValueError(
            "activation_not_active_at_consumption_handoff"
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

    # D8.10B owns eligibility assessment, durable O_EXCL reservation,
    # crash-safe conservative single-use semantics, record construction,
    # persistence, and replay denial.
    record = consumption_store.consume(
        grant=grant,
        now=current,
        incident_id=continuation.incident_id,
        component_id=continuation.component_id,
        execution_id=continuation.execution_id,
        effect_fingerprint=effect.effect_fingerprint,
    )

    if (
        type(record)
        is not SystemdProductionActivationConsumptionRecord
    ):
        raise TypeError(
            "canonical activation consumption record required"
        )

    record.__post_init__()

    if record.activation_id != grant.activation_id:
        raise ValueError(
            "consumption_activation_id_continuity_mismatch"
        )

    if record.approval_id != grant.approval_id:
        raise ValueError(
            "consumption_approval_id_continuity_mismatch"
        )

    if record.incident_id != grant.incident_id:
        raise ValueError(
            "consumption_incident_id_continuity_mismatch"
        )

    if record.component_id != grant.component_id:
        raise ValueError(
            "consumption_component_id_continuity_mismatch"
        )

    if record.execution_id != grant.execution_id:
        raise ValueError(
            "consumption_execution_id_continuity_mismatch"
        )

    if record.effect_fingerprint != grant.effect_fingerprint:
        raise ValueError(
            "consumption_effect_fingerprint_continuity_mismatch"
        )

    if record.grant_fingerprint != grant.fingerprint:
        raise ValueError(
            "consumption_grant_fingerprint_continuity_mismatch"
        )

    if float(record.consumed_at) != current:
        raise ValueError(
            "consumption_timestamp_continuity_mismatch"
        )

    return record
