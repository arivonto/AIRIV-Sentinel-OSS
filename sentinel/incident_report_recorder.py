"""Idempotent persistence reconciler for AIRIV Sentinel incident reports.

The recorder derives reports from canonical IncidentManager state and persists
only changed reporting artifacts. It has no authority over Incident lifecycle,
Commander decisions, remediation policy, execution, or verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sentinel.incident_reporting import IncidentReportBuilder


@dataclass(frozen=True, slots=True)
class IncidentReportRecorderResult:
    """Immutable summary of one reporting reconciliation pass."""

    written_incident_ids: tuple[str, ...]
    unchanged_incident_ids: tuple[str, ...]

    @property
    def report_count(self) -> int:
        return len(self.written_incident_ids) + len(self.unchanged_incident_ids)


class IncidentReportRecorder:
    """Reconcile canonical active/history state into a durable report store."""

    def __init__(self, store: Any, builder: IncidentReportBuilder | None = None) -> None:
        if not hasattr(store, "get") or not callable(store.get):
            raise TypeError("store must provide callable get()")
        if not hasattr(store, "save") or not callable(store.save):
            raise TypeError("store must provide callable save()")
        self.store = store
        self.builder = builder or IncidentReportBuilder()

    @staticmethod
    def _sources_by_incident_id(manager: Any) -> dict[str, Any]:
        active = getattr(manager, "active_incidents", None)
        if not isinstance(active, Mapping):
            raise TypeError("manager must expose active_incidents mapping")
        if not hasattr(manager, "get_history") or not callable(manager.get_history):
            raise TypeError("manager must provide callable get_history()")

        sources: dict[str, Any] = {}

        for incident in tuple(active.values()):
            incident_id = getattr(incident, "incident_id", None)
            if not isinstance(incident_id, str) or not incident_id:
                raise ValueError("active Incident missing incident_id")
            if incident_id in sources:
                raise RuntimeError(f"duplicate active incident_id: {incident_id}")
            sources[incident_id] = incident

        history = manager.get_history()
        if not isinstance(history, list):
            raise ValueError("IncidentManager history must be a list")

        for snapshot in history:
            if not isinstance(snapshot, Mapping):
                raise ValueError("IncidentManager history entries must be mappings")
            incident_id = snapshot.get("incident_id")
            if not isinstance(incident_id, str) or not incident_id:
                raise ValueError("history snapshot missing incident_id")
            if incident_id in sources:
                raise RuntimeError(
                    "incident_id present in both active state and history: "
                    f"{incident_id}"
                )
            sources[incident_id] = snapshot

        return sources

    def sync(self, manager: Any) -> IncidentReportRecorderResult:
        """Persist changed reports for all canonical active and terminal state.

        Existing corrupt reports fail closed through store.get(); they are never
        silently overwritten. Reports absent from current manager state are not
        deleted because reporting persistence is append-retentive by default.
        """
        sources = self._sources_by_incident_id(manager)
        written: list[str] = []
        unchanged: list[str] = []

        for incident_id in sorted(sources):
            report = self.builder.build(sources[incident_id])
            candidate = report.to_dict()
            existing = self.store.get(incident_id)

            if existing == candidate:
                unchanged.append(incident_id)
                continue

            self.store.save(report)
            written.append(incident_id)

        return IncidentReportRecorderResult(
            written_incident_ids=tuple(written),
            unchanged_incident_ids=tuple(unchanged),
        )
