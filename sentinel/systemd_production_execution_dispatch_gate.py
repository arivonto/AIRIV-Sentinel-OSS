"""Default-disabled production systemd execution-dispatch gate.

Phase 2.13D.D8.9A.

This boundary decides only whether an already-prepared canonical plan
may proceed to the downstream *policy evaluation stage*.

READY_FOR_POLICY is NOT remediation authorization.

This module never evaluates policy and never executes.
"""

import math
from dataclasses import dataclass
from enum import Enum

from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
)
from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)


class ProductionExecutionDispatchState(
    str,
    Enum,
):
    BLOCKED = "BLOCKED"
    READY_FOR_POLICY = "READY_FOR_POLICY"


@dataclass(
    frozen=True,
    slots=True,
)
class ProductionExecutionDispatchDecision:
    state: ProductionExecutionDispatchState
    reason: str
    incident_id: str | None
    component_id: str | None
    execution_id: str | None
    effect_fingerprint: str | None

    @property
    def ready_for_policy(
        self,
    ) -> bool:
        return (
            self.state
            is ProductionExecutionDispatchState.READY_FOR_POLICY
        )


class SystemdProductionExecutionDispatchGate:
    """Pure, side-effect-free pre-policy execution-dispatch gate."""

    def __init__(
        self,
        *,
        enabled: bool = False,
    ) -> None:
        if type(enabled) is not bool:
            raise TypeError(
                "enabled must be bool"
            )

        self._enabled = enabled

    @property
    def enabled(
        self,
    ) -> bool:
        return self._enabled

    def assess(
        self,
        *,
        prepared: PreparedSystemdProductionRemediation,
        now: float,
    ) -> ProductionExecutionDispatchDecision:
        if (
            type(prepared)
            is not PreparedSystemdProductionRemediation
        ):
            raise TypeError(
                "PreparedSystemdProductionRemediation required"
            )

        if (
            type(now) not in (int, float)
            or not math.isfinite(now)
            or now < 0
        ):
            raise ValueError(
                "now must be finite and non-negative"
            )

        if (
            type(prepared.binding)
            is not TrustedSystemdDispatchEvidenceBinding
        ):
            raise TypeError(
                "trusted dispatch/evidence binding required"
            )

        if (
            type(prepared.plan)
            is not BoundSystemdRemediationPlan
        ):
            raise TypeError(
                "canonical BoundSystemdRemediationPlan required"
            )

        if (
            type(prepared.prepared_at)
            not in (int, float)
            or not math.isfinite(
                prepared.prepared_at
            )
            or prepared.prepared_at < 0
            or prepared.prepared_at > now
        ):
            raise ValueError(
                "invalid preparation timestamp"
            )

        binding = prepared.binding
        plan = prepared.plan
        evidence = binding.evidence
        snapshot = evidence.snapshot

        # D8.7A.1 remains the freshness authority.
        if not binding.is_fresh(
            now
        ):
            return self._blocked(
                plan=plan,
                reason="trusted_evidence_stale",
            )

        # Fail closed against hand-built/substituted Prepared objects.
        if (
            plan.before
            != snapshot
        ):
            raise ValueError(
                "prepared_snapshot_binding_mismatch"
            )

        if (
            plan.before.identity.fingerprint
            != snapshot.identity.fingerprint
        ):
            raise ValueError(
                "prepared_target_fingerprint_mismatch"
            )

        if (
            plan.before.invocation_id
            != snapshot.invocation_id
        ):
            raise ValueError(
                "prepared_invocation_id_mismatch"
            )

        if (
            plan.effect.incident_id
            != evidence.incident_id
        ):
            raise ValueError(
                "prepared_incident_id_mismatch"
            )

        if (
            plan.effect.component_id
            != evidence.component_id
        ):
            raise ValueError(
                "prepared_component_id_mismatch"
            )

        if (
            plan.effect.target_fingerprint
            != snapshot.identity.fingerprint
        ):
            raise ValueError(
                "prepared_effect_target_mismatch"
            )

        if not plan.permit_binding.matches(
            plan.effect
        ):
            raise ValueError(
                "prepared_permit_binding_mismatch"
            )

        if not self._enabled:
            return self._blocked(
                plan=plan,
                reason="production_execution_dispatch_disabled",
            )

        return ProductionExecutionDispatchDecision(
            state=(
                ProductionExecutionDispatchState
                .READY_FOR_POLICY
            ),
            reason=(
                "ready_for_downstream_canonical_policy_evaluation"
            ),
            incident_id=plan.effect.incident_id,
            component_id=plan.effect.component_id,
            execution_id=plan.effect.execution_id,
            effect_fingerprint=(
                plan.effect.fingerprint
            ),
        )

    @staticmethod
    def _blocked(
        *,
        plan: BoundSystemdRemediationPlan,
        reason: str,
    ) -> ProductionExecutionDispatchDecision:
        return ProductionExecutionDispatchDecision(
            state=(
                ProductionExecutionDispatchState
                .BLOCKED
            ),
            reason=reason,
            incident_id=plan.effect.incident_id,
            component_id=plan.effect.component_id,
            execution_id=plan.effect.execution_id,
            effect_fingerprint=(
                plan.effect.fingerprint
            ),
        )
