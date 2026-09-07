"""Explicit per-call composition for durable Commander-approved production remediation.

This Gate 2 boundary does not mutate SentinelRuntime's default-disabled
production layers. It validates canonical consumed activation and Commander
authorization continuity, creates an ephemeral enabled routing chain from the
already-locked D8.9A/D8.9C/D8.9D/D8.10D boundaries, and delegates once to the
canonical SystemdCommanderIntegration.

It owns no policy decision, durable approval/activation mutation, execution,
verification semantics, or Incident lifecycle mutation.
"""

from collections.abc import Callable

from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegration,
)
from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
)
from sentinel.systemd_production_activation_runtime_bridge import (
    ProductionActivationRuntimeResult,
    SystemdProductionActivationRuntimeBridge,
)
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from sentinel.systemd_production_execution_delegation import (
    SystemdProductionExecutionDelegationBoundary,
)
from sentinel.systemd_production_execution_dispatch_gate import (
    SystemdProductionExecutionDispatchGate,
)
from sentinel.systemd_production_runtime_delegation_bridge import (
    SystemdProductionRuntimeDelegationBridge,
)
from sentinel.systemd_production_runtime_invocation import (
    SystemdProductionRuntimeInvocationBoundary,
)
from sentinel.systemd_remediation_safety import (
    SystemdUnitSnapshot,
)


def invoke_explicit_systemd_production_runtime(
    *,
    activation_binding: SystemdProductionConsumedActivationBinding,
    authorization_context: SystemdProductionCommanderAuthorizationContext,
    integration: SystemdCommanderIntegration,
    incident_state: str,
    after_snapshot_provider: Callable[[], SystemdUnitSnapshot],
    production_now: float,
    timeout: float = 5.0,
    production_attempts=(),
    active_production_effects: int = 0,
) -> ProductionActivationRuntimeResult:
    """Compose one exact ephemeral runtime chain and delegate once."""

    if (
        type(activation_binding)
        is not SystemdProductionConsumedActivationBinding
    ):
        raise TypeError(
            "canonical consumed activation binding required"
        )

    if (
        type(authorization_context)
        is not SystemdProductionCommanderAuthorizationContext
    ):
        raise TypeError(
            "canonical Commander authorization context required"
        )

    if authorization_context.binding is not activation_binding:
        raise ValueError(
            "explicit_runtime_activation_authorization_binding_mismatch"
        )

    if type(integration) is not SystemdCommanderIntegration:
        raise TypeError(
            "canonical SystemdCommanderIntegration required"
        )

    if not callable(after_snapshot_provider):
        raise TypeError(
            "after_snapshot_provider must be callable"
        )

    # Ephemeral routing only. SentinelRuntime's stored four layers remain
    # disabled, so no automatic daemon path can inherit this enablement.
    dispatch_gate = SystemdProductionExecutionDispatchGate(
        enabled=True,
    )
    invocation = SystemdProductionRuntimeInvocationBoundary(
        gate=dispatch_gate,
        enabled=True,
    )
    runtime_bridge = SystemdProductionRuntimeDelegationBridge(
        invocation=invocation,
        enabled=True,
    )
    activation_bridge = SystemdProductionActivationRuntimeBridge(
        runtime_bridge=runtime_bridge,
        enabled=True,
    )
    delegation = SystemdProductionExecutionDelegationBoundary()

    return activation_bridge.invoke_explicit(
        activation_binding=activation_binding,
        delegation=delegation,
        integration=integration,
        incident_state=incident_state,
        after_snapshot_provider=after_snapshot_provider,
        production_now=production_now,
        timeout=timeout,
        production_attempts=production_attempts,
        active_production_effects=active_production_effects,
        commander_authorization=authorization_context,
    )
