"""Canonical semantic fact boundary for Commander Intent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommanderIntentAssessment:
    """
    Explicit semantic facts supplied to CommanderIntentDecider.

    Ownership:
      diagnosis_status:
          Diagnostic evaluation.

      remediation_required:
          Commander semantic assessment.

      remediation_action_available:
          RemediationActionCatalog / action-selection boundary.

      commander_action_required:
          Commander semantic assessment.

    This DTO contains facts only.

    It does NOT:
      - authorize
      - execute
      - verify
      - terminalize incidents
      - evaluate Policy
      - generate commands
    """

    diagnosis_status: Any
    remediation_required: bool
    remediation_action_available: bool
    commander_action_required: bool
    semantic_configured: bool | None = None
    semantic_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.remediation_required, bool):
            raise TypeError(
                "remediation_required must be bool"
            )

        if not isinstance(
            self.remediation_action_available,
            bool,
        ):
            raise TypeError(
                "remediation_action_available must be bool"
            )

        if not isinstance(
            self.commander_action_required,
            bool,
        ):
            raise TypeError(
                "commander_action_required must be bool"
            )
