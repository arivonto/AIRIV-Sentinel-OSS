"""AIRIV Sentinel remediation authorization boundary."""

from __future__ import annotations

from sentinel.bound_effect_contract import (
    bound_effect_policy_run_id,
    validate_bound_effect_contract,
)


from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentinel.systemd_production_commander_authorization import (
        SystemdProductionCommanderAuthorizationContext,
    )


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class RemediationRequest:
    incident_state: str
    component_id: str
    action: str


@dataclass(frozen=True)
class RemediationDecision:
    decision: PolicyDecision
    reason: str
    incident_state: str
    component_id: str
    action: str


class RemediationPolicy:
    """Explicit remediation authorization gate."""

    def __init__(self, allowed_actions: set[str] | None = None) -> None:
        self.allowed_actions = allowed_actions or set()

    def evaluate(self, request: RemediationRequest) -> RemediationDecision:
        if request.action not in self.allowed_actions:
            return RemediationDecision(
                decision=PolicyDecision.DENY,
                reason="action_not_authorized",
                incident_state=request.incident_state,
                component_id=request.component_id,
                action=request.action,
            )

        return RemediationDecision(
            decision=PolicyDecision.ALLOW,
            reason="action_authorized",
            incident_state=request.incident_state,
            component_id=request.component_id,
            action=request.action,
        )

    # PHASE_213C1B_BOUND_POLICY
    def configure_bound_effect(self, effect) -> None:
        """Register one exact live-bound effect for a validation run.

        This is instance-local configuration. Production defaults remain
        empty. Legacy action-only evaluate() behavior is not changed.
        """

        from sentinel.bound_effect_contract import (
            bound_effect_policy_run_id,
            validate_bound_effect_contract,
        )

        validate_bound_effect_contract(
            effect
        )

        if effect.action not in self.allowed_actions:
            raise ValueError(
                "bound effect action must already be allowed by "
                "RemediationPolicy"
            )

        bindings = getattr(
            self,
            "_bound_effects_by_run",
            None,
        )

        if bindings is None:
            bindings = {}
            self._bound_effects_by_run = bindings

        existing = bindings.get(bound_effect_policy_run_id(effect))

        if existing is not None and existing != effect:
            raise ValueError(
                "bound remediation run already configured with "
                "different effect"
            )

        bindings[bound_effect_policy_run_id(effect)] = effect

    def clear_bound_effects(self) -> None:
        """Remove instance-local bound-effect configuration."""

        self._bound_effects_by_run = {}

    def list_bound_runs(self) -> tuple[str, ...]:
        bindings = getattr(
            self,
            "_bound_effects_by_run",
            {},
        )
        return tuple(sorted(bindings))

    def evaluate_bound(
        self,
        *,
        incident_state: str,
        effect,
    ):
        """Evaluate one exact resource-scoped effect.

        RemediationPolicy remains the sole ALLOW/DENY authority.

        ALLOW requires:
        - legacy policy ALLOW for state/component/action
        - strong target identity
        - exact configured run
        - exact incident/component/action
        - exact target fingerprint
        - exact argv/effect fingerprint
        - exact preallocated execution ID
        - exact permit ID
        """

        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
            BoundRemediationEffect,
        )

        validate_bound_effect_contract(
            effect
        )

        # Exactly one canonical policy evaluation.
        base = self.evaluate(
            RemediationRequest(
                incident_state,
                effect.component_id,
                effect.action,
            )
        )

        base_value = getattr(
            base.decision,
            "value",
            str(base.decision),
        )

        base_reason = getattr(
            base,
            "reason",
            "canonical remediation policy decision",
        )

        bindings = getattr(
            self,
            "_bound_effects_by_run",
            {},
        )

        configured = bindings.get(bound_effect_policy_run_id(effect))

        decision = "DENY"
        reason = str(base_reason)

        if base_value != "ALLOW":
            reason = "canonical_policy_denied"

        elif not effect.target.live_eligible:
            reason = "target_identity_not_live_eligible"

        elif configured is None:
            reason = "bound_run_not_configured"

        elif configured != effect:
            reason = "bound_effect_mismatch"

        else:
            decision = "ALLOW"
            reason = "exact_bound_effect_authorized"

        return BoundRemediationAuthorization(
            decision=decision,
            reason=reason,
            incident_id=effect.incident_id,
            component_id=effect.component_id,
            action=effect.action,
            run_id=bound_effect_policy_run_id(effect),
            execution_id=effect.execution_id,
            permit_id=effect.permit_id,
            target_fingerprint=effect.target.fingerprint,
            effect_fingerprint=effect.fingerprint,
        )

    # PHASE_213D_D8_2_SYSTEMD_PRODUCTION_POLICY
    def configure_systemd_production_target_policy(
        self,
        target_policy,
    ) -> None:
        """Configure instance-local production target-safety facts only."""
        from sentinel.systemd_production_target_policy import (
            SystemdProductionTargetPolicy,
        )

        if type(target_policy) is not SystemdProductionTargetPolicy:
            raise TypeError(
                "target_policy must be "
                "SystemdProductionTargetPolicy"
            )

        self._systemd_production_target_policy = target_policy

    def clear_systemd_production_target_policy(
        self,
    ) -> None:
        """Restore production target policy to default-empty."""
        from sentinel.systemd_production_target_policy import (
            SystemdProductionTargetPolicy,
        )

        self._systemd_production_target_policy = (
            SystemdProductionTargetPolicy()
        )

    def list_systemd_production_targets(
        self,
    ) -> tuple[str, ...]:
        """Return exact configured production unit names."""
        from sentinel.systemd_production_target_policy import (
            SystemdProductionTargetPolicy,
        )

        target_policy = getattr(
            self,
            "_systemd_production_target_policy",
            None,
        )

        if target_policy is None:
            target_policy = SystemdProductionTargetPolicy()

        return tuple(sorted(target_policy.rules))

    def evaluate_systemd_production_bound(
        self,
        *,
        incident_state: str,
        effect,
        now: float,
        attempts=(),
        active_production_effects: int = 0,
        commander_authorization: SystemdProductionCommanderAuthorizationContext | None = None,
    ):
        """Apply target-safety as a restriction on canonical bound policy."""
        # Canonical context dependencies load diagnostic package orchestration,
        # which itself consumes policy. Resolve the fact type only at evaluation.
        from sentinel.systemd_production_commander_authorization import (
            SystemdProductionCommanderAuthorizationContext,
        )
        from sentinel.bound_effect_contract import (
            bound_effect_policy_run_id,
        )
        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
        )
        from sentinel.systemd_production_target_policy import (
            ACTION_RESTART,
            SystemdProductionTargetPolicy,
        )

        # Exactly one existing canonical ALLOW/DENY evaluation.
        authorization = self.evaluate_bound(
            incident_state=incident_state,
            effect=effect,
        )

        target = getattr(
            effect,
            "target",
            None,
        )

        unit_name = getattr(
            target,
            "unit_name",
            None,
        )

        if type(unit_name) is not str:
            raise TypeError(
                "production systemd target must expose exact unit_name"
            )

        if (
            effect.component_id
            != "systemd:" + unit_name
        ):
            raise ValueError(
                "production_systemd_component_target_mismatch"
            )

        target_policy = getattr(
            self,
            "_systemd_production_target_policy",
            None,
        )

        if target_policy is None:
            target_policy = SystemdProductionTargetPolicy()

        target_action = (
            ACTION_RESTART
            if effect.action == "systemd_restart"
            else effect.action
        )

        assessment = target_policy.assess(
            unit=unit_name,
            action=target_action,
            now=now,
            attempts=attempts,
            active_production_effects=(
                active_production_effects
            ),
        )

        # Target safety may never upgrade canonical DENY.
        if not authorization.authorized:
            return authorization, assessment

        if assessment.autonomous_eligible:
            return authorization, assessment

        # Commander evidence is an input fact, never an independent ALLOW.
        # Preserve every target-safety restriction and the existing bound gate.
        if (
            assessment.commander_required
            and assessment.target_known
            and not assessment.protected_target
            and assessment.cooldown_satisfied
            and assessment.retry_budget_available
            and assessment.blast_radius_available
            and assessment.verification is not None
            and type(commander_authorization)
            is SystemdProductionCommanderAuthorizationContext
            and commander_authorization.matches(effect=effect, now=now)
        ):
            return authorization, assessment

        reason = (
            assessment.reasons[0]
            if assessment.reasons
            else "production_target_not_autonomous"
        )

        denied = BoundRemediationAuthorization(
            decision="DENY",
            reason=(
                "production_target_safety_denied:"
                + reason
            ),
            incident_id=effect.incident_id,
            component_id=effect.component_id,
            action=effect.action,
            run_id=bound_effect_policy_run_id(effect),
            execution_id=effect.execution_id,
            permit_id=effect.permit_id,
            target_fingerprint=(
                effect.target.fingerprint
            ),
            effect_fingerprint=(
                effect.fingerprint
            ),
        )

        return denied, assessment
