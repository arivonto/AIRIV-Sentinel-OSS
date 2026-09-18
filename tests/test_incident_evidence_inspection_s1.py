from copy import deepcopy

import pytest

from sentinel.incident_evidence import EvidenceCompleteIncidentReportBuilder
from sentinel.incident_evidence_inspection import IncidentEvidenceInspector
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incidents.manager import Incident, IncidentManager


def _observation(component_id: str) -> dict:
    return {
        "pane_id": component_id,
        "window_name": "lane-2-inspection-fixture",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "f" * 64,
        "agent_identity": "AIRIV_SYSTEM",
        "source": "TMUX",
        "pane_dead": True,
        "normalized_input": {
            "pane_dead": True,
            "activity_state": "FAILED",
        },
    }


def _complete_incident() -> Incident:
    incident = Incident(
        incident_id="INC-LANE2-INSPECT-001",
        component_id="%41",
        agent_identity="AIRIV_SYSTEM",
        anomaly_type="FAILED",
    )
    incident.add_evidence(
        _observation(incident.component_id),
        "Deterministic fixture failure detected.",
        "ANOMALY",
        {"observed_state": "FAILED"},
    )
    incident.add_evidence(
        {},
        "Fixture diagnostic command failed; evidence retained.",
        "DIAGNOSTIC_FAILURE",
        {
            "diagnostic_action_id": "ACT-INSPECT-001",
            "success": False,
            "exit_code": 17,
            "stderr": "fixture diagnostic failure",
        },
    )
    incident.add_evidence(
        {},
        "Commander decision required before consequential action.",
        "COMMANDER_HANDOFF",
        {
            "commander_required": True,
            "decision": "WAIT_FOR_COMMANDER",
        },
    )
    incident.add_evidence(
        {},
        "Fixture remediation denied; execution did not occur.",
        "REMEDIATION_DENIED",
        {
            "decision": "DENY",
            "decision_reason": "fixture has no execution authority",
        },
    )
    incident.add_evidence(
        {},
        "Read-only fixture verification recorded no execution effect.",
        "VERIFICATION",
        {
            "verified": False,
            "reason": "remediation_not_executed",
        },
    )

    manager = IncidentManager()
    manager.active_incidents[incident.component_id] = incident
    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={
            "verified": False,
            "reason": "fixture terminalization evidence",
        },
        observation=_observation(incident.component_id),
        final_outcome="UNRESOLVED",
    )
    return incident


def _store(tmp_path) -> IncidentReportStore:
    store = IncidentReportStore(tmp_path / "reports")
    report = EvidenceCompleteIncidentReportBuilder().build(_complete_incident())
    store.save(report)
    return store


def test_inspection_snapshot_is_complete_correlated_and_immutable(tmp_path):
    store = _store(tmp_path)
    before = store.recover()

    inspection = IncidentEvidenceInspector(store).inspect(
        "INC-LANE2-INSPECT-001"
    )
    data = inspection.to_dict()

    assert data["schema_version"] == "AIRIV_SENTINEL_INCIDENT_EVIDENCE_INSPECTION_V1"
    assert data["identity"]["incident_id"] == "INC-LANE2-INSPECT-001"
    assert data["identity"]["component_id"] == "%41"
    assert data["identity"]["final_status"] == "UNRESOLVED"
    assert data["integrity"]["verified"] is True
    assert data["integrity"]["event_count"] == len(data["timeline"])
    assert data["integrity"]["timeline_sha256"] == data["timeline"][-1]["event_sha256"]
    assert data["evidence_completeness"]["complete"] is True
    assert data["latest_observed_state"]["state"] == "FAILED"
    assert data["normalized_input_count"] >= 1
    assert data["diagnostics"]["event_count"] >= 1
    assert data["diagnostics"]["failure_count"] == 1
    assert data["diagnostics"]["failures"][0]["signal_type"] == "DIAGNOSTIC_FAILURE"
    assert data["commander"]["required"] is True
    assert data["commander"]["event_count"] == 1
    assert data["remediation"]["status"]["known"] is True
    assert data["remediation"]["status"]["eligibility"] == "DENIED"
    assert data["verification"]["event_count"] >= 1
    assert data["verification"]["latest"] is not None

    with pytest.raises(TypeError):
        inspection.payload["identity"]["incident_id"] = "tampered"
    with pytest.raises(TypeError):
        inspection.payload["timeline"][0]["reason"] = "tampered"

    exported = inspection.to_dict()
    exported["identity"]["incident_id"] = "changed-copy"
    assert inspection.payload["identity"]["incident_id"] == "INC-LANE2-INSPECT-001"
    assert store.recover() == before


def test_markdown_is_deterministic_and_contains_forensic_landmarks(tmp_path):
    inspection = IncidentEvidenceInspector(_store(tmp_path)).inspect(
        "INC-LANE2-INSPECT-001"
    )

    first = inspection.to_markdown()
    second = inspection.to_markdown()

    assert first == second
    assert "AIRIV Sentinel Incident Evidence Inspection" in first
    assert "INC-LANE2-INSPECT-001" in first
    assert "Timeline integrity:** `VERIFIED`" in first
    assert "DIAGNOSTIC_FAILURE" in first
    assert "COMMANDER_HANDOFF" in first
    assert "REMEDIATION_DENIED" in first
    assert "VERIFICATION" in first
    assert "Decision required:** `YES`" in first


def test_detection_only_inspection_preserves_explicit_incompleteness(tmp_path):
    incident = Incident(
        incident_id="INC-LANE2-INSPECT-INCOMPLETE",
        component_id="%42",
        agent_identity="AIRIV_SYSTEM",
        anomaly_type="FAILED",
    )
    incident.add_evidence(
        _observation(incident.component_id),
        "Detection-only fixture.",
        "ANOMALY",
        {"observed_state": "FAILED"},
    )

    store = IncidentReportStore(tmp_path / "incomplete-reports")
    store.save(EvidenceCompleteIncidentReportBuilder().build(incident))

    inspection = IncidentEvidenceInspector(store).inspect(incident.incident_id)
    data = inspection.to_dict()

    assert data["evidence_completeness"]["complete"] is False
    assert "diagnostics_understanding" in data["evidence_completeness"]["missing"]
    assert data["diagnostics"]["event_count"] == 0
    assert data["diagnostics"]["failure_count"] == 0
    assert data["commander"]["required"] is False
    assert "Complete:** `NO`" in inspection.to_markdown()
    assert "diagnostics_understanding" in inspection.to_markdown()


def test_unknown_incident_fails_explicitly(tmp_path):
    inspector = IncidentEvidenceInspector(_store(tmp_path))

    with pytest.raises(KeyError, match="Unknown incident_id"):
        inspector.inspect("INC-LANE2-UNKNOWN")


def test_tampered_durable_report_fails_closed_before_inspection(tmp_path):
    store = _store(tmp_path)
    valid = store.get("INC-LANE2-INSPECT-001")
    assert valid is not None

    corrupt = deepcopy(valid)
    corrupt["timeline"][0]["reason"] = "tampered after evidence seal"

    class CorruptStore:
        def get(self, incident_id):
            if incident_id == corrupt["incident_id"]:
                return deepcopy(corrupt)
            return None

        def recover(self):
            return [deepcopy(corrupt)]

    inspector = IncidentEvidenceInspector(CorruptStore())

    with pytest.raises(ValueError, match="integrity"):
        inspector.inspect("INC-LANE2-INSPECT-001")
