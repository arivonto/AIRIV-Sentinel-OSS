"""Read-only unattended rollups for AIRIV Sentinel incident reports.

This module aggregates already-derived incident reports into a compact
Commander-facing operational view. It does not mutate Incident lifecycle,
make policy decisions, grant authorization, execute remediation, or alter
stored evidence.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Iterable, Mapping


_ROLLUP_SCHEMA_VERSION = "AIRIV_SENTINEL_UNATTENDED_ROLLUP_V1"
_REPORT_SCHEMA_VERSION = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"


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


def _parse_aware_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _validate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise ValueError("unattended rollup reports must be mappings")

    snapshot = deepcopy(dict(report))
    if snapshot.get("schema_version") != _REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported incident report schema")

    required = (
        "incident_id",
        "component_id",
        "started_at",
        "updated_at",
        "final_status",
        "commander_attention_required",
        "evidence_count",
        "detection_and_understanding",
        "diagnostic_actions",
        "remediation_actions",
        "verification_results",
        "commander_decisions",
        "timeline",
    )
    missing = [key for key in required if key not in snapshot]
    if missing:
        raise ValueError(
            "incident report missing rollup fields: " + ", ".join(missing)
        )

    if not isinstance(snapshot["incident_id"], str) or not snapshot["incident_id"]:
        raise ValueError("incident report incident_id must not be empty")
    if not isinstance(snapshot["commander_attention_required"], bool):
        raise ValueError("commander_attention_required must be boolean")
    if not isinstance(snapshot["evidence_count"], int) or snapshot["evidence_count"] < 0:
        raise ValueError("incident report evidence_count must be non-negative")

    timeline = snapshot["timeline"]
    if not isinstance(timeline, list):
        raise ValueError("incident report timeline must be a list")
    if len(timeline) != snapshot["evidence_count"]:
        raise ValueError("incident report evidence_count does not match timeline")

    for field in (
        "detection_and_understanding",
        "diagnostic_actions",
        "remediation_actions",
        "verification_results",
        "commander_decisions",
    ):
        if not isinstance(snapshot[field], list):
            raise ValueError(f"incident report {field} must be a list")

    _parse_aware_timestamp(snapshot["started_at"], "started_at")
    _parse_aware_timestamp(snapshot["updated_at"], "updated_at")
    return snapshot


def _summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": report["incident_id"],
        "component_id": report["component_id"],
        "agent_identity": report.get("agent_identity") or "UNKNOWN",
        "anomaly_type": report.get("anomaly_type") or "UNKNOWN_ANOMALY",
        "started_at": report["started_at"],
        "updated_at": report["updated_at"],
        "lifecycle_state": report.get("lifecycle_state") or "UNKNOWN",
        "final_status": report["final_status"],
        "commander_attention_required": report["commander_attention_required"],
        "evidence_count": report["evidence_count"],
        "detection_understanding_count": len(
            report["detection_and_understanding"]
        ),
        "diagnostic_action_count": len(report["diagnostic_actions"]),
        "remediation_action_count": len(report["remediation_actions"]),
        "verification_result_count": len(report["verification_results"]),
        "commander_decision_count": len(report["commander_decisions"]),
    }


@dataclass(frozen=True, slots=True)
class CommanderAttentionQueue:
    """Immutable chronological view of explicit Commander-attention reports."""

    _items: tuple[Mapping[str, Any], ...]

    @property
    def items(self) -> tuple[Mapping[str, Any], ...]:
        return self._items

    def to_list(self) -> list[dict[str, Any]]:
        return [_thaw(item) for item in self._items]

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True, slots=True)
class UnattendedIncidentRollup:
    """Immutable unattended/overnight summary derived from incident reports."""

    _payload: Mapping[str, Any]

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    @property
    def commander_attention_queue(self) -> CommanderAttentionQueue:
        raw_items = self._payload["commander_attention_queue"]
        return CommanderAttentionQueue(tuple(raw_items))

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._payload)

    def to_markdown(self) -> str:
        data = self.to_dict()
        lines = [
            "# AIRIV Sentinel Unattended Incident Rollup",
            "",
            f"- **Generated:** `{data['generated_at']}`",
            f"- **Window start:** `{data['window_start'] or 'ALL'}`",
            f"- **Window end:** `{data['window_end'] or 'ALL'}`",
            f"- **Incidents:** `{data['incident_count']}`",
            f"- **Commander attention:** `{data['commander_attention_count']}`",
            f"- **Evidence events:** `{data['evidence_count']}`",
            "",
            "## Final status counts",
        ]

        if data["final_status_counts"]:
            for status, count in sorted(data["final_status_counts"].items()):
                lines.append(f"- **{status}:** `{count}`")
        else:
            lines.append("- None.")

        lines.extend(["", "## Incident summaries"])
        if not data["incidents"]:
            lines.append("- None recorded.")
        else:
            for item in data["incidents"]:
                attention = (
                    " · **COMMANDER ATTENTION**"
                    if item["commander_attention_required"]
                    else ""
                )
                lines.append(
                    "- "
                    f"`{item['started_at']}` · `{item['incident_id']}` · "
                    f"**{item['final_status']}** · evidence "
                    f"`{item['evidence_count']}`{attention}"
                )

        lines.extend(["", "## Commander Attention Queue"])
        if not data["commander_attention_queue"]:
            lines.append("- Empty.")
        else:
            for item in data["commander_attention_queue"]:
                lines.append(
                    "- "
                    f"`{item['started_at']}` · `{item['incident_id']}` · "
                    f"**{item['final_status']}** · component "
                    f"`{item['component_id']}`"
                )

        return "\n".join(lines) + "\n"


class UnattendedIncidentRollupBuilder:
    """Build chronological unattended rollups without creating new authority."""

    def build(
        self,
        reports: Iterable[Mapping[str, Any]],
        *,
        window_start: str | None = None,
        window_end: str | None = None,
        generated_at: str | None = None,
    ) -> UnattendedIncidentRollup:
        if (window_start is None) != (window_end is None):
            raise ValueError("window_start and window_end must be supplied together")

        start_dt = None
        end_dt = None
        normalized_start = None
        normalized_end = None
        if window_start is not None and window_end is not None:
            start_dt = _parse_aware_timestamp(window_start, "window_start")
            end_dt = _parse_aware_timestamp(window_end, "window_end")
            if end_dt <= start_dt:
                raise ValueError("window_end must be after window_start")
            normalized_start = _iso_utc(start_dt)
            normalized_end = _iso_utc(end_dt)

        generated_dt = (
            _parse_aware_timestamp(generated_at, "generated_at")
            if generated_at is not None
            else datetime.now(timezone.utc)
        )

        selected: list[tuple[datetime, dict[str, Any]]] = []
        for raw_report in reports:
            report = _validate_report(raw_report)
            started_dt = _parse_aware_timestamp(report["started_at"], "started_at")
            if start_dt is not None and end_dt is not None:
                if started_dt < start_dt or started_dt >= end_dt:
                    continue
            selected.append((started_dt, report))

        selected.sort(key=lambda item: (item[0], item[1]["incident_id"]))
        summaries = [_summary(report) for _, report in selected]

        status_counts: dict[str, int] = {}
        evidence_count = 0
        for summary in summaries:
            status = str(summary["final_status"] or "UNKNOWN").upper()
            status_counts[status] = status_counts.get(status, 0) + 1
            evidence_count += summary["evidence_count"]

        attention = [
            summary
            for summary in summaries
            if summary["commander_attention_required"] is True
        ]

        payload = {
            "schema_version": _ROLLUP_SCHEMA_VERSION,
            "generated_at": _iso_utc(generated_dt),
            "window_start": normalized_start,
            "window_end": normalized_end,
            "incident_count": len(summaries),
            "commander_attention_count": len(attention),
            "evidence_count": evidence_count,
            "final_status_counts": status_counts,
            "incidents": summaries,
            "commander_attention_queue": attention,
        }
        return UnattendedIncidentRollup(_freeze(payload))

    def build_from_store(
        self,
        store: Any,
        *,
        window_start: str | None = None,
        window_end: str | None = None,
        generated_at: str | None = None,
    ) -> UnattendedIncidentRollup:
        """Build from a report store through its read-only recovery surface."""
        if not hasattr(store, "recover") or not callable(store.recover):
            raise TypeError("store must provide a callable recover()")
        return self.build(
            store.recover(),
            window_start=window_start,
            window_end=window_end,
            generated_at=generated_at,
        )
