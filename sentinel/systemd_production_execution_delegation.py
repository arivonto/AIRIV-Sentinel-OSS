"""Explicit production-systemd canonical execution delegation boundary.

Phase 2.13D.D8.9B.

This surface exists only for isolated/test-driven composition validation.
It is intentionally not wired into SentinelRuntime or any daemon path.

It owns no policy, permit, execution, verification, or lifecycle
authority. Those remain inside the existing SystemdCommanderIntegration.
"""

from collections.abc import Callable

from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
)
from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegration,
    SystemdCommanderIntegrationResult,
)
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from sentinel.systemd_production_execution_dispatch_gate import (
    ProductionExecutionDispatchDecision,
    ProductionExecutionDispatchState,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_remediation_safety import (
    SystemdUnitSnapshot,
)


class SystemdProductionExecutionDelegationBoundary:
    """Validate exact READY decision continuity, then delegate exactly once."""

    def delegate_for_test(
        self,
        *,
        integration: SystemdCommanderIntegration,
        decision: ProductionExecutionDispatchDecision,
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
    ) -> SystemdCommanderIntegrationResult:
        if (
            type(integration)
            is not SystemdCommanderIntegration
        ):
            raise TypeError(
                "SystemdCommanderIntegration required"
            )

        if (
            type(decision)
            is not ProductionExecutionDispatchDecision
        ):
            raise TypeError(
                "ProductionExecutionDispatchDecision required"
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
            decision.state
            is not ProductionExecutionDispatchState.READY_FOR_POLICY
            or decision.ready_for_policy is not True
        ):
            raise ValueError(
                "production_dispatch_not_ready_for_policy"
            )

        plan = prepared.plan

        if (
            type(plan)
            is not BoundSystemdRemediationPlan
        ):
            raise TypeError(
                "canonical BoundSystemdRemediationPlan required"
            )

        # Reuse D8.7A.1 freshness authority immediately before delegation.
        if not prepared.binding.is_fresh(
            production_now
        ):
            raise ValueError(
                "trusted_evidence_stale_at_execution_delegation"
            )

        if (
            decision.incident_id
            != plan.effect.incident_id
        ):
            raise ValueError(
                "dispatch_incident_id_mismatch"
            )

        if (
            decision.component_id
            != plan.effect.component_id
        ):
            raise ValueError(
                "dispatch_component_id_mismatch"
            )

        if (
            decision.execution_id
            != plan.effect.execution_id
        ):
            raise ValueError(
                "dispatch_execution_id_mismatch"
            )

        if (
            decision.effect_fingerprint
            != plan.effect.fingerprint
        ):
            raise ValueError(
                "dispatch_effect_fingerprint_mismatch"
            )

        if not plan.permit_binding.matches(
            plan.effect
        ):
            raise ValueError(
                "prepared_permit_binding_mismatch"
            )

        if (
            commander_authorization is not None
            and commander_authorization.binding.prepared is not prepared
        ):
            raise ValueError(
                "commander_authorization_prepared_identity_mismatch"
            )

        # Sole delegation point.
        #
        # SystemdCommanderIntegration remains responsible for:
        # - canonical production policy evaluation;
        # - D8.4 runtime guard / attempt ledger / production lease;
        # - permit adapter;
        # - execution;
        # - verification.
        return integration.execute_verified(
            plan=plan,
            incident_state=incident_state,
            after_snapshot_provider=after_snapshot_provider,
            timeout=timeout,
            production_now=production_now,
            production_attempts=production_attempts,
            active_production_effects=active_production_effects,
            commander_authorization=commander_authorization,
        )
