"""Fail-closed external delivery projection for AIRIV Sentinel rollups.

The projection is an explicit allowlist between internal unattended reporting
and future transports such as email or webhooks. Unknown schema fields are
rejected so evidence, commands, credentials, or future sensitive additions
cannot leak through schema drift.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


_ROLLUP_SCHEMA_VERSION = "AIRIV_SENTINEL_UNATTENDED_ROLLUP_V1"
_DELIVERY_SCHEMA_VERSION = "AIRIV_SENTINEL_COMMANDER_DELIVERY_V1"

_ROLLUP_FIELDS = frozenset({
    "schema_version",
    "generated_at",
    "window_start",
    "window_end",
    "incident_count",
    "commander_attention_count",
    "evidence_count",
    "final_status_counts",
    "incidents",
    "commander_attention_queue",
})

_INCIDENT_FIELDS = frozenset({
    "incident_id",
    "component_id",
    "agent_identity",
    "anomaly_type",
    "started_at",
    "updated_at",
    "lifecycle_state",
    "final_status",
    "commander_attention_required",
    "evidence_count",
    "detection_understanding_count",
    "diagnostic_action_count",
    "remediation_action_count",
    "verification_result_count",
    "commander_decision_count",
})

_PROJECTED_INCIDENT_FIELDS = (
    "incident_id",
    "component_id",
    "agent_identity",
    "anomaly_type",
    "started_at",
    "updated_at",
    "lifecycle_state",
    "final_status",
    "commander_attention_required",
    "evidence_count",
    "detection_understanding_count",
    "diagnostic_action_count",
    "remediation_action_count",
    "verification_result_count",
    "commander_decision_count",
)


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


def _validate_aware_timestamp(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")


def _validate_exact_fields(
    mapping: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(mapping.keys())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise ValueError(f"{label} schema mismatch: {'; '.join(details)}")


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _validate_incident_summary(item: Any, label: str) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} must be an object")
    snapshot = deepcopy(dict(item))
    _validate_exact_fields(snapshot, _INCIDENT_FIELDS, label)

    for field in (
        "incident_id",
        "component_id",
        "agent_identity",
        "anomaly_type",
        "lifecycle_state",
        "final_status",
    ):
        if not isinstance(snapshot[field], str) or not snapshot[field].strip():
            raise ValueError(f"{label}.{field} must be a non-empty string")

    _validate_aware_timestamp(snapshot["started_at"], f"{label}.started_at")
    _validate_aware_timestamp(snapshot["updated_at"], f"{label}.updated_at")

    if not isinstance(snapshot["commander_attention_required"], bool):
        raise ValueError(
            f"{label}.commander_attention_required must be boolean"
        )

    for field in (
        "evidence_count",
        "detection_understanding_count",
        "diagnostic_action_count",
        "remediation_action_count",
        "verification_result_count",
        "commander_decision_count",
    ):
        _non_negative_int(snapshot[field], f"{label}.{field}")

    return snapshot


def _project_incident(item: Mapping[str, Any]) -> dict[str, Any]:
    return {field: deepcopy(item[field]) for field in _PROJECTED_INCIDENT_FIELDS}


@dataclass(frozen=True, slots=True)
class CommanderDeliveryProjection:
    """Immutable transport-safe projection with no transport capability."""

    _payload: Mapping[str, Any]

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._payload)

    def subject(self) -> str:
        data = self.to_dict()
        return (
            "AIRIV Sentinel — "
            f"{data['commander_attention_count']} attention / "
            f"{data['incident_count']} incidents"
        )

    def to_markdown(self) -> str:
        data = self.to_dict()
        lines = [
            "# AIRIV Sentinel Commander Brief",
            "",
            f"- **Generated:** `{data['generated_at']}`",
            f"- **Window start:** `{data['window_start'] or 'ALL'}`",
            f"- **Window end:** `{data['window_end'] or 'ALL'}`",
            f"- **Incidents:** `{data['incident_count']}`",
            f"- **Commander attention:** `{data['commander_attention_count']}`",
            f"- **Evidence events:** `{data['evidence_count']}`",
            "",
            "## Commander Attention Queue",
        ]

        if not data["commander_attention_queue"]:
            lines.append("- Empty.")
        else:
            for item in data["commander_attention_queue"]:
                lines.append(
                    "- "
                    f"`{item['started_at']}` · `{item['incident_id']}` · "
                    f"**{item['final_status']}** · "
                    f"`{item['component_id']}`"
                )

        lines.extend(["", "## Incident summaries"])
        if not data["incidents"]:
            lines.append("- None recorded.")
        else:
            for item in data["incidents"]:
                lines.append(
                    "- "
                    f"`{item['started_at']}` · `{item['incident_id']}` · "
                    f"**{item['final_status']}** · evidence "
                    f"`{item['evidence_count']}`"
                )

        return "\n".join(lines) + "\n"


class CommanderDeliveryProjector:
    """Project a V1 unattended rollup through an explicit disclosure allowlist."""

    def project(self, rollup: Any) -> CommanderDeliveryProjection:
        if hasattr(rollup, "to_dict") and callable(rollup.to_dict):
            source = rollup.to_dict()
        elif isinstance(rollup, Mapping):
            source = deepcopy(dict(rollup))
        else:
            raise TypeError("rollup must be a rollup-like object or mapping")

        if not isinstance(source, Mapping):
            raise ValueError("rollup serialization must be an object")
        source = deepcopy(dict(source))
        _validate_exact_fields(source, _ROLLUP_FIELDS, "rollup")

        if source["schema_version"] != _ROLLUP_SCHEMA_VERSION:
            raise ValueError("unsupported unattended rollup schema")

        _validate_aware_timestamp(source["generated_at"], "generated_at")
        for field in ("window_start", "window_end"):
            if source[field] is not None:
                _validate_aware_timestamp(source[field], field)

        incident_count = _non_negative_int(
            source["incident_count"], "incident_count"
        )
        attention_count = _non_negative_int(
            source["commander_attention_count"],
            "commander_attention_count",
        )
        evidence_count = _non_negative_int(
            source["evidence_count"], "evidence_count"
        )

        statuses = source["final_status_counts"]
        if not isinstance(statuses, Mapping):
            raise ValueError("final_status_counts must be an object")
        status_counts: dict[str, int] = {}
        for status, count in statuses.items():
            if not isinstance(status, str) or not status.strip():
                raise ValueError("final_status_counts keys must be non-empty strings")
            status_counts[status] = _non_negative_int(
                count, f"final_status_counts.{status}"
            )
        if sum(status_counts.values()) != incident_count:
            raise ValueError("final_status_counts does not match incident_count")

        raw_incidents = source["incidents"]
        raw_queue = source["commander_attention_queue"]
        if not isinstance(raw_incidents, list):
            raise ValueError("incidents must be a list")
        if not isinstance(raw_queue, list):
            raise ValueError("commander_attention_queue must be a list")
        if len(raw_incidents) != incident_count:
            raise ValueError("incidents length does not match incident_count")
        if len(raw_queue) != attention_count:
            raise ValueError(
                "commander_attention_queue length does not match "
                "commander_attention_count"
            )

        incidents: list[dict[str, Any]] = []
        incidents_by_id: dict[str, dict[str, Any]] = {}
        total_evidence = 0
        for index, raw_item in enumerate(raw_incidents):
            item = _validate_incident_summary(
                raw_item, f"incidents[{index}]"
            )
            incident_id = item["incident_id"]
            if incident_id in incidents_by_id:
                raise ValueError(f"duplicate incident_id: {incident_id}")
            incidents_by_id[incident_id] = item
            incidents.append(item)
            total_evidence += item["evidence_count"]
        if total_evidence != evidence_count:
            raise ValueError("incident evidence counts do not match evidence_count")

        queue: list[dict[str, Any]] = []
        seen_queue_ids: set[str] = set()
        for index, raw_item in enumerate(raw_queue):
            item = _validate_incident_summary(
                raw_item, f"commander_attention_queue[{index}]"
            )
            incident_id = item["incident_id"]
            if incident_id in seen_queue_ids:
                raise ValueError(
                    f"duplicate Commander attention incident_id: {incident_id}"
                )
            seen_queue_ids.add(incident_id)
            canonical = incidents_by_id.get(incident_id)
            if canonical is None:
                raise ValueError(
                    "Commander attention item missing from incident summaries: "
                    f"{incident_id}"
                )
            if item != canonical:
                raise ValueError(
                    "Commander attention item does not match incident summary: "
                    f"{incident_id}"
                )
            if item["commander_attention_required"] is not True:
                raise ValueError(
                    "Commander attention queue contains non-attention incident: "
                    f"{incident_id}"
                )
            queue.append(item)

        explicit_attention_ids = {
            item["incident_id"]
            for item in incidents
            if item["commander_attention_required"] is True
        }
        if explicit_attention_ids != seen_queue_ids:
            raise ValueError(
                "Commander attention queue does not match explicit attention flags"
            )

        payload = {
            "schema_version": _DELIVERY_SCHEMA_VERSION,
            "source_schema_version": _ROLLUP_SCHEMA_VERSION,
            "generated_at": source["generated_at"],
            "window_start": source["window_start"],
            "window_end": source["window_end"],
            "incident_count": incident_count,
            "commander_attention_count": attention_count,
            "evidence_count": evidence_count,
            "final_status_counts": status_counts,
            "incidents": [_project_incident(item) for item in incidents],
            "commander_attention_queue": [
                _project_incident(item) for item in queue
            ],
        }
        return CommanderDeliveryProjection(_freeze(payload))
