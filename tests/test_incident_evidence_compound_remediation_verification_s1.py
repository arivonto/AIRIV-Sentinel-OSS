from sentinel.incident_evidence import EvidenceCompleteIncidentReportBuilder
from sentinel.incident_evidence_inspection import IncidentEvidenceInspector
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incidents.manager import IncidentManager


def _observation(component_id: str = "%61") -> dict:
    return {
        "pane_id": component_id,
        "window_name": "lane-2-compound-remediation-fixture",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "6" * 64,
        "agent_identity": "AIRIV_SYSTEM",
        "normalized_input": {
            "pane_dead": False,
            "activity_state": "FAILED",
        },
    }


def _incident(manager: IncidentManager, component_id: str = "%61"):
    incident = manager.evaluate_anomaly(
        observation=_observation(component_id),
        anomaly_type="FAILED",
        reason="Deterministic compound-evidence fixture detected.",
        signal={"observed_state": "FAILED"},
    )
    incident.add_evidence(
        {},
        "Read-only diagnostics established fixture understanding.",
        "DIAGNOSTIC_RESULT",
        {
            "success": True,
            "understanding": "fixture diagnostic understanding",
        },
    )
    return incident


def _remediation_signal(*, verified: bool) -> dict:
    return {
        "decision": "ALLOW",
        "decision_reason": "deterministic fixture policy decision",
        "action": "FIXTURE_READ_ONLY_ACTION",
        "execution_id": "EXEC-LANE2-COMPOUND-001",
        "replayed": False,
        "execution": {
            "command": "fixture-noop",
            "stdout": "fixture stdout",
            "stderr": "",
            "exit_code": 0,
            "success": True,
        },
        "verification": {
            "verified": verified,
            "reason": "fixture verification result",
            "observation": {"state": "RECOVERED" if verified else "FAILED"},
        },
    }


def _terminalize(manager: IncidentManager, incident, final_outcome: str) -> None:
    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={
            "verified": final_outcome == "RECOVERED",
            "reason": "fixture terminalization evidence",
        },
        observation=_observation(incident.component_id),
        final_outcome=final_outcome,
    )


def test_remediation_verified_is_preserved_in_both_projection_views():
    manager = IncidentManager()
    incident = _incident(manager)
    incident.add_evidence(
        {},
        "Canonical remediation execution and verification succeeded.",
        "REMEDIATION_VERIFIED",
        _remediation_signal(verified=True),
    )
    _terminalize(manager, incident, "RECOVERED")

    report = EvidenceCompleteIncidentReportBuilder().build(incident).to_dict()

    remediation_types = [event["signal_type"] for event in report["remediation_actions"]]
    verification_types = [event["signal_type"] for event in report["verification_results"]]

    assert "REMEDIATION_VERIFIED" in remediation_types
    assert "REMEDIATION_VERIFIED" in verification_types
    assert report["remediation_eligibility_status"]["known"] is True
    assert report["remediation_eligibility_status"]["eligibility"] == "ELIGIBLE"
    assert report["remediation_eligibility_status"]["status"] == "REMEDIATION_VERIFIED"
    assert report["verification_result"]["signal_type"] == "REMEDIATION_VERIFIED"
    assert report["verification_result"]["signal_snapshot"]["verification"]["verified"] is True
    assert report["evidence_completeness"]["complete"] is True


def test_remediation_verification_failed_is_preserved_in_both_projection_views():
    manager = IncidentManager()
    incident = _incident(manager, "%62")
    incident.add_evidence(
        {},
        "Canonical remediation verification failed.",
        "REMEDIATION_VERIFICATION_FAILED",
        _remediation_signal(verified=False),
    )
    _terminalize(manager, incident, "UNRESOLVED")

    report = EvidenceCompleteIncidentReportBuilder().build(incident).to_dict()

    remediation_types = [event["signal_type"] for event in report["remediation_actions"]]
    verification_types = [event["signal_type"] for event in report["verification_results"]]

    assert "REMEDIATION_VERIFICATION_FAILED" in remediation_types
    assert "REMEDIATION_VERIFICATION_FAILED" in verification_types
    assert report["remediation_eligibility_status"]["known"] is True
    assert report["remediation_eligibility_status"]["eligibility"] == "ELIGIBLE"
    assert report["remediation_eligibility_status"]["status"] == "REMEDIATION_VERIFICATION_FAILED"
    assert report["verification_result"]["signal_type"] == "REMEDIATION_VERIFICATION_FAILED"
    assert report["verification_result"]["signal_snapshot"]["verification"]["verified"] is False
    assert report["evidence_completeness"]["complete"] is True


def test_executed_unverified_is_not_promoted_to_verification_evidence():
    manager = IncidentManager()
    incident = _incident(manager, "%63")
    signal = _remediation_signal(verified=False)
    signal.pop("verification")
    incident.add_evidence(
        {},
        "Canonical remediation execution completed without verification.",
        "REMEDIATION_EXECUTED_UNVERIFIED",
        signal,
    )

    report = EvidenceCompleteIncidentReportBuilder().build(incident).to_dict()

    remediation_types = [event["signal_type"] for event in report["remediation_actions"]]
    verification_types = [event["signal_type"] for event in report["verification_results"]]

    assert "REMEDIATION_EXECUTED_UNVERIFIED" in remediation_types
    assert "REMEDIATION_EXECUTED_UNVERIFIED" not in verification_types
    assert report["verification_result"] is None
    assert report["remediation_eligibility_status"]["eligibility"] == "ELIGIBLE"
    assert report["evidence_completeness"]["complete"] is False
    assert "verification_accounted_for" in report["evidence_completeness"]["missing"]
    assert "final_incident_status" in report["evidence_completeness"]["missing"]


def test_inspection_preserves_compound_projection_membership(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager, "%64")
    incident.add_evidence(
        {},
        "Canonical remediation verification failed for inspection fixture.",
        "REMEDIATION_VERIFICATION_FAILED",
        _remediation_signal(verified=False),
    )
    _terminalize(manager, incident, "UNRESOLVED")

    report = EvidenceCompleteIncidentReportBuilder().build(incident)
    store = IncidentReportStore(tmp_path / "compound-reports")
    store.save(report)

    inspection = IncidentEvidenceInspector(store).inspect(incident.incident_id).to_dict()
    remediation_types = [event["signal_type"] for event in inspection["remediation"]["events"]]
    verification_types = [event["signal_type"] for event in inspection["verification"]["events"]]

    assert "REMEDIATION_VERIFICATION_FAILED" in remediation_types
    assert "REMEDIATION_VERIFICATION_FAILED" in verification_types
    assert inspection["remediation"]["status"]["status"] == "REMEDIATION_VERIFICATION_FAILED"
    assert inspection["verification"]["latest"]["signal_type"] == "REMEDIATION_VERIFICATION_FAILED"
    assert inspection["evidence_completeness"]["complete"] is True
