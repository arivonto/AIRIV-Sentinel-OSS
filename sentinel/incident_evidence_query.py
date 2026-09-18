"""Read-only query boundary for durable S1 incident evidence reports.

This module consumes reports already persisted through IncidentReportStore.
It does not mutate Incident state, Diagnostic Engine state, remediation policy,
Commander authority, execution state, verification state, or host state.

Every report is integrity-checked before it is returned. Corrupt, malformed, or
cross-correlated evidence fails closed instead of being silently skipped.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from types import MappingProxyType
from typing import Any, Mapping

from sentinel.incident_evidence import verify_timeline_integrity


_EVIDENCE_PROFILE = "AIRIV_SENTINEL_EVIDENCE_COMPLETE_S1_V1"
_EMPTY_TIMELINE_SHA256 = hashlib.sha256(b"").hexdigest()


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _normalize_values(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} entries must be non-empty strings")
        item = value.strip().upper()
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)


def _validate_report(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("incident evidence report must be a mapping")

    report = deepcopy(dict(raw))
    if report.get("evidence_profile") != _EVIDENCE_PROFILE:
        raise ValueError("unsupported incident evidence profile")

    incident_id = report.get("incident_id")
    component_id = report.get("component_id")
    if not isinstance(incident_id, str) or not incident_id:
        raise ValueError("incident evidence report requires incident_id")
    if not isinstance(component_id, str) or not component_id:
        raise ValueError("incident evidence report requires component_id")

    started_at = report.get("started_at")
    updated_at = report.get("updated_at")
    _parse_timestamp(started_at, "started_at")
    _parse_timestamp(updated_at, "updated_at")

    timeline = report.get("timeline")
    if not isinstance(timeline, list):
        raise ValueError("incident evidence timeline must be a list")
    if not verify_timeline_integrity(timeline):
        raise ValueError("incident evidence timeline integrity check failed")

    expected_digest = (
        timeline[-1].get("event_sha256")
        if timeline
        else _EMPTY_TIMELINE_SHA256
    )
    if report.get("timeline_sha256") != expected_digest:
        raise ValueError("incident evidence timeline digest mismatch")

    for expected_sequence, event in enumerate(timeline, start=1):
        if not isinstance(event, Mapping):
            raise ValueError("incident evidence timeline entries must be mappings")
        if event.get("sequence") != expected_sequence:
            raise ValueError("incident evidence timeline sequence mismatch")
        if not isinstance(event.get("source"), str) or not event["source"]:
            raise ValueError("incident evidence event requires source")
        if not isinstance(event.get("source_id"), str) or not event["source_id"]:
            raise ValueError("incident evidence event requires source_id")
        if not isinstance(event.get("signal_type"), str) or not event["signal_type"]:
            raise ValueError("incident evidence event requires signal_type")
        _parse_timestamp(event.get("timestamp"), "timeline.timestamp")

        correlation = event.get("correlation")
        if not isinstance(correlation, Mapping):
            raise ValueError("incident evidence event requires correlation")
        if correlation.get("incident_id") != incident_id:
            raise ValueError("incident evidence event incident_id mismatch")
        if correlation.get("component_id") != component_id:
            raise ValueError("incident evidence event component_id mismatch")

    final_status = report.get("final_incident_status")
    if not isinstance(final_status, str) or not final_status:
        raise ValueError("incident evidence report requires final_incident_status")

    commander = report.get("commander_decision_requirement")
    if not isinstance(commander, Mapping) or not isinstance(
        commander.get("required"), bool
    ):
        raise ValueError(
            "incident evidence report requires commander_decision_requirement.required"
        )

    completeness = report.get("evidence_completeness")
    if not isinstance(completeness, Mapping) or not isinstance(
        completeness.get("complete"), bool
    ):
        raise ValueError("incident evidence report requires evidence_completeness.complete")

    return report


@dataclass(frozen=True, slots=True)
class IncidentEvidenceQuery:
    """Deterministic, read-only filters over durable incident evidence reports."""

    incident_id: str | None = None
    component_id: str | None = None
    final_statuses: tuple[str, ...] = ()
    commander_required: bool | None = None
    complete: bool | None = None
    signal_types: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    started_at_or_after: str | None = None
    started_before: str | None = None
    event_at_or_after: str | None = None
    event_before: str | None = None

    def __post_init__(self) -> None:
        if self.incident_id is not None and (
            not isinstance(self.incident_id, str) or not self.incident_id
        ):
            raise ValueError("incident_id must be a non-empty string")
        if self.component_id is not None and (
            not isinstance(self.component_id, str) or not self.component_id
        ):
            raise ValueError("component_id must be a non-empty string")
        if self.commander_required is not None and not isinstance(
            self.commander_required, bool
        ):
            raise ValueError("commander_required must be boolean or None")
        if self.complete is not None and not isinstance(self.complete, bool):
            raise ValueError("complete must be boolean or None")

        object.__setattr__(
            self,
            "final_statuses",
            _normalize_values(self.final_statuses, "final_statuses"),
        )
        object.__setattr__(
            self,
            "signal_types",
            _normalize_values(self.signal_types, "signal_types"),
        )
        object.__setattr__(
            self,
            "sources",
            _normalize_values(self.sources, "sources"),
        )

        started_after = (
            _parse_timestamp(self.started_at_or_after, "started_at_or_after")
            if self.started_at_or_after is not None
            else None
        )
        started_before = (
            _parse_timestamp(self.started_before, "started_before")
            if self.started_before is not None
            else None
        )
        if (
            started_after is not None
            and started_before is not None
            and started_before <= started_after
        ):
            raise ValueError("started_before must be after started_at_or_after")

        event_after = (
            _parse_timestamp(self.event_at_or_after, "event_at_or_after")
            if self.event_at_or_after is not None
            else None
        )
        event_before = (
            _parse_timestamp(self.event_before, "event_before")
            if self.event_before is not None
            else None
        )
        if (
            event_after is not None
            and event_before is not None
            and event_before <= event_after
        ):
            raise ValueError("event_before must be after event_at_or_after")


@dataclass(frozen=True, slots=True)
class IncidentEvidenceQueryResult:
    """Immutable result set returned in deterministic incident order."""

    _items: tuple[Mapping[str, Any], ...]

    @property
    def items(self) -> tuple[Mapping[str, Any], ...]:
        return self._items

    def to_list(self) -> list[dict[str, Any]]:
        return [_thaw(item) for item in self._items]

    def __len__(self) -> int:
        return len(self._items)


class IncidentEvidenceQueryService:
    """Read and filter evidence-complete reports without mutating the store."""

    def __init__(self, store: Any) -> None:
        if not hasattr(store, "get") or not callable(store.get):
            raise TypeError("store must provide callable get()")
        if not hasattr(store, "recover") or not callable(store.recover):
            raise TypeError("store must provide callable recover()")
        self._store = store

    def get(self, incident_id: str) -> Mapping[str, Any] | None:
        if not isinstance(incident_id, str) or not incident_id:
            raise ValueError("incident_id must be a non-empty string")
        raw = self._store.get(incident_id)
        if raw is None:
            return None
        report = _validate_report(raw)
        if report["incident_id"] != incident_id:
            raise ValueError("store returned mismatched incident_id")
        return _freeze(report)

    @staticmethod
    def _event_matches(event: Mapping[str, Any], query: IncidentEvidenceQuery) -> bool:
        if query.signal_types and str(event["signal_type"]).upper() not in query.signal_types:
            return False
        if query.sources and str(event["source"]).upper() not in query.sources:
            return False

        timestamp = _parse_timestamp(event["timestamp"], "timeline.timestamp")
        if query.event_at_or_after is not None:
            if timestamp < _parse_timestamp(query.event_at_or_after, "event_at_or_after"):
                return False
        if query.event_before is not None:
            if timestamp >= _parse_timestamp(query.event_before, "event_before"):
                return False
        return True

    @staticmethod
    def _report_matches(report: Mapping[str, Any], query: IncidentEvidenceQuery) -> bool:
        if query.incident_id is not None and report["incident_id"] != query.incident_id:
            return False
        if query.component_id is not None and report["component_id"] != query.component_id:
            return False
        if query.final_statuses and str(report["final_incident_status"]).upper() not in query.final_statuses:
            return False
        if query.commander_required is not None:
            if report["commander_decision_requirement"]["required"] is not query.commander_required:
                return False
        if query.complete is not None:
            if report["evidence_completeness"]["complete"] is not query.complete:
                return False

        started = _parse_timestamp(report["started_at"], "started_at")
        if query.started_at_or_after is not None:
            if started < _parse_timestamp(query.started_at_or_after, "started_at_or_after"):
                return False
        if query.started_before is not None:
            if started >= _parse_timestamp(query.started_before, "started_before"):
                return False
        return True

    def search(
        self,
        query: IncidentEvidenceQuery | None = None,
    ) -> IncidentEvidenceQueryResult:
        query = query or IncidentEvidenceQuery()
        if not isinstance(query, IncidentEvidenceQuery):
            raise TypeError("query must be an IncidentEvidenceQuery")

        if query.incident_id is not None:
            raw = self._store.get(query.incident_id)
            raw_reports = [] if raw is None else [raw]
        else:
            raw_reports = self._store.recover()
            if not isinstance(raw_reports, list):
                raise ValueError("store.recover() must return a list")

        selected: list[tuple[datetime, str, dict[str, Any]]] = []
        event_filter_active = bool(
            query.signal_types
            or query.sources
            or query.event_at_or_after is not None
            or query.event_before is not None
        )

        for raw in raw_reports:
            report = _validate_report(raw)
            if not self._report_matches(report, query):
                continue

            matched_events = [
                deepcopy(event)
                for event in report["timeline"]
                if self._event_matches(event, query)
            ]
            if event_filter_active and not matched_events:
                continue

            summary = {
                "incident_id": report["incident_id"],
                "component_id": report["component_id"],
                "started_at": report["started_at"],
                "updated_at": report["updated_at"],
                "final_incident_status": report["final_incident_status"],
                "commander_decision_requirement": deepcopy(
                    report["commander_decision_requirement"]
                ),
                "evidence_completeness": deepcopy(report["evidence_completeness"]),
                "timeline_sha256": report["timeline_sha256"],
                "matched_event_count": len(matched_events),
                "matched_events": matched_events,
            }
            selected.append(
                (
                    _parse_timestamp(report["started_at"], "started_at"),
                    report["incident_id"],
                    summary,
                )
            )

        selected.sort(key=lambda item: (item[0], item[1]))
        return IncidentEvidenceQueryResult(
            tuple(_freeze(item[2]) for item in selected)
        )
