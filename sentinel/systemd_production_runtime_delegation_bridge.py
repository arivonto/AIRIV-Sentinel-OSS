"""Default-disabled runtime bridge to the locked delegation boundary.

Phase 2.13D.D8.9D.

SentinelRuntime owns this bridge, but it remains disabled and stores no
delegation boundary or execution integration.

An explicit caller would have to supply both objects. Runtime automatic
paths do not call this surface.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegration,
    SystemdCommanderIntegrationResult,
)
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from sentinel.systemd_production_execution_delegation import (
    SystemdProductionExecutionDelegationBoundary,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_production_runtime_invocation import (
    ProductionRuntimeInvocationAssessment,
    SystemdProductionRuntimeInvocationBoundary,
)
from sentinel.systemd_remediation_safety import (
    SystemdUnitSnapshot,
)


class ProductionRuntimeDelegationState(
    str,
    Enum,
):
    BLOCKED = "BLOCKED"
    DELEGATED_TO_CANONICAL_INTEGRATION = (
        "DELEGATED_TO_CANONICAL_INTEGRATION"
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ProductionRuntimeDelegationResult:
    state: ProductionRuntimeDelegationState
    reason: str
    invocation_assessment: (
        ProductionRuntimeInvocationAssessment
        | None
    )
    integration_result: (
        SystemdCommanderIntegrationResult
        | None
    )

    @property
    def delegated(
        self,
    ) -> bool:
        return (
            self.state
            is ProductionRuntimeDelegationState
            .DELEGATED_TO_CANONICAL_INTEGRATION
        )


class SystemdProductionRuntimeDelegationBridge:
    """Fail-closed explicit bridge; no automatic runtime ownership of effect authority."""

    def __init__(
        self,
        *,
        invocation: SystemdProductionRuntimeInvocationBoundary,
        enabled: bool = False,
    ) -> None:
        if (
            type(invocation)
            is not SystemdProductionRuntimeInvocationBoundary
        ):
            raise TypeError(
                "SystemdProductionRuntimeInvocationBoundary required"
            )

        if type(enabled) is not bool:
            raise TypeError(
                "enabled must be bool"
            )

        self._invocation = invocation
        self._enabled = enabled

    @property
    def enabled(
        self,
    ) -> bool:
        return self._enabled

    @property
    def invocation(
        self,
    ) -> SystemdProductionRuntimeInvocationBoundary:
        return self._invocation

    def invoke_explicit(
        self,
        *,
        delegation: SystemdProductionExecutionDelegationBoundary,
        integration: SystemdCommanderIntegration,
        prepared: PreparedSystemdProductionRemediation,
        incident_state: str,
        after_snapshot_provider: Callable[
            [],
            SystemdUnitSnapshot,
        ],
        production_now: float,
        timeout: float = 5.0,
        production_attempts=(),
        active_production_effects: int = 0,
        commander_authorization: SystemdProductionCommanderAuthorizationContext | None = None,
    ) -> ProductionRuntimeDelegationResult:
        if not self._enabled:
            return ProductionRuntimeDelegationResult(
                state=(
                    ProductionRuntimeDelegationState
                    .BLOCKED
                ),
                reason=(
                    "production_runtime_delegation_disabled"
                ),
                invocation_assessment=None,
                integration_result=None,
            )

        if (
            type(delegation)
            is not SystemdProductionExecutionDelegationBoundary
        ):
            raise TypeError(
                "SystemdProductionExecutionDelegationBoundary required"
            )

        if (
            type(integration)
            is not SystemdCommanderIntegration
        ):
            raise TypeError(
                "SystemdCommanderIntegration required"
            )

        if (
            type(prepared)
            is not PreparedSystemdProductionRemediation
        ):
            raise TypeError(
                "PreparedSystemdProductionRemediation required"
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
            and commander_authorization.binding.prepared is not prepared
        ):
            raise ValueError(
                "runtime_commander_authorization_prepared_mismatch"
            )

        invocation_assessment = (
            self._invocation.assess_explicit(
                prepared=prepared,
                now=production_now,
            )
        )

        if (
            not invocation_assessment.ready_for_delegation
        ):
            return ProductionRuntimeDelegationResult(
                state=(
                    ProductionRuntimeDelegationState
                    .BLOCKED
                ),
                reason=invocation_assessment.reason,
                invocation_assessment=(
                    invocation_assessment
                ),
                integration_result=None,
            )

        decision = (
            invocation_assessment
            .dispatch_decision
        )

        if (
            decision is None
            or decision.ready_for_policy is not True
        ):
            raise ValueError(
                "missing_ready_dispatch_decision"
            )

        result = delegation.delegate_for_test(
            integration=integration,
            decision=decision,
            prepared=prepared,
            incident_state=incident_state,
            after_snapshot_provider=(
                after_snapshot_provider
            ),
            production_now=production_now,
            timeout=timeout,
            production_attempts=(
                production_attempts
            ),
            active_production_effects=(
                active_production_effects
            ),
            commander_authorization=commander_authorization,
        )

        return ProductionRuntimeDelegationResult(
            state=(
                ProductionRuntimeDelegationState
                .DELEGATED_TO_CANONICAL_INTEGRATION
            ),
            reason=(
                "delegated_to_existing_canonical_integration"
            ),
            invocation_assessment=(
                invocation_assessment
            ),
            integration_result=result,
        )
