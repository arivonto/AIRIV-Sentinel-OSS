"""Inert Commander authorization-context composition handoff.

D8.20 owns no approval issuance, activation consumption, consumed-activation
binding, policy decision, execution, verification, or incident lifecycle
mutation.

It validates exact Commander-path continuity from D8.16 through D8.19 and
delegates exactly one construction request to the existing D8.15
SystemdProductionCommanderAuthorizationContext.

The D8.15 context remains the sole authorization-fact constructor and owns
verification of exact durable D8.14 issuance and D8.10B consumption records.
"""

from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionStore,
)
from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer,
)
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from sentinel.systemd_production_commander_incident_continuation import (
    SystemdProductionCommanderIncidentContinuation,
)


def build_systemd_production_commander_authorization_context(
    *,
    continuation,
    binding,
    issuer,
    consumption_store,
):
    """Compose one canonical durable Commander authorization fact."""

    if (
        type(continuation)
        is not SystemdProductionCommanderIncidentContinuation
    ):
        raise TypeError(
            "canonical Commander incident continuation required"
        )

    if (
        type(binding)
        is not SystemdProductionConsumedActivationBinding
    ):
        raise TypeError(
            "canonical consumed activation binding required"
        )

    if (
        type(issuer)
        is not SystemdProductionCommanderApprovalIssuer
    ):
        raise TypeError(
            "canonical approval issuer required"
        )

    if (
        type(consumption_store)
        is not SystemdProductionActivationConsumptionStore
    ):
        raise TypeError(
            "canonical consumption store required"
        )

    # D8.16 remains the Commander-path semantic fact owner.
    continuation.__post_init__()

    grant = binding.grant
    consumption = binding.consumption
    prepared = binding.prepared

    if prepared is not continuation.prepared:
        raise ValueError(
            "commander_authorization_prepared_identity_mismatch"
        )

    if binding.approval_id != continuation.approval_id:
        raise ValueError(
            "commander_authorization_approval_id_mismatch"
        )

    if binding.incident_id != continuation.incident_id:
        raise ValueError(
            "commander_authorization_incident_id_mismatch"
        )

    if binding.component_id != continuation.component_id:
        raise ValueError(
            "commander_authorization_component_id_mismatch"
        )

    if binding.execution_id != continuation.execution_id:
        raise ValueError(
            "commander_authorization_execution_id_mismatch"
        )

    if (
        consumption.consumed_at
        < continuation.continued_at
    ):
        raise ValueError(
            "commander_authorization_consumption_precedes_continuation"
        )

    if consumption.consumed_at > binding.bound_at:
        raise ValueError(
            "commander_authorization_consumption_after_binding"
        )

    if binding.bound_at < continuation.continued_at:
        raise ValueError(
            "commander_authorization_binding_precedes_continuation"
        )

    if (
        binding.bound_at
        >= continuation.approval_expires_at
    ):
        raise ValueError(
            "commander_authorization_binding_after_approval_expiry"
        )

    approval = continuation.approval

    if grant.approval_id != approval.approval_id:
        raise ValueError(
            "commander_authorization_grant_approval_id_mismatch"
        )

    if grant.issued_at != approval.issued_at:
        raise ValueError(
            "commander_authorization_grant_issued_at_mismatch"
        )

    if grant.expires_at != approval.expires_at:
        raise ValueError(
            "commander_authorization_grant_expiry_mismatch"
        )

    # D8.15 owns:
    # - canonical binding validation
    # - reconstruction of the trusted approval fact
    # - exact durable D8.14 issuance evidence lookup
    # - exact durable D8.10B consumption evidence lookup
    # - authorization binding/freshness validation
    context = SystemdProductionCommanderAuthorizationContext(
        binding=binding,
        issuer=issuer,
        consumption_store=consumption_store,
    )

    if (
        type(context)
        is not SystemdProductionCommanderAuthorizationContext
    ):
        raise TypeError(
            "canonical Commander authorization context required"
        )

    if context.binding is not binding:
        raise ValueError(
            "returned_commander_authorization_binding_identity_mismatch"
        )

    context_approval = context.approval

    if context_approval.approval_id != approval.approval_id:
        raise ValueError(
            "returned_commander_authorization_approval_id_mismatch"
        )

    if context_approval.effect != approval.effect:
        raise ValueError(
            "returned_commander_authorization_effect_mismatch"
        )

    if context_approval.issued_at != approval.issued_at:
        raise ValueError(
            "returned_commander_authorization_issued_at_mismatch"
        )

    if context_approval.expires_at != approval.expires_at:
        raise ValueError(
            "returned_commander_authorization_expiry_mismatch"
        )

    return context
