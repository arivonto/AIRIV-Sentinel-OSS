"""Default-disabled activation-aware production runtime bridge.

Phase 2.13D.D8.10D.

This layer requires an already-created D8.10C consumed-activation
binding and rechecks that binding at the invocation time.

It does not create or consume activation grants.

When explicitly enabled, it delegates routing once to the existing D8.9D
runtime bridge. Production runtime composition remains disabled by default.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math

from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegration,
)
from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
)
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from sentinel.systemd_production_execution_delegation import (
    SystemdProductionExecutionDelegationBoundary,
)
from sentinel.systemd_production_runtime_delegation_bridge import (
    ProductionRuntimeDelegationResult,
    SystemdProductionRuntimeDelegationBridge,
)
from sentinel.systemd_remediation_safety import (
    SystemdUnitSnapshot,
)


def _time(value):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            "production_now must be finite and non-negative"
        )
    return float(value)


class ProductionActivationRuntimeState(str, Enum):
    BLOCKED = "BLOCKED"
    DELEGATED_TO_RUNTIME_BRIDGE = "DELEGATED_TO_RUNTIME_BRIDGE"


@dataclass(frozen=True, slots=True)
class ProductionActivationRuntimeResult:
    state: ProductionActivationRuntimeState
    reason: str
    activation_id: str | None
    approval_id: str | None
    runtime_delegation_result: ProductionRuntimeDelegationResult | None

    @property
    def delegated(self) -> bool:
        return (
            self.state
            is ProductionActivationRuntimeState.DELEGATED_TO_RUNTIME_BRIDGE
        )


class SystemdProductionActivationRuntimeBridge:
    """Fourth fail-closed runtime layer."""

    def __init__(
        self,
        *,
        runtime_bridge: SystemdProductionRuntimeDelegationBridge,
        enabled: bool = False,
    ):
        if type(runtime_bridge) is not SystemdProductionRuntimeDelegationBridge:
            raise TypeError(
                "SystemdProductionRuntimeDelegationBridge required"
            )
        if type(enabled) is not bool:
            raise TypeError("enabled must be bool")
        self._runtime_bridge = runtime_bridge
        self._enabled = enabled

    @property
    def enabled(self):
        return self._enabled

    @property
    def runtime_bridge(self):
        return self._runtime_bridge

    def invoke_explicit(
        self,
        *,
        activation_binding: SystemdProductionConsumedActivationBinding,
        delegation: SystemdProductionExecutionDelegationBoundary,
        integration: SystemdCommanderIntegration,
        incident_state: str,
        after_snapshot_provider: Callable[[], SystemdUnitSnapshot],
        production_now: float,
        timeout: float = 5.0,
        production_attempts=(),
        active_production_effects: int = 0,
        commander_authorization: SystemdProductionCommanderAuthorizationContext | None = None,
    ) -> ProductionActivationRuntimeResult:
        if not self._enabled:
            return ProductionActivationRuntimeResult(
                state=ProductionActivationRuntimeState.BLOCKED,
                reason="production_activation_runtime_bridge_disabled",
                activation_id=None,
                approval_id=None,
                runtime_delegation_result=None,
            )

        if type(activation_binding) is not SystemdProductionConsumedActivationBinding:
            raise TypeError(
                "SystemdProductionConsumedActivationBinding required"
            )

        if (
            commander_authorization is not None
            and type(commander_authorization)
            is not SystemdProductionCommanderAuthorizationContext
        ):
            raise TypeError(
                "canonical Commander authorization context required"
            )

        if (
            commander_authorization is not None
            and commander_authorization.binding is not activation_binding
        ):
            raise ValueError(
                "activation_runtime_commander_authorization_binding_mismatch"
            )

        now = _time(production_now)

        if not activation_binding.is_current(now):
            return ProductionActivationRuntimeResult(
                state=ProductionActivationRuntimeState.BLOCKED,
                reason="consumed_activation_binding_not_current",
                activation_id=activation_binding.activation_id,
                approval_id=activation_binding.approval_id,
                runtime_delegation_result=None,
            )

        result = self._runtime_bridge.invoke_explicit(
            delegation=delegation,
            integration=integration,
            prepared=activation_binding.prepared,
            incident_state=incident_state,
            after_snapshot_provider=after_snapshot_provider,
            production_now=now,
            timeout=timeout,
            production_attempts=production_attempts,
            active_production_effects=active_production_effects,
            commander_authorization=commander_authorization,
        )

        return ProductionActivationRuntimeResult(
            state=ProductionActivationRuntimeState.DELEGATED_TO_RUNTIME_BRIDGE,
            reason="delegated_to_existing_runtime_bridge",
            activation_id=activation_binding.activation_id,
            approval_id=activation_binding.approval_id,
            runtime_delegation_result=result,
        )
