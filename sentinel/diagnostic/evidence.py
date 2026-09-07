from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .executor import DiagnosticResult
from .models import DiagnosticAction, Investigation, Observation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class DiagnosticEvidenceRecord:
    evidence_id: str
    investigation_id: str
    incident_id: str
    diagnostic_action_id: str
    classification: str
    command: str
    started_at: datetime
    finished_at: datetime
    exit_code: int | None
    success: bool
    state: str
    stdout: str
    stderr: str
    observation_id: str | None
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceAdapter:
    """
    Adapts actual diagnostic execution results into the existing
    immutable Evidence Trail through InvestigationManager.

    This adapter does not create Incident lifecycle authority,
    authorization authority, remediation authority, or diagnosis.
    """

    def __init__(self, investigation_manager) -> None:
        self._investigation_manager = investigation_manager

    def record_incident_observations(self, investigation: Investigation, records) -> None:
        """Copy canonical TMUX facts into existing Investigation persistence."""
        if investigation.state.value != "ACTIVE" or investigation.budget.exhausted():
            return
        for record in records:
            facts = record.observation_snapshot
            if (record.incident_id != investigation.incident_id
                    or record.component_id != investigation.component_id
                    or facts.get("source") != "TMUX"
                    or facts.get("pane_id") != investigation.component_id):
                continue
            observation_id = record.evidence_id
            if observation_id not in investigation.observation_ids:
                observation = Observation(
                    observation_id=observation_id,
                    investigation_id=investigation.investigation_id,
                    diagnostic_action_id="",
                    component_id=investigation.component_id,
                    observed_at=datetime.fromisoformat(record.timestamp),
                    source="TMUX",
                    subject="pane_dead",
                    value={key: facts[key] for key in ("pane_id", "pane_dead") if key in facts},
                    # PHASE_213C1C_RAW_EVIDENCE
                    raw_evidence=dict(facts),
                )
                investigation = self._investigation_manager.record_observation(
                    investigation.investigation_id, observation,
                )
            investigation = self._investigation_manager.add_evidence_reference(
                investigation.investigation_id, record.evidence_id,
            )

    def record_diagnostic_result(
        self,
        investigation: Investigation,
        action: DiagnosticAction,
        result: DiagnosticResult,
        observation: Observation | None = None,
    ) -> DiagnosticEvidenceRecord:
        if action.investigation_id != investigation.investigation_id:
            raise ValueError("investigation_id_mismatch")

        if action.incident_id != investigation.incident_id:
            raise ValueError("incident_id_mismatch")

        if result.diagnostic_action_id != action.diagnostic_action_id:
            raise ValueError("diagnostic_action_id_mismatch")

        evidence_id = (
            f"diagnostic:{investigation.investigation_id}:"
            f"{action.diagnostic_action_id}"
        )

        record = DiagnosticEvidenceRecord(
            evidence_id=evidence_id,
            investigation_id=investigation.investigation_id,
            incident_id=investigation.incident_id,
            diagnostic_action_id=action.diagnostic_action_id,
            classification=action.classification.value,
            command=action.command,
            started_at=result.started_at,
            finished_at=result.finished_at,
            exit_code=result.exit_code,
            success=result.success,
            state=result.state,
            stdout=result.stdout,
            stderr=result.stderr,
            observation_id=(
                observation.observation_id
                if observation is not None
                else None
            ),
            recorded_at=utc_now(),
        )

        self._investigation_manager.add_evidence_reference(
            investigation.investigation_id,
            evidence_id,
        )

        return record

    def record_observation(
        self,
        investigation: Investigation,
        observation: Observation,
    ) -> None:
        if observation.investigation_id != investigation.investigation_id:
            raise ValueError("investigation_id_mismatch")

        self._investigation_manager.record_observation(
            investigation.investigation_id,
            observation,
        )
