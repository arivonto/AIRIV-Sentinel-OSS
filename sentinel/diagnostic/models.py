from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationState(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ESCALATED = "ESCALATED"


class DiagnosticActionClassification(str, Enum):
    OBSERVE = "OBSERVE"
    DIAGNOSTIC = "DIAGNOSTIC"
    CONSEQUENTIAL = "CONSEQUENTIAL"
    PROHIBITED = "PROHIBITED"


class DiagnosticActionState(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class DiagnosisStatus(str, Enum):
    ESTABLISHED = "ESTABLISHED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(slots=True)
class DiagnosticBudget:
    max_duration_seconds: float
    max_actions: int
    max_repeated_action: int
    max_risk: int
    minimum_evidence: int

    consumed_actions: int = 0
    consumed_risk: int = 0
    repeated_actions: dict[str, int] = field(default_factory=dict)

    def exhausted(self) -> bool:
        return (
            self.consumed_actions >= self.max_actions
            or self.consumed_risk >= self.max_risk
        )


@dataclass(slots=True)
class DiagnosticResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    started_at: datetime
    finished_at: datetime
    observation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Investigation:
    investigation_id: str
    incident_id: str
    component_id: str
    trigger: str
    state: InvestigationState
    budget: DiagnosticBudget

    current_hypothesis_ids: list[str] = field(default_factory=list)
    action_ids: list[str] = field(default_factory=list)
    observation_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    diagnosis_id: str | None = None

    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None


@dataclass(slots=True)
class DiagnosticAction:
    diagnostic_action_id: str
    investigation_id: str
    incident_id: str
    classification: DiagnosticActionClassification
    command: str
    rationale: str
    expected_information: str
    state: DiagnosticActionState = DiagnosticActionState.PLANNED

    result: DiagnosticResult | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Observation:
    observation_id: str
    investigation_id: str
    diagnostic_action_id: str
    component_id: str
    observed_at: datetime
    source: str
    subject: str
    value: Any
    raw_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Hypothesis:
    hypothesis_id: str
    investigation_id: str
    statement: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Diagnosis:
    diagnosis_id: str
    investigation_id: str
    conclusion: str
    status: DiagnosisStatus
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradictory_evidence_ids: list[str] = field(default_factory=list)
    confidence_basis: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
