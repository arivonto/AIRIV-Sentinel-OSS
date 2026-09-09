"""Durable read/write storage for derived AIRIV Sentinel incident reports.

The store persists reporting artifacts only. It does not own Incident lifecycle,
Commander authority, remediation policy, execution, or verification.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from sentinel.incident_reporting import IncidentReport


_STORE_SCHEMA_VERSION = "AIRIV_SENTINEL_INCIDENT_REPORT_STORE_V1"
_REPORT_SCHEMA_VERSION = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"
_INCIDENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _validate_incident_id(incident_id: str) -> str:
    if not isinstance(incident_id, str) or not _INCIDENT_ID_RE.fullmatch(
        incident_id
    ):
        raise ValueError("incident_id contains unsafe path characters")
    return incident_id


def _canonical_report_bytes(report: Mapping[str, Any]) -> bytes:
    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _report_digest(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_report_bytes(report)).hexdigest()


def _validate_report_payload(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise ValueError("stored report must be a mapping")
    if report.get("schema_version") != _REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported incident report schema")

    incident_id = report.get("incident_id")
    _validate_incident_id(incident_id)

    required = (
        "component_id",
        "lifecycle_state",
        "final_status",
        "commander_attention_required",
        "evidence_count",
        "timeline",
    )
    missing = [key for key in required if key not in report]
    if missing:
        raise ValueError(
            "incident report missing required fields: " + ", ".join(missing)
        )

    timeline = report["timeline"]
    if not isinstance(timeline, list):
        raise ValueError("incident report timeline must be a list")
    evidence_count = report["evidence_count"]
    if not isinstance(evidence_count, int) or evidence_count < 0:
        raise ValueError("incident report evidence_count must be non-negative")
    if evidence_count != len(timeline):
        raise ValueError("incident report evidence_count does not match timeline")
    if not isinstance(report["commander_attention_required"], bool):
        raise ValueError("commander_attention_required must be boolean")


def _write_atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("incident report store envelope must be an object")
    return data


class IncidentReportStore:
    """Durable filesystem store for derived, non-authoritative reports."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(
            root
            or os.environ.get(
                "AIRIV_SENTINEL_INCIDENT_REPORT_DIR",
                "var/incident_reports",
            )
        )

    def _report_path(self, incident_id: str) -> Path:
        safe_id = _validate_incident_id(incident_id)
        return self.root / "reports" / f"{safe_id}.json"

    def save(self, report: IncidentReport) -> None:
        if not isinstance(report, IncidentReport):
            raise TypeError("report must be an IncidentReport")

        payload = report.to_dict()
        _validate_report_payload(payload)
        incident_id = payload["incident_id"]

        envelope = {
            "store_schema_version": _STORE_SCHEMA_VERSION,
            "report_sha256": _report_digest(payload),
            "report": payload,
        }
        _write_atomic_json(self._report_path(incident_id), envelope)

    def get(self, incident_id: str) -> dict[str, Any] | None:
        path = self._report_path(incident_id)
        if not path.exists():
            return None

        envelope = _read_json(path)
        if envelope.get("store_schema_version") != _STORE_SCHEMA_VERSION:
            raise ValueError("unsupported incident report store schema")

        report = envelope.get("report")
        if not isinstance(report, dict):
            raise ValueError("incident report store envelope missing report")
        _validate_report_payload(report)

        expected = envelope.get("report_sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("incident report store digest is invalid")
        actual = _report_digest(report)
        if actual != expected:
            raise ValueError("incident report store digest mismatch")

        if report["incident_id"] != incident_id:
            raise ValueError("stored incident_id does not match report path")

        return deepcopy(report)

    def list_incident_ids(self) -> list[str]:
        reports_dir = self.root / "reports"
        if not reports_dir.exists():
            return []

        incident_ids: list[str] = []
        for path in sorted(reports_dir.glob("*.json")):
            incident_ids.append(_validate_incident_id(path.stem))
        return incident_ids

    def recover(self) -> list[dict[str, Any]]:
        """Load all durable reports in deterministic incident-id order.

        Corrupt or malformed reports fail closed instead of being skipped.
        """
        recovered: list[dict[str, Any]] = []
        for incident_id in self.list_incident_ids():
            report = self.get(incident_id)
            if report is None:
                raise RuntimeError(
                    f"incident report disappeared during recovery: {incident_id}"
                )
            recovered.append(report)
        return recovered
