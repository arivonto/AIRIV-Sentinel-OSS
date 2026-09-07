"""Commander Intent semantic decision boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sentinel.commander_intent import CommanderIntent

if TYPE_CHECKING:
    from sentinel.commander_intent_assessment import (
        CommanderIntentAssessment,
    )


@dataclass(frozen=True)
class CommanderIntentDecision:
    """Result of Commander Intent evaluation."""

    intent: CommanderIntent
    reason: str


class CommanderIntentDecider:
    """
    Select Commander Intent from explicit semantic facts.

    The assessment API is canonical.

    A legacy keyword-compatible path is retained temporarily so existing
    runtime callers remain behaviorally compatible while the semantic
    assessment producer is introduced.

    This class does NOT:
      - authorize actions
      - execute remediation
      - terminalize incidents
      - evaluate remediation policy
    """

    def decide(
        self,
        assessment: CommanderIntentAssessment | None = None,
        *,
        diagnosis_status: Any = None,
        remediation_action_available: bool | None = None,
        commander_action_required: bool | None = None,
    ) -> CommanderIntentDecision:
        """
        Decide Commander Intent.

        Canonical:
            decide(assessment)

        Compatibility:
            decide(
                diagnosis_status=...,
                remediation_action_available=...,
                commander_action_required=...,
            )
        """

        if assessment is not None:
            if any(
                value is not None
                for value in (
                    diagnosis_status,
                    remediation_action_available,
                    commander_action_required,
                )
            ):
                raise TypeError(
                    "provide either assessment or legacy keyword facts, "
                    "not both"
                )

            return self._decide_assessment(assessment)

        if diagnosis_status is None:
            raise TypeError(
                "assessment is required"
            )

        if remediation_action_available is None:
            remediation_action_available = False

        if commander_action_required is None:
            commander_action_required = False

        return self._decide_facts(
            diagnosis_status=diagnosis_status,
            remediation_required=remediation_action_available,
            remediation_action_available=remediation_action_available,
            commander_action_required=commander_action_required,
        )

    def _decide_assessment(
        self,
        assessment: CommanderIntentAssessment,
    ) -> CommanderIntentDecision:
        return self._decide_facts(
            diagnosis_status=assessment.diagnosis_status,
            remediation_required=assessment.remediation_required,
            remediation_action_available=(
                assessment.remediation_action_available
            ),
            commander_action_required=(
                assessment.commander_action_required
            ),
        )

    @staticmethod
    def _decide_facts(
        *,
        diagnosis_status: Any,
        remediation_required: bool,
        remediation_action_available: bool,
        commander_action_required: bool,
    ) -> CommanderIntentDecision:
        status = getattr(
            diagnosis_status,
            "value",
            diagnosis_status,
        )

        if status == "INSUFFICIENT_EVIDENCE":
            return CommanderIntentDecision(
                intent=CommanderIntent.INSUFFICIENT_EVIDENCE,
                reason="Diagnosis contains insufficient evidence.",
            )

        if commander_action_required:
            return CommanderIntentDecision(
                intent=CommanderIntent.NEED_COMMANDER,
                reason="Commander intervention is required.",
            )

        if (
            remediation_required
            and remediation_action_available
        ):
            return CommanderIntentDecision(
                intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
                reason=(
                    "Remediation is required and an explicit "
                    "remediation action is available."
                ),
            )

        return CommanderIntentDecision(
            intent=CommanderIntent.NO_ACTION,
            reason=(
                "No autonomous remediation or Commander "
                "intervention is required."
            ),
        )
