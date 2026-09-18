"""Deterministic read-only integrity audit for durable S1 incident evidence.

This module audits already-persisted incident evidence reports through the
integrity-checked IncidentEvidenceQueryService. It does not mutate Incident
lifecycle, diagnostic state, Commander authority, remediation policy,
execution state, verification state, report persistence, or host state.

Integrity and evidence completeness are intentionally distinct: an incomplete
report may be structurally valid and integrity-verified. Corruption,
contradictory completeness metadata, duplicate incident identity, or audit
manifest tampering fails closed.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from sentinel.incident_evidence_query import IncidentEvidenceQueryService


_AUDIT_SCHEMA_VERSION = "AIRIV_SENTINEL_INCIDENT_EVIDENCE_INTEGRITY_AUDIT_V1"


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


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_completeness(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("evidence_completeness must be a mapping")

    complete = raw.get("complete")
    checks = raw.get("checks")
    missing = raw.get("missing")
    if not isinstance(complete, bool):
        raise ValueError("evidence_completeness.complete must be boolean")
    if not isinstance(checks, Mapping):
        raise ValueError("evidence_completeness.checks must be a mapping")
    if not isinstance(missing, list):
        raise ValueError("evidence_completeness.missing must be a list")

    normalized_checks: dict[str, bool] = {}
    for key, value in checks.items():
        if not isinstance(key, str) or not key:
            raise ValueError("evidence completeness check names must be non-empty strings")
        if not isinstance(value, bool):
            raise ValueError("evidence completeness check values must be boolean")
        normalized_checks[key] = value

    normalized_missing: list[str] = []
    for item in missing:
        if not isinstance(item, str) or not item:
            raise ValueError("evidence completeness missing entries must be non-empty strings")
        if item in normalized_missing:
            raise ValueError("evidence completeness missing entries must be unique")
        normalized_missing.append(item)

    failed_checks = sorted(
        name for name, passed in normalized_checks.items() if not passed
    )
    if sorted(normalized_missing) != failed_checks:
        raise ValueError("evidence completeness missing/checks mismatch")
    if complete is not (not failed_checks):
        raise ValueError("evidence completeness complete flag mismatch")

    return {
        "complete": complete,
        "checks": dict(sorted(normalized_checks.items())),
        "missing": failed_checks,
    }


def _audit_digest(payload_without_digest: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload_without_digest)).hexdigest()


def verify_integrity_audit(raw: Mapping[str, Any]) -> bool:
    """Verify a standalone audit manifest without accessing the report store."""
    try:
        if not isinstance(raw, Mapping):
            return False
        payload = deepcopy(dict(raw))
        digest = payload.pop("audit_sha256", None)
        if not _is_sha256(digest):
            return False
        if payload.get("schema_version") != _AUDIT_SCHEMA_VERSION:
            return False
        reports = payload.get("reports")
        if not isinstance(reports, list):
            return False
        if payload.get("integrity_verified") is not True:
            return False

        seen: set[str] = set()
        ordering: list[tuple[datetime, str]] = []
        complete_count = 0
        commander_count = 0
        evidence_count = 0

        for expected_sequence, report in enumerate(reports, start=1):
            if not isinstance(report, Mapping):
                return False
            if report.get("sequence") != expected_sequence:
                return False
            incident_id = report.get("incident_id")
            component_id = report.get("component_id")
            if not isinstance(incident_id, str) or not incident_id:
                return False
            if not isinstance(component_id, str) or not component_id:
                return False
            if incident_id in seen:
                return False
            seen.add(incident_id)

            started = _parse_timestamp(report.get("started_at"), "started_at")
            _parse_timestamp(report.get("updated_at"), "updated_at")
            ordering.append((started, incident_id))

            timeline_sha256 = report.get("timeline_sha256")
            if not _is_sha256(timeline_sha256):
                return False
            event_count = report.get("evidence_event_count")
            if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 0:
                return False
            evidence_count += event_count

            completeness = _validate_completeness(report.get("evidence_completeness"))
            if completeness["complete"]:
                complete_count += 1
            commander_required = report.get("commander_required")
            if not isinstance(commander_required, bool):
                return False
            if commander_required:
                commander_count += 1

        if ordering != sorted(ordering, key=lambda item: (item[0], item[1])):
            return False

        report_count = len(reports)
        incomplete_count = report_count - complete_count
        if payload.get("report_count") != report_count:
            return False
        if payload.get("complete_report_count") != complete_count:
            return False
        if payload.get("incomplete_report_count") != incomplete_count:
            return False
        if payload.get("commander_required_count") != commander_count:
            return False
        if payload.get("evidence_event_count") != evidence_count:
            return False
        if payload.get("all_evidence_complete") is not (incomplete_count == 0):
            return False

        return digest == _audit_digest(payload)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class IncidentEvidenceIntegrityAudit:
    """Immutable store-wide incident evidence integrity manifest."""

    _payload: Mapping[str, Any]

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._payload)

    def to_markdown(self) -> str:
        data = self.to_dict()
        lines = [
            "# AIRIV Sentinel Incident Evidence Integrity Audit",
            "",
            "- **Integrity:** `VERIFIED`",
            f"- **Reports:** `{data['report_count']}`",
            f"- **Evidence events:** `{data['evidence_event_count']}`",
            f"- **Complete reports:** `{data['complete_report_count']}`",
            f"- **Incomplete reports:** `{data['incomplete_report_count']}`",
            f"- **Commander-required reports:** `{data['commander_required_count']}`",
            f"- **All evidence complete:** `{'YES' if data['all_evidence_complete'] else 'NO'}`",
            f"- **Audit SHA-256:** `{data['audit_sha256']}`",
            "",
            "## Reports",
        ]
        if not data["reports"]:
            lines.append("- None recorded.")
        else:
            for report in data["reports"]:
                completeness = report["evidence_completeness"]
                state = "COMPLETE" if completeness["complete"] else "INCOMPLETE"
                missing = ", ".join(completeness["missing"]) or "NONE"
                lines.append(
                    "- "
                    f"`#{report['sequence']}` · `{report['incident_id']}` · "
                    f"component `{report['component_id']}` · **{state}** · "
                    f"events `{report['evidence_event_count']}` · missing `{missing}`"
                )
        return "\n".join(lines) + "\n"


class IncidentEvidenceIntegrityAuditor:
    """Audit every durable S1 evidence report through validated read paths."""

    def __init__(self, store: Any) -> None:
        self._query = IncidentEvidenceQueryService(store)

    def run(self) -> IncidentEvidenceIntegrityAudit:
        """Return one deterministic manifest; any corruption aborts the audit."""
        result = self._query.search()
        summaries = result.to_list()

        seen: set[str] = set()
        reports: list[dict[str, Any]] = []
        complete_count = 0
        commander_count = 0
        evidence_count = 0

        for sequence, summary in enumerate(summaries, start=1):
            incident_id = summary["incident_id"]
            if incident_id in seen:
                raise ValueError(f"duplicate incident_id in evidence store: {incident_id}")
            seen.add(incident_id)

            completeness = _validate_completeness(summary["evidence_completeness"])
            timeline_sha256 = summary["timeline_sha256"]
            if not _is_sha256(timeline_sha256):
                raise ValueError("incident evidence timeline_sha256 must be lowercase SHA-256")

            event_count = summary["matched_event_count"]
            matched_events = summary["matched_events"]
            if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 0:
                raise ValueError("incident evidence event count must be non-negative")
            if not isinstance(matched_events, list) or event_count != len(matched_events):
                raise ValueError("incident evidence event count mismatch")

            commander_required = summary["commander_decision_requirement"]["required"]
            if not isinstance(commander_required, bool):
                raise ValueError("commander requirement must be boolean")

            reports.append(
                {
                    "sequence": sequence,
                    "incident_id": incident_id,
                    "component_id": summary["component_id"],
                    "started_at": summary["started_at"],
                    "updated_at": summary["updated_at"],
                    "final_incident_status": summary["final_incident_status"],
                    "timeline_sha256": timeline_sha256,
                    "evidence_event_count": event_count,
                    "evidence_completeness": completeness,
                    "commander_required": commander_required,
                }
            )
            evidence_count += event_count
            if completeness["complete"]:
                complete_count += 1
            if commander_required:
                commander_count += 1

        report_count = len(reports)
        incomplete_count = report_count - complete_count
        payload: dict[str, Any] = {
            "schema_version": _AUDIT_SCHEMA_VERSION,
            "integrity_verified": True,
            "report_count": report_count,
            "complete_report_count": complete_count,
            "incomplete_report_count": incomplete_count,
            "commander_required_count": commander_count,
            "evidence_event_count": evidence_count,
            "all_evidence_complete": incomplete_count == 0,
            "reports": reports,
        }
        payload["audit_sha256"] = _audit_digest(payload)

        if not verify_integrity_audit(payload):
            raise ValueError("constructed incident evidence integrity audit is invalid")
        return IncidentEvidenceIntegrityAudit(_freeze(payload))
