"""AIRIV Sentinel read-only incident reporting boundary.

This module turns canonical Incident state and evidence into Commander-readable
operational reports. It is deliberately non-authoritative: it does not mutate
Incident state, execute remediation, evaluate policy, or grant authorization.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


_SCHEMA_VERSION = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"


def _freeze(value: Any) -> Any:
    """Recursively freeze JSON-like data into read-only structures."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(_freeze(item) for item in sorted(value, key=repr))
    return deepcopy(value)


def _thaw(value: Any) -> Any:
    """Return a defensive mutable copy suitable for serialization."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)


def _normalized_signal_type(entry: Mapping[str, Any]) -> str:
    return str(entry.get("signal_type") or "UNKNOWN").strip().upper()


def _event_category(signal_type: str) -> str:
    if (
        "COMMANDER" in signal_type
        or "HANDOFF" in signal_type
        or "ESCALAT" in signal_type
    ):
        return "commander"
    if (
        signal_type in {"ANOMALY", "CONTRACT_VIOLATION", "OBSERVATION"}
        or "DETECT" in signal_type
    ):
        return "detection"
    if any(
        token in signal_type
        for token in ("DIAG", "INVESTIG", "HYPOTHESIS", "UNDERSTAND")
    ):
        return "diagnostic"
    if any(
        token in signal_type
        for token in ("VERIFY", "VERIFICATION", "RECOVERY")
    ):
        return "verification"
    if any(
        token in signal_type
        for token in ("REMEDIAT", "EXECUTION", "ACTION")
    ):
        return "remediation"
    return "other"


def _truthy_flag(mapping: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        if mapping.get(key) is True:
            return True
    return False


def _one_line(value: Any) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class IncidentReport:
    """Immutable, non-executing operational view of one Incident."""

    _payload: Mapping[str, Any]

    @property
    def payload(self) -> Mapping[str, Any]:
        """Expose the recursively read-only report payload."""
        return self._payload

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive JSON-compatible copy of the report."""
        return _thaw(self._payload)

    def to_markdown(self) -> str:
        """Render a compact Commander-readable unattended incident report."""
        data = self.to_dict()
        lines = [
            "# AIRIV Sentinel Incident Report",
            "",
            f"- **Incident:** `{data['incident_id']}`",
            f"- **Component:** `{data['component_id']}`",
            f"- **Agent:** `{data['agent_identity']}`",
            f"- **Anomaly:** `{data['anomaly_type']}`",
            f"- **Started:** `{data['started_at']}`",
            f"- **Last update:** `{data['updated_at']}`",
            f"- **Lifecycle:** `{data['lifecycle_state']}`",
            f"- **Final status:** `{data['final_status']}`",
            (
                "- **Commander attention:** `REQUIRED`"
                if data["commander_attention_required"]
                else "- **Commander attention:** `NOT REQUIRED`"
            ),
            f"- **Evidence events:** `{data['evidence_count']}`",
        ]

        sections = (
            ("Detection / understanding", "detection_and_understanding"),
            ("Diagnostic actions", "diagnostic_actions"),
            ("Remediation actions", "remediation_actions"),
            ("Verification results", "verification_results"),
            ("Commander decisions / handoffs", "commander_decisions"),
            ("Evidence timeline", "timeline"),
        )

        for title, key in sections:
            lines.extend(["", f"## {title}"])
            events = data[key]
            if not events:
                lines.append("- None recorded.")
                continue
            for event in events:
                timestamp = _one_line(event.get("timestamp")) or "unknown-time"
                signal_type = _one_line(event.get("signal_type")) or "UNKNOWN"
                reason = _one_line(event.get("reason")) or "No reason recorded."
                lines.append(
                    f"- `{timestamp}` · **{signal_type}** · {reason}"
                )

        return "\n".join(lines) + "\n"


