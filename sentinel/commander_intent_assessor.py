"""Commander semantic assessment boundary."""

from __future__ import annotations

from typing import Any

from sentinel.commander_intent_assessment import CommanderIntentAssessment
from sentinel.commander_semantic_policy import CommanderSemanticPolicy


class CommanderIntentAssessor:
    """
    Produces CommanderIntentAssessment.

    Canonical production path:
        incident + diagnosis
            ↓
        CommanderSemanticPolicy
            ↓
        CommanderIntentAssessment

    remediation_required and commander_action_required are owned
    exclusively by CommanderSemanticPolicy.

    remediation_action_available remains independently supplied by
    RemediationActionCatalog.

    Legacy keyword arguments are retained only for test/API compatibility.
    They do not become the authoritative production semantic source.
    """

    def __init__(
        self,
        semantic_policy: CommanderSemanticPolicy | None = None,
    ) -> None:
        self.semantic_policy = (
            semantic_policy
            if semantic_policy is not None
            else CommanderSemanticPolicy()
        )

    def assess(
        self,
        *,
        incident: Any = None,
        diagnosis: Any = None,
        remediation_action_available: bool | None = None,
        diagnosis_status: Any = None,
        remediation_required: bool | None = None,
        commander_action_required: bool | None = None,
    ) -> CommanderIntentAssessment:
        """
        Build a CommanderIntentAssessment.

        Canonical production usage requires incident + diagnosis and derives
        semantic facts from CommanderSemanticPolicy.

        Legacy keyword compatibility is retained for existing focused tests.
        When no incident is supplied, the explicit legacy semantic facts are
        accepted only as compatibility inputs.
        """

        # ------------------------------------------------------------
        # CANONICAL PRODUCTION PATH
        # ------------------------------------------------------------

        if incident is not None:
            if diagnosis is None:
                raise ValueError("diagnosis is required")

            if remediation_action_available is None:
                raise TypeError(
                    "remediation_action_available must be bool"
                )

            if not isinstance(remediation_action_available, bool):
                raise TypeError(
                    "remediation_action_available must be bool"
                )

            trigger = getattr(incident, "anomaly_type", None)

            if not isinstance(trigger, str) or not trigger.strip():
                raise ValueError(
                    "incident must provide anomaly_type for semantic assessment"
                )

            facts = self.semantic_policy.assess(trigger)

            return CommanderIntentAssessment(
                diagnosis_status=getattr(diagnosis, "status", None),
                remediation_required=facts.remediation_required,
                remediation_action_available=remediation_action_available,
                commander_action_required=facts.commander_action_required,
                semantic_configured=facts.configured,
                semantic_reason=facts.reason,
            )

        # ------------------------------------------------------------
        # LEGACY TEST/API COMPATIBILITY PATH
        # ------------------------------------------------------------

        if diagnosis_status is None:
            raise TypeError(
                "canonical assessment requires incident and diagnosis"
            )

        if remediation_action_available is None:
            raise TypeError(
                "remediation_action_available must be bool"
            )

        if remediation_required is None:
            raise TypeError(
                "remediation_required must be bool"
            )

        if commander_action_required is None:
            raise TypeError(
                "commander_action_required must be bool"
            )

        if not isinstance(remediation_action_available, bool):
            raise TypeError(
                "remediation_action_available must be bool"
            )

        if not isinstance(remediation_required, bool):
            raise TypeError(
                "remediation_required must be bool"
            )

        if not isinstance(commander_action_required, bool):
            raise TypeError(
                "commander_action_required must be bool"
            )

        return CommanderIntentAssessment(
            diagnosis_status=diagnosis_status,
            remediation_required=remediation_required,
            remediation_action_available=remediation_action_available,
            commander_action_required=commander_action_required,
        )
