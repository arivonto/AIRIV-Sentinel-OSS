from copy import deepcopy

import pytest

from sentinel.incident_evidence import EvidenceCompleteIncidentReportBuilder
from sentinel.incident_evidence_integrity import (
    IncidentEvidenceIntegrityAuditor,
    verify_integrity_audit,
)
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incidents.manager import Incident, IncidentManager


def _observation(component_id: str) -> dict:
    return {
        "pane_id": component_id,
        "window_name": "lane-2-integrity-fixture",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "a" * 64,
        "agent_identity": "AIRIV_SYSTEM",
        "normalized_input": {"pane_dead": False, "activity_state": "FAILED"},
    }


def _complete_incident(incident_id: str, component_id: str) -> Incident:
    manager = IncidentManager()
    observation = _observation(component_id)
    incident = Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="AIRIV_SYSTEM",
        anomaly_type="FAILED",
    )
    incident.add_evidence(
        observation,
        "Deterministic failure detected.",
        "ANOMALY",
        {"observed_state": "FAILED"},
    )
    manager.active_incidents[component_id] = incident
    manager.investigate(component_id)
    incident.add_evidence(
        {},
        "Fixture diagnostics completed without creating operational authority.",
        "DIAGNOSTIC_RESULT",
        {"success": True, "understanding": "fixture diagnostic evidence"},
    )
    manager.resolve(
        component_id,
        recovery_evidence={"verified": True, "reason": "fixture terminal evidence"},
        observation=observation,
        final_outcome="UNRESOLVED",
    )
    return incident


def _incomplete_incident(incident_id: str, component_id: str) -> Incident:
    incident = Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="AIRIV_SYSTEM",
        anomaly_type="FAILED",
    )
    incident.add_evidence(
        _observation(component_id),
        "Detection-only fixture intentionally lacks diagnostics.",
        "ANOMALY",
        {"observed_state": "FAILED"},
    )
    return incident


def _store(tmp_path):
    store = IncidentReportStore(tmp_path / "reports")
    builder = EvidenceCompleteIncidentReportBuilder()
    store.save(builder.build(_complete_incident("INC-LANE2-AUDIT-001", "%41")))
    store.save(builder.build(_incomplete_incident("INC-LANE2-AUDIT-002", "%42")))
    return store


def test_store_wide_audit_distinguishes_integrity_from_completeness(tmp_path):
    store = _store(tmp_path)
    before = store.recover()
    auditor = IncidentEvidenceIntegrityAuditor(store)

    first = auditor.run()
    second = auditor.run()
    payload = first.to_dict()

    assert payload == second.to_dict()
    assert payload["integrity_verified"] is True
    assert payload["report_count"] == 2
    assert payload["complete_report_count"] == 1
    assert payload["incomplete_report_count"] == 1
    assert payload["all_evidence_complete"] is False
    assert payload["evidence_event_count"] == sum(
        item["evidence_event_count"] for item in payload["reports"]
    )
    assert verify_integrity_audit(payload) is True

    complete = next(
        item for item in payload["reports"]
        if item["incident_id"] == "INC-LANE2-AUDIT-001"
    )
    incomplete = next(
        item for item in payload["reports"]
        if item["incident_id"] == "INC-LANE2-AUDIT-002"
    )
    assert complete["evidence_completeness"]["complete"] is True
    assert complete["evidence_completeness"]["missing"] == []
    assert incomplete["evidence_completeness"]["complete"] is False
    assert "diagnostics_understanding" in incomplete["evidence_completeness"]["missing"]

    markdown = first.to_markdown()
    assert markdown == second.to_markdown()
    assert "Integrity:** `VERIFIED`" in markdown
    assert "INC-LANE2-AUDIT-001" in markdown
    assert "INC-LANE2-AUDIT-002" in markdown
    assert store.recover() == before

    with pytest.raises(TypeError):
        first.payload["report_count"] = 99
    with pytest.raises(TypeError):
        first.payload["reports"][0]["incident_id"] = "tampered"


def test_corrupt_durable_timeline_fails_closed(tmp_path):
    store = _store(tmp_path)
    corrupt = store.get("INC-LANE2-AUDIT-001")
    assert corrupt is not None
    corrupt = deepcopy(corrupt)
    corrupt["timeline"][0]["reason"] = "tampered after evidence seal"

    class CorruptStore:
        def get(self, incident_id):
            return deepcopy(corrupt) if incident_id == corrupt["incident_id"] else None

        def recover(self):
            return [deepcopy(corrupt)]

    with pytest.raises(ValueError, match="integrity"):
        IncidentEvidenceIntegrityAuditor(CorruptStore()).run()


def test_duplicate_incident_identity_fails_closed(tmp_path):
    store = _store(tmp_path)
    report = store.get("INC-LANE2-AUDIT-001")
    assert report is not None

    class DuplicateStore:
        def get(self, incident_id):
            return deepcopy(report) if incident_id == report["incident_id"] else None

        def recover(self):
            return [deepcopy(report), deepcopy(report)]

    with pytest.raises(ValueError, match="duplicate incident_id"):
        IncidentEvidenceIntegrityAuditor(DuplicateStore()).run()


def test_contradictory_completeness_metadata_fails_closed(tmp_path):
    store = _store(tmp_path)
    report = store.get("INC-LANE2-AUDIT-002")
    assert report is not None
    contradictory = deepcopy(report)
    contradictory["evidence_completeness"]["complete"] = True

    class ContradictoryStore:
        def get(self, incident_id):
            return deepcopy(contradictory) if incident_id == contradictory["incident_id"] else None

        def recover(self):
            return [deepcopy(contradictory)]

    with pytest.raises(ValueError, match="complete flag mismatch"):
        IncidentEvidenceIntegrityAuditor(ContradictoryStore()).run()


def test_audit_manifest_tampering_is_detected(tmp_path):
    audit = IncidentEvidenceIntegrityAuditor(_store(tmp_path)).run().to_dict()
    assert verify_integrity_audit(audit) is True

    tampered_count = deepcopy(audit)
    tampered_count["reports"][0]["evidence_event_count"] += 1
    assert verify_integrity_audit(tampered_count) is False

    tampered_missing = deepcopy(audit)
    tampered_missing["reports"][0]["evidence_completeness"]["missing"] = [
        "fabricated_missing_field"
    ]
    assert verify_integrity_audit(tampered_missing) is False

    tampered_digest = deepcopy(audit)
    tampered_digest["audit_sha256"] = "0" * 64
    assert verify_integrity_audit(tampered_digest) is False


def test_empty_store_has_deterministic_valid_audit(tmp_path):
    store = IncidentReportStore(tmp_path / "empty-reports")
    audit = IncidentEvidenceIntegrityAuditor(store).run()
    payload = audit.to_dict()

    assert payload["report_count"] == 0
    assert payload["complete_report_count"] == 0
    assert payload["incomplete_report_count"] == 0
    assert payload["evidence_event_count"] == 0
    assert payload["all_evidence_complete"] is True
    assert payload["reports"] == []
    assert verify_integrity_audit(payload) is True
