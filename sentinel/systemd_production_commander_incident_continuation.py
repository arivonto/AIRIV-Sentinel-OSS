"""Inert Commander-only continuation fact for one exact systemd incident.

This boundary owns no policy, execution, activation, verification, or
incident-lifecycle mutation.

It validates only that an active INVESTIGATING incident requiring Commander
action is exactly continuous with trusted systemd evidence, one prepared
production effect, and one exact typed Commander approval.

Runtime wiring is intentionally absent.
"""

from dataclasses import dataclass
import math

from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_decider import CommanderIntentDecision
from sentinel.incidents.manager import Incident
from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_approval_issuance import (
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_production_target_policy import ACTION_RESTART


def _timestamp(value, field):
    if type(value) not in (int, float):
        raise TypeError(f"{field} must be numeric")

    value = float(value)

    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"{field} must be finite and non-negative"
        )

    return value


def _required_id(value, field):
    if type(value) is not str or not value.strip():
        raise ValueError(
            f"{field} must be non-empty string"
        )

    return value


def _systemd_action_semantic(action):
    """Normalize canonical execution action to production target semantics."""
    return ACTION_RESTART if action == "systemd_restart" else action


@dataclass(frozen=True)
class SystemdProductionCommanderIncidentContinuation:
    """Immutable approved-continuation fact; never execution authority."""

    incident_id: str
    component_id: str
    action: str
    execution_id: str
    approval_id: str

    continued_at: float
    approval_expires_at: float

    binding: TrustedSystemdDispatchEvidenceBinding
    prepared: PreparedSystemdProductionRemediation
    approval: TrustedSystemdProductionCommanderApproval

    def __post_init__(self):
        _required_id(
            self.incident_id,
            "incident_id",
        )
        _required_id(
            self.component_id,
            "component_id",
        )
        _required_id(
            self.action,
            "action",
        )
        _required_id(
            self.execution_id,
            "execution_id",
        )
        _required_id(
            self.approval_id,
            "approval_id",
        )

        continued_at = _timestamp(
            self.continued_at,
            "continued_at",
        )
        expires_at = _timestamp(
            self.approval_expires_at,
            "approval_expires_at",
        )

        if continued_at >= expires_at:
            raise ValueError(
                "commander_approval_expired"
            )

        if (
            type(self.binding)
            is not TrustedSystemdDispatchEvidenceBinding
        ):
            raise TypeError(
                "canonical trusted evidence binding required"
            )

        if (
            type(self.prepared)
            is not PreparedSystemdProductionRemediation
        ):
            raise TypeError(
                "canonical prepared remediation required"
            )

        if (
            type(self.approval)
            is not TrustedSystemdProductionCommanderApproval
        ):
            raise TypeError(
                "canonical trusted Commander approval required"
            )

        if self.prepared.binding is not self.binding:
            raise ValueError(
                "trusted_evidence_binding_mismatch"
            )

        plan = self.prepared.plan
        effect = plan.effect

        if self.incident_id != effect.incident_id:
            raise ValueError(
                "incident_binding_mismatch"
            )

        if self.component_id != effect.component_id:
            raise ValueError(
                "component_binding_mismatch"
            )

        if self.action != _systemd_action_semantic(effect.action):
            raise ValueError(
                "action_binding_mismatch"
            )

        if self.execution_id != effect.execution_id:
            raise ValueError(
                "execution_binding_mismatch"
            )

        if self.approval_id != self.approval.approval_id:
            raise ValueError(
                "approval_id_mismatch"
            )

        if self.approval.effect != plan.permit_binding:
            raise ValueError(
                "approval_effect_binding_mismatch"
            )

        if (
            float(self.approval.expires_at)
            != expires_at
        ):
            raise ValueError(
                "approval_expiry_binding_mismatch"
            )


def build_systemd_production_commander_incident_continuation(
    *,
    incident,
    decision,
    binding,
    prepared,
    approval,
    now,
):
    """Build one exact inert Commander-only continuation fact."""

    if type(incident) is not Incident:
        raise TypeError(
            "canonical Incident required"
        )

    if type(decision) is not CommanderIntentDecision:
        raise TypeError(
            "canonical CommanderIntentDecision required"
        )

    if decision.intent is not CommanderIntent.NEED_COMMANDER:
        raise ValueError(
            "commander_only_continuation_requires_need_commander"
        )

    if (
        incident.status != "INVESTIGATING"
        or incident.lifecycle_state != "INVESTIGATING"
        or incident.final_outcome is not None
    ):
        raise ValueError(
            "commander_only_continuation_requires_active_investigation"
        )

    if (
        type(binding)
        is not TrustedSystemdDispatchEvidenceBinding
    ):
        raise TypeError(
            "canonical trusted evidence binding required"
        )

    if (
        type(prepared)
        is not PreparedSystemdProductionRemediation
    ):
        raise TypeError(
            "canonical prepared remediation required"
        )

    if (
        type(approval)
        is not TrustedSystemdProductionCommanderApproval
    ):
        raise TypeError(
            "canonical trusted Commander approval required"
        )

    current = _timestamp(
        now,
        "now",
    )

    if not (
        float(approval.issued_at)
        <= current
        < float(approval.expires_at)
    ):
        raise ValueError(
            "commander_approval_not_current"
        )

    effect = prepared.plan.effect
    action = _systemd_action_semantic(effect.action)

    if action != ACTION_RESTART:
        raise ValueError(
            "unsupported_systemd_production_action"
        )

    if incident.incident_id != effect.incident_id:
        raise ValueError(
            "incident_binding_mismatch"
        )

    if incident.component_id != effect.component_id:
        raise ValueError(
            "component_binding_mismatch"
        )

    return SystemdProductionCommanderIncidentContinuation(
        incident_id=incident.incident_id,
        component_id=incident.component_id,
        action=action,
        execution_id=effect.execution_id,
        approval_id=approval.approval_id,
        continued_at=current,
        approval_expires_at=float(
            approval.expires_at
        ),
        binding=binding,
        prepared=prepared,
        approval=approval,
    )
