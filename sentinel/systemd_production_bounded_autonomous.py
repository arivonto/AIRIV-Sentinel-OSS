"""Default-disabled bounded autonomous production-systemd composition.

Gate 4 foundation.

This module does not create Commander approval evidence and never accepts a
Commander authorization context. When explicitly enabled by trusted
composition, it exposes exactly one prepared effect to the existing canonical
production pipeline. RemediationPolicy remains the sole ALLOW/DENY authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from sentinel.live_remediation_activation_lease import (
    TemporaryLiveRemediationActivationLease,
)
from sentinel.remediation_action_catalog import (
    RemediationActionCatalog,
    RemediationActionEntry,
)
from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegration,
)
from sentinel.systemd_production_execution_delegation import (
    SystemdProductionExecutionDelegationBoundary,
)
from sentinel.systemd_production_execution_dispatch_gate import (
    SystemdProductionExecutionDispatchGate,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_production_runtime_delegation_bridge import (
    ProductionRuntimeDelegationResult,
    SystemdProductionRuntimeDelegationBridge,
)
from sentinel.systemd_production_runtime_invocation import (
    SystemdProductionRuntimeInvocationBoundary,
)
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    ProductionTargetMode,
    SystemdProductionTargetPolicy,
    SystemdProductionTargetRule,
)
from sentinel.systemd_remediation_safety import SystemdUnitSnapshot


UNIT = "airiv-sentinel-production-remediation-probe.service"
COMPONENT = "systemd:" + UNIT
ACTION = "systemd_restart"
ARGV = (
    "/usr/bin/systemctl",
    "--no-ask-password",
    "restart",
    UNIT,
)


def _positive(value, name):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


@dataclass(frozen=True, slots=True)
class BoundedAutonomousSystemdCapability:
    """Trusted composition facts for the single Gate 4 target."""

    enabled: bool = False
    unit: str = UNIT
    cooldown_seconds: float = 3600.0
    retry_window_seconds: float = 86400.0
    max_attempts_per_window: int = 1

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if self.unit != UNIT:
            raise ValueError("gate4_exact_probe_target_required")
        _positive(self.cooldown_seconds, "cooldown_seconds")
        _positive(self.retry_window_seconds, "retry_window_seconds")
        if (
            type(self.max_attempts_per_window) is not int
            or self.max_attempts_per_window <= 0
        ):
            raise ValueError("max_attempts_per_window must be positive int")

        # Reuse the canonical target-policy validator for every capability fact.
        self.target_rule

    @property
    def target_rule(self):
        return SystemdProductionTargetRule(
            unit=self.unit,
            mode=ProductionTargetMode.AUTONOMOUS,
            cooldown_seconds=float(self.cooldown_seconds),
            retry_window_seconds=float(self.retry_window_seconds),
            max_attempts_per_window=self.max_attempts_per_window,
        )

    @property
    def target_policy(self):
        return SystemdProductionTargetPolicy([self.target_rule])


class BoundedAutonomousInvocationState(str, Enum):
    BLOCKED = "BLOCKED"
    DELEGATED_TO_CANONICAL_PRODUCTION_PIPELINE = (
        "DELEGATED_TO_CANONICAL_PRODUCTION_PIPELINE"
    )


@dataclass(frozen=True, slots=True)
class BoundedAutonomousInvocationResult:
    state: BoundedAutonomousInvocationState
    reason: str
    runtime_result: ProductionRuntimeDelegationResult | None

    @property
    def delegated(self):
        return (
            self.state
            is BoundedAutonomousInvocationState
            .DELEGATED_TO_CANONICAL_PRODUCTION_PIPELINE
        )


def _validate_exact_prepared(prepared):
    if type(prepared) is not PreparedSystemdProductionRemediation:
        raise TypeError("PreparedSystemdProductionRemediation required")

    plan = prepared.plan
    effect = plan.effect
    before = plan.before

    if type(before) is not SystemdUnitSnapshot:
        raise TypeError("canonical systemd pre-snapshot required")
    if before.identity.unit_name != UNIT:
        raise ValueError("gate4_prepared_target_mismatch")
    if before.identity.component_id != COMPONENT:
        raise ValueError("gate4_prepared_component_mismatch")
    if not before.identity.live_eligible:
        raise ValueError("gate4_target_not_live_eligible")
    if before.load_state != "loaded":
        raise ValueError("gate4_target_not_loaded")
    if effect.component_id != COMPONENT:
        raise ValueError("gate4_effect_component_mismatch")
    if effect.action != ACTION:
        raise ValueError("gate4_effect_action_mismatch")
    if tuple(effect.argv) != ARGV:
        raise ValueError("gate4_effect_argv_mismatch")
    if effect.target.fingerprint != before.identity.fingerprint:
        raise ValueError("gate4_effect_target_mismatch")
    if not plan.permit_binding.matches(effect):
        raise ValueError("gate4_prepared_permit_binding_mismatch")

    return effect


def invoke_bounded_autonomous_systemd_production(
    *,
    capability: BoundedAutonomousSystemdCapability,
    integration: SystemdCommanderIntegration,
    catalog: RemediationActionCatalog,
    prepared: PreparedSystemdProductionRemediation,
    incident_state: str,
    after_snapshot_provider,
    production_now: float,
    timeout: float = 5.0,
    production_attempts=(),
    active_production_effects: int = 0,
) -> BoundedAutonomousInvocationResult:
    """Delegate one exact autonomous candidate without Commander evidence."""

    if type(capability) is not BoundedAutonomousSystemdCapability:
        raise TypeError("BoundedAutonomousSystemdCapability required")
    if type(integration) is not SystemdCommanderIntegration:
        raise TypeError("SystemdCommanderIntegration required")
    if type(catalog) is not RemediationActionCatalog:
        raise TypeError("RemediationActionCatalog required")
    if not callable(after_snapshot_provider):
        raise TypeError("after_snapshot_provider must be callable")
    if (
        type(production_now) not in (int, float)
        or not math.isfinite(production_now)
        or production_now < 0
    ):
        raise ValueError("production_now must be finite and non-negative")

    effect = _validate_exact_prepared(prepared)

    if not capability.enabled:
        return BoundedAutonomousInvocationResult(
            state=BoundedAutonomousInvocationState.BLOCKED,
            reason="gate4_bounded_autonomous_disabled",
            runtime_result=None,
        )

    policy = integration.policy

    # Do not overwrite or inherit another production activation scope.
    if policy.list_systemd_production_targets():
        return BoundedAutonomousInvocationResult(
            state=BoundedAutonomousInvocationState.BLOCKED,
            reason="gate4_existing_production_target_policy",
            runtime_result=None,
        )

    entry = RemediationActionEntry(
        action=effect.action,
        command=" ".join(effect.argv),
        rationale="Gate 4 bounded autonomous exact-probe remediation.",
    )

    lease = TemporaryLiveRemediationActivationLease(
        policy=policy,
        catalog=catalog,
        effect=effect,
        entry=entry,
    )

    dispatch_gate = SystemdProductionExecutionDispatchGate(enabled=True)
    invocation = SystemdProductionRuntimeInvocationBoundary(
        gate=dispatch_gate,
        enabled=True,
    )
    runtime_bridge = SystemdProductionRuntimeDelegationBridge(
        invocation=invocation,
        enabled=True,
    )
    delegation = SystemdProductionExecutionDelegationBoundary()

    with lease:
        policy.configure_systemd_production_target_policy(
            capability.target_policy
        )
        try:
            result = runtime_bridge.invoke_explicit(
                delegation=delegation,
                integration=integration,
                prepared=prepared,
                incident_state=incident_state,
                after_snapshot_provider=after_snapshot_provider,
                production_now=float(production_now),
                timeout=timeout,
                production_attempts=production_attempts,
                active_production_effects=active_production_effects,
                commander_authorization=None,
            )
        finally:
            policy.clear_systemd_production_target_policy()

    if policy.list_systemd_production_targets():
        raise RuntimeError("gate4_production_target_policy_cleanup_failed")

    return BoundedAutonomousInvocationResult(
        state=(
            BoundedAutonomousInvocationState
            .DELEGATED_TO_CANONICAL_PRODUCTION_PIPELINE
        ),
        reason="gate4_delegated_without_commander_authorization",
        runtime_result=result,
    )
