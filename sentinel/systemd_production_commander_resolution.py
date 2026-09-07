"""Gate 1 canonical Commander-approved systemd outcome/resolution composition.

This boundary introduces no new policy, execution, verification, or lifecycle
authority. It translates already-canonical facts through FinalOutcomeMapper and
then delegates the sole terminal mutation to IncidentManager.resolve().

It is intentionally not wired into SentinelRuntime; runtime composition belongs
to Gate 2.
"""

from dataclasses import dataclass

from sentinel.commander_intent import CommanderIntent
from sentinel.final_outcome_mapper import FinalOutcomeMapper
from sentinel.incidents.manager import Incident, IncidentManager
from sentinel.remediation_policy import PolicyDecision
from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegrationResult,
)
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from sentinel.systemd_production_commander_incident_continuation import (
    SystemdProductionCommanderIncidentContinuation,
)


@dataclass(frozen=True, slots=True)
class SystemdProductionCommanderResolution:
    final_outcome: str
    incident: Incident


def resolve_systemd_production_commander_result(
    *,
    continuation: SystemdProductionCommanderIncidentContinuation,
    commander_authorization: SystemdProductionCommanderAuthorizationContext,
    integration_result: SystemdCommanderIntegrationResult,
    incident_manager: IncidentManager,
) -> SystemdProductionCommanderResolution:
    """Map exact Commander-approved execution facts and terminalize once."""

    if (
        type(continuation)
        is not SystemdProductionCommanderIncidentContinuation
    ):
        raise TypeError(
            "canonical Commander incident continuation required"
        )

    if (
        type(commander_authorization)
        is not SystemdProductionCommanderAuthorizationContext
    ):
        raise TypeError(
            "canonical Commander authorization context required"
        )

    if (
        type(integration_result)
        is not SystemdCommanderIntegrationResult
    ):
        raise TypeError(
            "canonical SystemdCommanderIntegrationResult required"
        )

    if type(incident_manager) is not IncidentManager:
        raise TypeError("canonical IncidentManager required")

    continuation.__post_init__()
    effect = continuation.prepared.plan.effect

    if commander_authorization.binding.prepared is not continuation.prepared:
        raise ValueError(
            "commander_resolution_authorization_continuity_mismatch"
        )

    authorization = integration_result.authorization
    if not authorization.matches(effect):
        raise ValueError(
            "commander_resolution_policy_effect_mismatch"
        )

    if authorization.incident_id != continuation.incident_id:
        raise ValueError(
            "commander_resolution_incident_mismatch"
        )

    if authorization.component_id != continuation.component_id:
        raise ValueError(
            "commander_resolution_component_mismatch"
        )

    if authorization.execution_id != continuation.execution_id:
        raise ValueError(
            "commander_resolution_execution_mismatch"
        )

    incident = incident_manager.get_active_incident(
        continuation.component_id
    )

    if type(incident) is not Incident:
        raise ValueError(
            "commander_resolution_active_incident_required"
        )

    if incident.incident_id != continuation.incident_id:
        raise ValueError(
            "commander_resolution_active_incident_identity_mismatch"
        )

    if (
        incident.status != "INVESTIGATING"
        or incident.lifecycle_state != "INVESTIGATING"
        or incident.final_outcome is not None
    ):
        raise ValueError(
            "commander_resolution_requires_active_investigation"
        )

    policy_decision = (
        PolicyDecision.ALLOW
        if authorization.authorized
        else PolicyDecision.DENY
    )

    final_outcome = FinalOutcomeMapper.map_commander_approved_remediation(
        intent=CommanderIntent.NEED_COMMANDER,
        continuation=continuation,
        commander_authorization=commander_authorization,
        policy_decision=policy_decision,
        execution_succeeded=(
            integration_result.execution_succeeded
            if authorization.authorized
            else None
        ),
        verification_succeeded=(
            integration_result.verification_succeeded
            if authorization.authorized
            and integration_result.execution_succeeded
            else None
        ),
    )

    binding = commander_authorization.binding
    grant = binding.grant

    resolved = incident_manager.resolve(
        component_id=continuation.component_id,
        recovery_evidence={
            "source": "systemd_production_commander_resolution",
            "incident_id": continuation.incident_id,
            "component_id": continuation.component_id,
            "execution_id": continuation.execution_id,
            "approval_id": continuation.approval_id,
            "activation_id": grant.activation_id,
            "effect_fingerprint": effect.fingerprint,
            "policy_decision": policy_decision.value,
            "execution_succeeded": (
                integration_result.execution_succeeded
                if authorization.authorized
                else None
            ),
            "verification_succeeded": (
                integration_result.verification_succeeded
                if authorization.authorized
                and integration_result.execution_succeeded
                else None
            ),
            "final_outcome": final_outcome,
        },
        observation={
            "incident_id": continuation.incident_id,
            "component_id": continuation.component_id,
            "final_outcome": final_outcome,
        },
        operator_note=(
            "Commander-approved systemd remediation terminalized incident "
            f"with outcome: {final_outcome}."
        ),
        final_outcome=final_outcome,
    )

    return SystemdProductionCommanderResolution(
        final_outcome=final_outcome,
        incident=resolved,
    )
