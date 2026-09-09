from copy import deepcopy

import pytest

from sentinel.incident_reporting import IncidentReportBuilder
from sentinel.incidents.manager import IncidentManager


def _observation(component_id: str = "%7"):
    return {
        "pane_id": component_id,
        "window_name": "sentinel-test",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "a" * 64,
        "agent_identity": "AIRIV_SYSTEM",
    }


def _active_incident(manager: IncidentManager):
    return manager.evaluate_anomaly(
        observation=_observation(),
        anomaly_type="FAILED",
        reason="Synthetic failure detected",
        signal={"source": "test"},
    )


def test_active_report_is_read_only_and_preserves_incident_state():
    manager = IncidentManager()
    incident = _active_incident(manager)
    manager.investigate(incident.component_id, "Investigation started")
    incident.add_evidence(
        _observation(),
        "Root cause established",
        "DIAGNOSIS",
        {"diagnosis": "synthetic"},
    )

    before = deepcopy(incident.to_dict())
    report = IncidentReportBuilder().build(incident)

    assert incident.to_dict() == before
    assert report.payload["incident_id"] == incident.incident_id
    assert report.payload["lifecycle_state"] == "INVESTIGATING"
    assert report.payload["final_status"] == "INVESTIGATING"
    assert report.payload["evidence_count"] == len(before["evidence_trail"])
    assert report.payload["detection_and_understanding"]
    assert report.payload["diagnostic_actions"]

    with pytest.raises(TypeError):
        report.payload["final_status"] = "RECOVERED"


def test_terminal_recovered_report_uses_final_outcome_and_verification_evidence():
    manager = IncidentManager()
    incident = _active_incident(manager)

    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={"verified": True, "check": "synthetic-health"},
        observation=_observation(),
        final_outcome="RECOVERED",
    )

    report = IncidentReportBuilder().build_from_manager(
        manager, incident.incident_id
    )

    assert report.payload["lifecycle_state"] == "TERMINAL"
    assert report.payload["final_outcome"] == "RECOVERED"
    assert report.payload["final_status"] == "RECOVERED"
    assert any(
        event["signal_type"] == "RECOVERY"
        for event in report.payload["verification_results"]
    )


def test_escalated_terminal_report_requires_commander_attention():
    manager = IncidentManager()
    incident = _active_incident(manager)

    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={"terminalization_basis": "commander escalation"},
        observation=_observation(),
        final_outcome="ESCALATED",
    )

    report = IncidentReportBuilder().build_from_manager(
        manager, incident.incident_id
    )

    assert report.payload["final_status"] == "ESCALATED"
    assert report.payload["commander_attention_required"] is True


def test_commander_required_signal_is_surfaced_without_state_mutation():
    manager = IncidentManager()
    incident = _active_incident(manager)
    incident.add_evidence(
        _observation(),
        "Commander approval required for next effect",
        "COMMANDER_HANDOFF",
        {
            "commander_required": True,
            "requested_action": "RESTART",
        },
    )
    before = deepcopy(incident.to_dict())

    report = IncidentReportBuilder().build(incident)

    assert incident.to_dict() == before
    assert report.payload["commander_attention_required"] is True
    assert len(report.payload["commander_decisions"]) == 1
    assert (
        report.payload["commander_decisions"][0]["signal_type"]
        == "COMMANDER_HANDOFF"
    )


def test_report_classifies_remediation_and_verification_timeline():
    manager = IncidentManager()
    incident = _active_incident(manager)
    incident.add_evidence(
        _observation(),
        "Authorized exact remediation executed",
        "REMEDIATION_EXECUTION",
        {"execution_id": "EXEC-test", "succeeded": True},
    )
    incident.add_evidence(
        _observation(),
        "Independent post-effect verification passed",
        "VERIFICATION",
        {"verified": True},
    )

    report = IncidentReportBuilder().build(incident)

    assert [
        event["signal_type"] for event in report.payload["remediation_actions"]
    ] == ["REMEDIATION_EXECUTION"]
    assert [
        event["signal_type"] for event in report.payload["verification_results"]
    ] == ["VERIFICATION"]
    assert [event["sequence"] for event in report.payload["timeline"]] == [
        1,
        2,
        3,
    ]


def test_build_from_manager_reads_active_then_terminal_same_incident():
    manager = IncidentManager()
    incident = _active_incident(manager)
    builder = IncidentReportBuilder()

    active_report = builder.build_from_manager(manager, incident.incident_id)
    assert active_report.payload["final_status"] == "OPEN"

    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={"verified": True},
        observation=_observation(),
        final_outcome="UNRESOLVED",
    )

    terminal_report = builder.build_from_manager(manager, incident.incident_id)
    assert terminal_report.payload["lifecycle_state"] == "TERMINAL"
    assert terminal_report.payload["final_status"] == "UNRESOLVED"
    assert manager.get_incident_by_id(incident.incident_id) is None


def test_report_defensive_copy_markdown_and_malformed_evidence_fail_closed():
    manager = IncidentManager()
    incident = _active_incident(manager)
    report = IncidentReportBuilder().build(incident)

    exported = report.to_dict()
    exported["incident_id"] = "tampered"
    exported["timeline"][0]["reason"] = "tampered"

    assert report.payload["incident_id"] == incident.incident_id
    assert report.payload["timeline"][0]["reason"] == "Synthetic failure detected"

    markdown = report.to_markdown()
    assert "# AIRIV Sentinel Incident Report" in markdown
    assert incident.incident_id in markdown
    assert "## Evidence timeline" in markdown
    assert "Commander attention" in markdown

    malformed = incident.to_dict()
    malformed["evidence_trail"] = ["not-a-mapping"]
    with pytest.raises(ValueError, match="entries must be mappings"):
        IncidentReportBuilder().build(malformed)

    with pytest.raises(KeyError, match="Unknown incident_id"):
        IncidentReportBuilder().build_from_manager(manager, "INC-missing")