class IncidentReportBuilder:
    """Build read-only reports from canonical Incident objects or snapshots."""

    @staticmethod
    def _snapshot(source: Any) -> dict[str, Any]:
        if isinstance(source, Mapping):
            snapshot = deepcopy(dict(source))
        elif hasattr(source, "to_dict") and callable(source.to_dict):
            snapshot = deepcopy(source.to_dict())
        else:
            raise TypeError("source must be an Incident-like object or mapping")

        if not snapshot.get("incident_id"):
            raise ValueError("incident report requires incident_id")
        if not snapshot.get("component_id"):
            raise ValueError("incident report requires component_id")
        return snapshot

    @staticmethod
    def _event(entry: Mapping[str, Any], sequence: int) -> dict[str, Any]:
        signal_type = _normalized_signal_type(entry)
        return {
            "sequence": sequence,
            "timestamp": entry.get("timestamp"),
            "signal_type": signal_type,
            "reason": entry.get("reason") or "",
            "observation_snapshot": deepcopy(
                entry.get("observation_snapshot") or {}
            ),
            "signal_snapshot": deepcopy(entry.get("signal_snapshot") or {}),
        }

    def build(self, source: Any) -> IncidentReport:
        snapshot = self._snapshot(source)
        raw_evidence = snapshot.get("evidence_trail") or []
        if not isinstance(raw_evidence, (list, tuple)):
            raise ValueError("evidence_trail must be a sequence")

        timeline = []
        for sequence, entry in enumerate(raw_evidence, start=1):
            if not isinstance(entry, Mapping):
                raise ValueError("evidence_trail entries must be mappings")
            timeline.append(self._event(entry, sequence))

        detection = []
        diagnostic = []
        remediation = []
        verification = []
        commander = []
        commander_attention_required = False

        for event in timeline:
            category = _event_category(event["signal_type"])
            if category == "detection":
                detection.append(event)
            elif category == "diagnostic":
                diagnostic.append(event)
            elif category == "remediation":
                remediation.append(event)
            elif category == "verification":
                verification.append(event)
            elif category == "commander":
                commander.append(event)
                commander_attention_required = True

            signal = event["signal_snapshot"]
            if isinstance(signal, Mapping) and _truthy_flag(
                signal,
                "commander_required",
                "requires_commander",
                "approval_required",
                "authorization_required",
            ):
                commander_attention_required = True
                if event not in commander:
                    commander.append(event)

        final_outcome = snapshot.get("final_outcome")
        lifecycle_state = (
            snapshot.get("lifecycle_state")
            or snapshot.get("status")
            or "UNKNOWN"
        )
        final_status = final_outcome or lifecycle_state
        if str(final_outcome or "").upper() == "ESCALATED":
            commander_attention_required = True

        payload = {
            "schema_version": _SCHEMA_VERSION,
            "incident_id": snapshot["incident_id"],
            "component_id": snapshot["component_id"],
            "agent_identity": snapshot.get("agent_identity") or "UNKNOWN",
            "anomaly_type": snapshot.get("anomaly_type") or "UNKNOWN_ANOMALY",
            "started_at": snapshot.get("created_at"),
            "updated_at": snapshot.get("updated_at"),
            "lifecycle_state": lifecycle_state,
            "final_outcome": final_outcome,
            "final_status": final_status,
            "commander_attention_required": commander_attention_required,
            "evidence_count": len(timeline),
            "detection_and_understanding": detection + diagnostic,
            "diagnostic_actions": diagnostic,
            "remediation_actions": remediation,
            "verification_results": verification,
            "commander_decisions": commander,
            "timeline": timeline,
        }
        return IncidentReport(_freeze(payload))

    def build_from_manager(self, manager: Any, incident_id: str) -> IncidentReport:
        """Read an active or terminal Incident without mutating manager state."""
        if not incident_id:
            raise ValueError("incident_id must not be empty")

        active = manager.get_incident_by_id(incident_id)
        if active is not None:
            return self.build(active)

        for snapshot in manager.get_history():
            if snapshot.get("incident_id") == incident_id:
                return self.build(snapshot)

        raise KeyError(f"Unknown incident_id: {incident_id}")
