from sentinel.incident_evidence import EvidenceCompleteIncidentReportBuilder
from sentinel.incidents.manager import IncidentManager


def _observation(component_id: str = "%52") -> dict:
    return {
        "pane_id": component_id,
        "window_name": "lane-2-terminal-completeness-fixture",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "f" * 64,
        "agent_identity": "AIRIV_SYSTEM",
        "normalized_input": {
            "pane_dead": False,
            "activity_state": "FAILED",
        },
    }


def _diagnosed_incident(manager: IncidentManager):
    incident = manager.evaluate_anomaly(
        observation=_observation(),
        anomaly_type="FAILED",
        reason="Deterministic fixture failure detected.",
        signal={"observed_state": "FAILED"},
    )
    incident.add_evidence(
        {},
        "Read-only fixture diagnostics produced understanding.",
        "DIAGNOSTIC_RESULT",
        {
            "success": True,
            "understanding": "fixture diagnostics completed",
        },
    )
    return incident


def test_active_incident_with_diagnostics_is_not_evidence_complete():
    manager = IncidentManager()
    incident = _diagnosed_incident(manager)
    builder = EvidenceCompleteIncidentReportBuilder()

    open_report = builder.build(incident).to_dict()
    assert open_report["lifecycle_state"] == "OPEN"
    assert open_report["final_incident_status"] == "OPEN"
    assert open_report["evidence_completeness"]["checks"]["diagnostics_understanding"] is True
    assert open_report["evidence_completeness"]["checks"]["final_incident_status"] is False
    assert open_report["evidence_completeness"]["complete"] is False
    assert open_report["evidence_completeness"]["missing"] == ["final_incident_status"]

    manager.investigate(incident.component_id)
    investigating_report = builder.build(incident).to_dict()
    assert investigating_report["lifecycle_state"] == "INVESTIGATING"
    assert investigating_report["final_incident_status"] == "INVESTIGATING"
    assert investigating_report["evidence_completeness"]["checks"]["final_incident_status"] is False
    assert investigating_report["evidence_completeness"]["complete"] is False


def test_terminal_outcome_closes_final_status_completeness_gap():
    manager = IncidentManager()
    incident = _diagnosed_incident(manager)
    builder = EvidenceCompleteIncidentReportBuilder()

    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={
            "verified": False,
            "reason": "fixture terminalization evidence",
        },
        observation=_observation(),
        final_outcome="UNRESOLVED",
    )

    report = builder.build(incident).to_dict()
    assert report["lifecycle_state"] == "TERMINAL"
    assert report["final_incident_status"] == "UNRESOLVED"
    assert report["evidence_completeness"]["checks"]["final_incident_status"] is True
    assert report["evidence_completeness"]["complete"] is True
    assert report["evidence_completeness"]["missing"] == []
