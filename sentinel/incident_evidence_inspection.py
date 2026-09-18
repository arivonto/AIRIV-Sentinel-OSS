"""Deterministic read-only inspection of durable S1 incident evidence.

This boundary consumes only integrity-checked reports through
IncidentEvidenceQueryService. It does not mutate Incident lifecycle, diagnostic
state, Commander authority, remediation policy, execution state, verification
state, report persistence, or host state.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from sentinel.incident_evidence_query import IncidentEvidenceQueryService


_INSPECTION_SCHEMA_VERSION = "AIRIV_SENTINEL_INCIDENT_EVIDENCE_INSPECTION_V1"


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
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)


def _single_line(value: Any) -> str:
    text = str(value if value is not None else "")
    return " ".join(text.replace("\r", "\n").splitlines()).strip()


def _latest(items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return deepcopy(items[-1]) if items else None


@dataclass(frozen=True, slots=True)
class IncidentEvidenceInspection:
    """Immutable Commander/forensics inspection snapshot for one incident."""

    _payload: Mapping[str, Any]

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._payload)

    def to_markdown(self) -> str:
        """Render a stable human-readable inspection without changing evidence."""
        data = self.to_dict()
        identity = data["identity"]
        integrity = data["integrity"]
        completeness = data["evidence_completeness"]
        commander = data["commander"]
        remediation = data["remediation"]
        verification = data["verification"]
        latest_state = data["latest_observed_state"]

        lines = [
            "# AIRIV Sentinel Incident Evidence Inspection",
            "",
            "## Identity",
            f"- **Incident:** `{identity['incident_id']}`",
            f"- **Component:** `{identity['component_id']}`",
            f"- **Agent:** `{identity['agent_identity']}`",
            f"- **Anomaly:** `{identity['anomaly_type']}`",
            f"- **Started:** `{identity['started_at']}`",
            f"- **Updated:** `{identity['updated_at']}`",
            f"- **Lifecycle:** `{identity['lifecycle_state']}`",
            f"- **Final status:** `{identity['final_status']}`",
            "",
            "## Integrity",
            "- **Timeline integrity:** `VERIFIED`",
            f"- **Evidence events:** `{integrity['event_count']}`",
            f"- **Timeline SHA-256:** `{integrity['timeline_sha256']}`",
            "",
            "## Evidence completeness",
            f"- **Complete:** `{'YES' if completeness['complete'] else 'NO'}`",
        ]

        missing = completeness.get("missing") or []
        if missing:
            lines.append("- **Missing:** " + ", ".join(f"`{item}`" for item in missing))
        else:
            lines.append("- **Missing:** `NONE`")

        lines.extend(
            [
                "",
                "## Current evidence view",
                "- **Latest observed state:** "
                + (
                    f"`{latest_state.get('state')}` at `{latest_state.get('timestamp')}`"
                    if latest_state is not None
                    else "`UNKNOWN`"
                ),
                f"- **Normalized input snapshots:** `{data['normalized_input_count']}`",
                f"- **Detection events:** `{data['detection']['event_count']}`",
                f"- **Diagnostic events:** `{data['diagnostics']['event_count']}`",
                f"- **Diagnostic failures:** `{data['diagnostics']['failure_count']}`",
                "",
                "## Commander",
                f"- **Decision required:** `{'YES' if commander['required'] else 'NO'}`",
                f"- **Decision evidence events:** `{commander['event_count']}`",
                "",
                "## Remediation",
                f"- **Known:** `{'YES' if remediation['status']['known'] else 'NO'}`",
                f"- **Eligibility:** `{remediation['status'].get('eligibility') or 'UNKNOWN'}`",
                f"- **Status:** `{remediation['status'].get('status') or 'UNKNOWN'}`",
                f"- **Evidence events:** `{remediation['event_count']}`",
                "",
                "## Verification",
                f"- **Evidence events:** `{verification['event_count']}`",
                "- **Latest result:** "
                + (
                    f"`{verification['latest'].get('signal_type')}` — "
                    f"{_single_line(verification['latest'].get('reason'))}"
                    if verification["latest"] is not None
                    else "`NONE`"
                ),
                "",
                "## Chronological evidence timeline",
            ]
        )

        if not data["timeline"]:
            lines.append("- No evidence events recorded.")
        else:
            for event in data["timeline"]:
                reason = _single_line(event.get("reason")) or "no reason recorded"
                lines.append(
                    "- "
                    f"`#{event['sequence']}` · `{event['timestamp']}` · "
                    f"**{event['signal_type']}** · `{event['source']}` / "
                    f"`{event['source_id']}` · {reason}"
                )

        return "\n".join(lines) + "\n"


class IncidentEvidenceInspector:
    """Build one deterministic inspection snapshot from durable evidence."""

    def __init__(self, store: Any) -> None:
        self._query = IncidentEvidenceQueryService(store)

    def inspect(self, incident_id: str) -> IncidentEvidenceInspection:
        """Inspect one incident through the integrity-checked exact read path."""
        report_view = self._query.get(incident_id)
        if report_view is None:
            raise KeyError(f"Unknown incident_id: {incident_id}")

        report = _thaw(report_view)
        timeline = deepcopy(report["timeline"])

        detection = [
            deepcopy(event)
            for event in timeline
            if event.get("category") == "detection"
        ]
        diagnostics = [
            deepcopy(event)
            for event in timeline
            if event.get("category") == "diagnostic"
        ]
        remediation_events = deepcopy(report.get("remediation_actions") or [])
        verification_events = deepcopy(report.get("verification_results") or [])
        commander_events = [
            deepcopy(event)
            for event in timeline
            if event.get("category") == "commander"
        ]

        diagnostic_failures = [
            deepcopy(event)
            for event in diagnostics
            if "FAIL" in str(event.get("signal_type") or "").upper()
            or (
                isinstance(event.get("signal_snapshot"), Mapping)
                and event["signal_snapshot"].get("success") is False
            )
        ]

        observed_states = deepcopy(report.get("observed_states") or [])
        normalized_inputs = deepcopy(report.get("normalized_inputs") or [])
        decisions = deepcopy(report.get("decisions") or [])
        commander_requirement = deepcopy(
            report["commander_decision_requirement"]
        )
        remediation_status = deepcopy(report["remediation_eligibility_status"])
        verification_result = deepcopy(report.get("verification_result"))
        completeness = deepcopy(report["evidence_completeness"])

        category_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        for event in timeline:
            category = str(event.get("category") or "other")
            source = str(event.get("source") or "UNKNOWN")
            category_counts[category] = category_counts.get(category, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1

        payload = {
            "schema_version": _INSPECTION_SCHEMA_VERSION,
            "source_report_schema": report.get("schema_version"),
            "evidence_profile": report.get("evidence_profile"),
            "identity": {
                "incident_id": report["incident_id"],
                "component_id": report["component_id"],
                "agent_identity": report.get("agent_identity") or "UNKNOWN",
                "anomaly_type": report.get("anomaly_type") or "UNKNOWN_ANOMALY",
                "started_at": report["started_at"],
                "updated_at": report["updated_at"],
                "lifecycle_state": report.get("lifecycle_state") or "UNKNOWN",
                "final_status": report["final_incident_status"],
            },
            "integrity": {
                "verified": True,
                "timeline_sha256": report["timeline_sha256"],
                "event_count": len(timeline),
            },
            "evidence_completeness": completeness,
            "latest_observed_state": _latest(observed_states),
            "observed_states": observed_states,
            "normalized_input_count": len(normalized_inputs),
            "normalized_inputs": normalized_inputs,
            "detection": {
                "event_count": len(detection),
                "events": detection,
            },
            "diagnostics": {
                "event_count": len(diagnostics),
                "failure_count": len(diagnostic_failures),
                "failures": diagnostic_failures,
                "events": diagnostics,
            },
            "decisions": {
                "event_count": len(decisions),
                "events": decisions,
            },
            "commander": {
                "required": commander_requirement["required"],
                "status": commander_requirement.get("status"),
                "event_count": len(commander_events),
                "events": commander_events,
            },
            "remediation": {
                "status": remediation_status,
                "event_count": len(remediation_events),
                "events": remediation_events,
            },
            "verification": {
                "latest": verification_result,
                "event_count": len(verification_events),
                "events": verification_events,
            },
            "category_counts": category_counts,
            "source_counts": source_counts,
            "timeline": timeline,
        }
        return IncidentEvidenceInspection(_freeze(payload))
