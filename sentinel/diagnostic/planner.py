from __future__ import annotations

import shlex

from dataclasses import dataclass
from uuid import uuid4

from .models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    Hypothesis,
    Investigation,
    InvestigationState,
)


@dataclass(frozen=True, slots=True)
class DiagnosticCatalogEntry:
    """
    Controlled diagnostic command definition.

    Commands are explicitly registered by the system and are not
    generated arbitrarily by the planner.
    """

    name: str
    command: str
    classification: DiagnosticActionClassification
    rationale: str
    expected_information: str


class DiagnosticActionCatalog:
    """
    Allowlisted source of diagnostic actions.

    Only OBSERVE and DIAGNOSTIC actions may be registered.
    """

    _ALLOWED_CLASSIFICATIONS = frozenset(
        {
            DiagnosticActionClassification.OBSERVE,
            DiagnosticActionClassification.DIAGNOSTIC,
        }
    )

    def __init__(
        self,
        entries: list[DiagnosticCatalogEntry] | None = None,
    ) -> None:
        self._entries: dict[str, DiagnosticCatalogEntry] = {}

        for entry in entries or []:
            self.register(entry)

    def register(
        self,
        entry: DiagnosticCatalogEntry,
    ) -> None:
        if entry.classification not in self._ALLOWED_CLASSIFICATIONS:
            raise ValueError("catalog_action_classification_not_allowed")

        if not entry.name:
            raise ValueError("catalog_action_name_required")

        if not entry.command:
            raise ValueError("catalog_action_command_required")

        if entry.name in self._entries:
            raise ValueError(
                f"diagnostic_catalog_entry_already_exists: {entry.name}"
            )

        self._entries[entry.name] = entry

    def get(
        self,
        name: str,
    ) -> DiagnosticCatalogEntry | None:
        return self._entries.get(name)

    def list(self) -> list[DiagnosticCatalogEntry]:
        return list(self._entries.values())


class DiagnosticPlanner:
    """
    Plans safe diagnostic actions from a controlled catalog.

    Authority boundary:
    - selects an allowlisted diagnostic action
    - creates a new diagnostic_action_id for each attempt
    - produces PLANNED DiagnosticAction records

    This planner does not:
    - execute commands
    - consume budget
    - authorize remediation
    - create or resolve incidents
    - establish diagnosis
    - execute CONSEQUENTIAL actions
    - execute PROHIBITED actions
    - reuse UNKNOWN action identity
    """

    _ALLOWED_CLASSIFICATIONS = frozenset(
        {
            DiagnosticActionClassification.OBSERVE,
            DiagnosticActionClassification.DIAGNOSTIC,
        }
    )

    def __init__(
        self,
        catalog: DiagnosticActionCatalog,
    ) -> None:
        self.catalog = catalog

    def plan(
        self,
        investigation: Investigation,
        catalog_name: str,
        *,
        hypothesis: Hypothesis | None = None,
    ) -> DiagnosticAction:
        if investigation.state is not InvestigationState.ACTIVE:
            raise ValueError("investigation_not_active")

        entry = self.catalog.get(catalog_name)

        if entry is None:
            raise ValueError("diagnostic_action_not_in_catalog")

        if entry.classification not in self._ALLOWED_CLASSIFICATIONS:
            raise ValueError("diagnostic_action_classification_not_allowed")

        if hypothesis is not None:
            if hypothesis.investigation_id != investigation.investigation_id:
                raise ValueError("hypothesis_investigation_id_mismatch")

        command = entry.command.replace(
            "{component_id}",
            shlex.quote(investigation.component_id),
        )

        return DiagnosticAction(
            diagnostic_action_id=f"diagnostic-action:{uuid4()}",
            investigation_id=investigation.investigation_id,
            incident_id=investigation.incident_id,
            classification=entry.classification,
            command=command,
            rationale=entry.rationale,
            expected_information=entry.expected_information,
            state=DiagnosticActionState.PLANNED,
        )
