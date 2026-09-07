"""Controlled runtime invocation surface for production systemd remediation.

Phase 2.13D.D8.9C.

This runtime-owned facade remains disabled by default.

Even when explicitly enabled in isolated tests, it may only invoke the
already-locked D8.9A dispatch gate and report whether the prepared plan
is READY_FOR_DELEGATION.

It does not import or call the D8.9B delegation boundary and therefore
cannot reach the canonical downstream execution integration.
"""

from dataclasses import dataclass
from enum import Enum

from sentinel.systemd_production_execution_dispatch_gate import (
    ProductionExecutionDispatchDecision,
    SystemdProductionExecutionDispatchGate,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)


class ProductionRuntimeInvocationState(
    str,
    Enum,
):
    BLOCKED = "BLOCKED"
    READY_FOR_DELEGATION = "READY_FOR_DELEGATION"


@dataclass(
    frozen=True,
    slots=True,
)
class ProductionRuntimeInvocationAssessment:
    state: ProductionRuntimeInvocationState
    reason: str
    dispatch_decision: (
        ProductionExecutionDispatchDecision
        | None
    )

    @property
    def ready_for_delegation(
        self,
    ) -> bool:
        return (
            self.state
            is ProductionRuntimeInvocationState
            .READY_FOR_DELEGATION
        )


class SystemdProductionRuntimeInvocationBoundary:
    """Runtime-owned fail-closed facade around the D8.9A gate."""

    def __init__(
        self,
        *,
        gate: SystemdProductionExecutionDispatchGate,
        enabled: bool = False,
    ) -> None:
        if (
            type(gate)
            is not SystemdProductionExecutionDispatchGate
        ):
            raise TypeError(
                "SystemdProductionExecutionDispatchGate required"
            )

        if type(enabled) is not bool:
            raise TypeError(
                "enabled must be bool"
            )

        self._gate = gate
        self._enabled = enabled

    @property
    def enabled(
        self,
    ) -> bool:
        return self._enabled

    @property
    def gate(
        self,
    ) -> SystemdProductionExecutionDispatchGate:
        return self._gate

    def assess_explicit(
        self,
        *,
        prepared: PreparedSystemdProductionRemediation,
        now: float,
    ) -> ProductionRuntimeInvocationAssessment:
        if (
            type(prepared)
            is not PreparedSystemdProductionRemediation
        ):
            raise TypeError(
                "PreparedSystemdProductionRemediation required"
            )

        # First independent fail-closed layer.
        #
        # When disabled we deliberately do not even invoke D8.9A.
        if not self._enabled:
            return ProductionRuntimeInvocationAssessment(
                state=(
                    ProductionRuntimeInvocationState
                    .BLOCKED
                ),
                reason=(
                    "production_runtime_invocation_disabled"
                ),
                dispatch_decision=None,
            )

        # Second independent fail-closed layer.
        decision = self._gate.assess(
            prepared=prepared,
            now=now,
        )

        if not decision.ready_for_policy:
            return ProductionRuntimeInvocationAssessment(
                state=(
                    ProductionRuntimeInvocationState
                    .BLOCKED
                ),
                reason=decision.reason,
                dispatch_decision=decision,
            )

        return ProductionRuntimeInvocationAssessment(
            state=(
                ProductionRuntimeInvocationState
                .READY_FOR_DELEGATION
            ),
            reason=(
                "ready_for_explicit_canonical_delegation"
            ),
            dispatch_decision=decision,
        )
