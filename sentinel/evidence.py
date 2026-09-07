"""AIRIV Sentinel Evidence Trail Boundary V1.

Evidence is:
- append-oriented
- immutable once recorded
- observable
- auditable
- non-executing

This boundary records evidence only.
It MUST NOT execute remediation or alter incident authority.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable representation of one evidence event."""

    evidence_id: str
    incident_id: str
    component_id: str
    timestamp: str
    evidence_type: str
    reason: str
    observation_snapshot: Dict[str, Any]
    signal_snapshot: Dict[str, Any]

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


class EvidenceTrail:
    """Append-only in-memory evidence store."""

    def __init__(self) -> None:
        self._records: List[EvidenceRecord] = []
        self._sequence = 0

    def append(
        self,
        incident_id: str,
        component_id: str,
        evidence_type: str,
        reason: str,
        observation: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
    ) -> EvidenceRecord:
        if not incident_id:
            raise ValueError("incident_id must not be empty")

        if not component_id:
            raise ValueError("component_id must not be empty")

        if not evidence_type:
            raise ValueError("evidence_type must not be empty")

        self._sequence += 1

        record = EvidenceRecord(
            evidence_id=f"EVD-{self._sequence:08d}",
            incident_id=incident_id,
            component_id=component_id,
            timestamp=EvidenceRecord.now(),
            evidence_type=evidence_type,
            reason=reason,
            observation_snapshot=deepcopy(observation or {}),
            signal_snapshot=deepcopy(signal or {}),
        )

        self._records.append(record)
        return record

    def records(self) -> tuple[EvidenceRecord, ...]:
        """Return an immutable view of the current evidence sequence."""
        return tuple(
            EvidenceRecord(
                evidence_id=record.evidence_id,
                incident_id=record.incident_id,
                component_id=record.component_id,
                timestamp=record.timestamp,
                evidence_type=record.evidence_type,
                reason=record.reason,
                observation_snapshot=deepcopy(
                    record.observation_snapshot
                ),
                signal_snapshot=deepcopy(
                    record.signal_snapshot
                ),
            )
            for record in self._records
        )

    def count(self) -> int:
        return len(self._records)
