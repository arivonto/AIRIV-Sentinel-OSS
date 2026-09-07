"""Exact durable-consumption to prepared-effect binding.

Phase 2.13D.D8.10C.

This module proves continuity between:

    D8.10A activation grant
        ->
    D8.10B durable consumption record
        ->
    D8.8B prepared production remediation

It performs no persistence, policy evaluation, runtime activation,
delegation, permit claim, effect execution, verification, or incident
lifecycle mutation.
"""

from dataclasses import dataclass
import math

from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
)
from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionRecord,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)


def _time(
    value,
    name,
):
    if (
        type(value) not in (
            int,
            float,
        )
        or not math.isfinite(
            value
        )
        or value < 0
    ):
        raise ValueError(
            f"{name} must be finite and non-negative"
        )

    return float(
        value
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdProductionConsumedActivationBinding:
    grant: SystemdProductionActivationGrant
    consumption: SystemdProductionActivationConsumptionRecord
    prepared: PreparedSystemdProductionRemediation
    bound_at: float

    def __post_init__(
        self,
    ) -> None:
        if (
            type(self.grant)
            is not SystemdProductionActivationGrant
        ):
            raise TypeError(
                "SystemdProductionActivationGrant required"
            )

        if (
            type(self.consumption)
            is not SystemdProductionActivationConsumptionRecord
        ):
            raise TypeError(
                "SystemdProductionActivationConsumptionRecord required"
            )

        if (
            type(self.prepared)
            is not PreparedSystemdProductionRemediation
        ):
            raise TypeError(
                "PreparedSystemdProductionRemediation required"
            )

        now = _time(
            self.bound_at,
            "bound_at",
        )

        plan = self.prepared.plan
        binding = self.prepared.binding

        if (
            type(plan)
            is not BoundSystemdRemediationPlan
        ):
            raise TypeError(
                "canonical BoundSystemdRemediationPlan required"
            )

        if (
            type(binding)
            is not TrustedSystemdDispatchEvidenceBinding
        ):
            raise TypeError(
                "TrustedSystemdDispatchEvidenceBinding required"
            )

        # Activation must remain live at the actual handoff-binding time.
        if not self.grant.is_active(
            now
        ):
            raise ValueError(
                "activation_not_active_at_prepared_binding"
            )

        # Durable consumption itself must have happened inside the grant
        # validity interval and cannot come from the future.
        if not (
            self.grant.issued_at
            <= self.consumption.consumed_at
            < self.grant.expires_at
        ):
            raise ValueError(
                "consumption_timestamp_outside_activation_window"
            )

        if (
            self.consumption.consumed_at
            > now
        ):
            raise ValueError(
                "consumption_timestamp_in_future"
            )

        # Exact immutable grant -> durable record continuity.
        expected = (
            (
                self.consumption.activation_id,
                self.grant.activation_id,
                "activation_id",
            ),
            (
                self.consumption.approval_id,
                self.grant.approval_id,
                "approval_id",
            ),
            (
                self.consumption.incident_id,
                self.grant.incident_id,
                "incident_id",
            ),
            (
                self.consumption.component_id,
                self.grant.component_id,
                "component_id",
            ),
            (
                self.consumption.execution_id,
                self.grant.execution_id,
                "execution_id",
            ),
            (
                self.consumption.effect_fingerprint,
                self.grant.effect_fingerprint,
                "effect_fingerprint",
            ),
            (
                self.consumption.grant_fingerprint,
                self.grant.fingerprint,
                "grant_fingerprint",
            ),
        )

        for actual, wanted, field in expected:
            if actual != wanted:
                raise ValueError(
                    f"activation_consumption_{field}_mismatch"
                )

        effect = plan.effect

        # Exact durable record -> prepared effect continuity.
        prepared_expected = (
            (
                self.consumption.incident_id,
                effect.incident_id,
                "incident_id",
            ),
            (
                self.consumption.component_id,
                effect.component_id,
                "component_id",
            ),
            (
                self.consumption.execution_id,
                effect.execution_id,
                "execution_id",
            ),
            (
                self.consumption.effect_fingerprint,
                effect.fingerprint,
                "effect_fingerprint",
            ),
        )

        for consumed, prepared_value, field in prepared_expected:
            if consumed != prepared_value:
                raise ValueError(
                    f"consumption_prepared_{field}_mismatch"
                )

        # Reuse canonical evidence freshness semantics rather than inventing
        # another freshness authority.
        if not binding.is_fresh(
            now
        ):
            raise ValueError(
                "trusted_evidence_stale_at_activation_binding"
            )

    @property
    def activation_id(
        self,
    ) -> str:
        return self.grant.activation_id

    @property
    def approval_id(
        self,
    ) -> str:
        return self.grant.approval_id

    @property
    def incident_id(
        self,
    ) -> str:
        return self.consumption.incident_id

    @property
    def component_id(
        self,
    ) -> str:
        return self.consumption.component_id

    @property
    def execution_id(
        self,
    ) -> str:
        return self.consumption.execution_id

    @property
    def effect_fingerprint(
        self,
    ) -> str:
        return self.consumption.effect_fingerprint

    @property
    def grant_fingerprint(
        self,
    ) -> str:
        return self.consumption.grant_fingerprint

    def is_current(
        self,
        now,
    ) -> bool:
        current = _time(
            now,
            "now",
        )

        if current < self.bound_at:
            return False

        return (
            self.grant.is_active(
                current
            )
            and self.prepared.binding.is_fresh(
                current
            )
        )


def bind_consumed_activation_to_prepared_effect(
    *,
    grant,
    consumption,
    prepared,
    now,
):
    return SystemdProductionConsumedActivationBinding(
        grant=grant,
        consumption=consumption,
        prepared=prepared,
        bound_at=_time(
            now,
            "now",
        ),
    )
