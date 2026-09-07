"""Canonical AIRIV Sentinel incident final-outcome semantic mapper."""

from __future__ import annotations

from sentinel.commander_intent import CommanderIntent
from sentinel.incidents.manager import Incident
from sentinel.remediation_policy import PolicyDecision


class FinalOutcomeMappingError(RuntimeError):
    """Raised when final-outcome facts are semantically inconsistent."""


class FinalOutcomeMapper:
    """
    Pure semantic mapping boundary.

    This boundary:
    - does not authorize
    - does not execute
    - does not verify
    - does not mutate Incident
    - does not terminalize Incident

    IncidentManager remains the sole lifecycle mutation authority.
    """

    @classmethod
    def map(
        cls,
        *,
        intent: CommanderIntent,
        policy_decision: PolicyDecision | None = None,
        execution_succeeded: bool | None = None,
        verification_succeeded: bool | None = None,
    ) -> str | None:
        """
        Map canonical Commander/runtime facts to an Incident final outcome.

        None means the incident must remain non-terminal at this boundary.
        """

        if not isinstance(intent, CommanderIntent):
            raise TypeError("intent must be a CommanderIntent")

        if (
            policy_decision is not None
            and not isinstance(policy_decision, PolicyDecision)
        ):
            raise TypeError(
                "policy_decision must be a PolicyDecision or None"
            )

        cls._validate_optional_bool(
            execution_succeeded,
            "execution_succeeded",
        )
        cls._validate_optional_bool(
            verification_succeeded,
            "verification_succeeded",
        )

        if intent is CommanderIntent.NO_ACTION:
            cls._require_no_remediation_facts(
                policy_decision=policy_decision,
                execution_succeeded=execution_succeeded,
                verification_succeeded=verification_succeeded,
            )
            return None

        if intent is CommanderIntent.INSUFFICIENT_EVIDENCE:
            cls._require_no_remediation_facts(
                policy_decision=policy_decision,
                execution_succeeded=execution_succeeded,
                verification_succeeded=verification_succeeded,
            )
            return cls._canonical("INSUFFICIENT_EVIDENCE")

        if intent is CommanderIntent.NEED_COMMANDER:
            cls._require_no_remediation_facts(
                policy_decision=policy_decision,
                execution_succeeded=execution_succeeded,
                verification_succeeded=verification_succeeded,
            )
            return cls._canonical("ESCALATED")

        if intent is not CommanderIntent.AUTONOMOUS_REMEDIATE:
            raise FinalOutcomeMappingError(
                f"unsupported CommanderIntent: {intent!r}"
            )

        return cls._map_remediation_result(
            policy_decision=policy_decision,
            execution_succeeded=execution_succeeded,
            verification_succeeded=verification_succeeded,
            deny_outcome="ESCALATED",
            missing_policy_message=(
                "AUTONOMOUS_REMEDIATE requires PolicyDecision"
            ),
        )

    @classmethod
    def map_commander_approved_remediation(
        cls,
        *,
        intent: CommanderIntent,
        continuation,
        commander_authorization,
        policy_decision: PolicyDecision,
        execution_succeeded: bool | None = None,
        verification_succeeded: bool | None = None,
    ) -> str:
        """Map one durable Commander-approved NEED_COMMANDER continuation.

        This is intentionally separate from ``map`` so a Commander-approved
        continuation is never relabeled as autonomous remediation.
        """
        from sentinel.systemd_production_commander_authorization import (
            SystemdProductionCommanderAuthorizationContext,
        )
        from sentinel.systemd_production_commander_incident_continuation import (
            SystemdProductionCommanderIncidentContinuation,
        )

        if intent is not CommanderIntent.NEED_COMMANDER:
            raise FinalOutcomeMappingError(
                "Commander-approved remediation requires NEED_COMMANDER intent"
            )

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

        continuation.__post_init__()

        binding = commander_authorization.binding
        if binding.prepared is not continuation.prepared:
            raise FinalOutcomeMappingError(
                "Commander authorization continuation mismatch"
            )

        if binding.approval_id != continuation.approval_id:
            raise FinalOutcomeMappingError(
                "Commander approval continuity mismatch"
            )

        if binding.incident_id != continuation.incident_id:
            raise FinalOutcomeMappingError(
                "Commander incident continuity mismatch"
            )

        if binding.component_id != continuation.component_id:
            raise FinalOutcomeMappingError(
                "Commander component continuity mismatch"
            )

        if binding.execution_id != continuation.execution_id:
            raise FinalOutcomeMappingError(
                "Commander execution continuity mismatch"
            )

        return cls._map_remediation_result(
            policy_decision=policy_decision,
            execution_succeeded=execution_succeeded,
            verification_succeeded=verification_succeeded,
            deny_outcome="ESCALATED",
            missing_policy_message=(
                "Commander-approved remediation requires PolicyDecision"
            ),
        )

    @classmethod
    def _map_remediation_result(
        cls,
        *,
        policy_decision: PolicyDecision | None,
        execution_succeeded: bool | None,
        verification_succeeded: bool | None,
        deny_outcome: str,
        missing_policy_message: str,
    ) -> str:
        if (
            policy_decision is not None
            and not isinstance(policy_decision, PolicyDecision)
        ):
            raise TypeError(
                "policy_decision must be a PolicyDecision or None"
            )

        cls._validate_optional_bool(
            execution_succeeded,
            "execution_succeeded",
        )
        cls._validate_optional_bool(
            verification_succeeded,
            "verification_succeeded",
        )

        if policy_decision is None:
            raise FinalOutcomeMappingError(
                missing_policy_message
            )

        if policy_decision is PolicyDecision.DENY:
            if (
                execution_succeeded is not None
                or verification_succeeded is not None
            ):
                raise FinalOutcomeMappingError(
                    "DENY must not contain execution or verification facts"
                )
            return cls._canonical(deny_outcome)

        if policy_decision is not PolicyDecision.ALLOW:
            raise FinalOutcomeMappingError(
                f"unsupported PolicyDecision: {policy_decision!r}"
            )

        if execution_succeeded is not True:
            return cls._canonical("UNRESOLVED")

        if verification_succeeded is not True:
            return cls._canonical("UNRESOLVED")

        return cls._canonical("RECOVERED")

    @staticmethod
    def _validate_optional_bool(
        value: bool | None,
        field_name: str,
    ) -> None:
        if value is not None and type(value) is not bool:
            raise TypeError(
                f"{field_name} must be bool or None"
            )

    @staticmethod
    def _require_no_remediation_facts(
        *,
        policy_decision: PolicyDecision | None,
        execution_succeeded: bool | None,
        verification_succeeded: bool | None,
    ) -> None:
        if (
            policy_decision is not None
            or execution_succeeded is not None
            or verification_succeeded is not None
        ):
            raise FinalOutcomeMappingError(
                "non-remediation intent must not contain "
                "remediation lifecycle facts"
            )

    @staticmethod
    def _canonical(outcome: str) -> str:
        if outcome not in Incident.VALID_OUTCOMES:
            raise FinalOutcomeMappingError(
                f"non-canonical incident final outcome: {outcome}"
            )

        return outcome
