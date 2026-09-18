from copy import deepcopy
from datetime import timedelta

import pytest

from sentinel.diagnostic.executor import DiagnosticResult
from sentinel.diagnostic.investigation import InvestigationManager
from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    Hypothesis,
    HypothesisStatus,
    Observation,
)
from sentinel.diagnostic.store import InvestigationStore
from sentinel.incident_evidence import (
    EvidenceCompleteIncidentReportBuilder,
    verify_timeline_integrity,
)
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incidents.manager import IncidentManager


def _observation(component_id: str = "%7") -> dict:
    return {
        "pane_id": component_id,
        "window_name": "lane-2-fixture",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "d" * 64,
        "agent_identity": "AIRIV_SYSTEM",
        "source": "TMUX",
        "pane_dead": True,
        "normalized_input": {
            "pane_dead": True,
            "activity_state": "FAILED",
        },
    }


def _incident(manager: IncidentManager):
    return manager.evaluate_anomaly(
        observation=_observation(),
        anomaly_type="FAILED",
        reason="Deterministic simulated failure detected",
        signal={"source": "lane2-fixture", "observed_state": "FAILED"},
    )


def _diagnostic_store(tmp_path, incident) -> InvestigationStore:
    store = InvestigationStore(tmp_path / "diagnostic")
    manager = InvestigationManager(store)
    investigation = manager.start(
        incident_id=incident.incident_id,
        component_id=incident.component_id,
        trigger="FAILED",
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=2,
            max_repeated_action=1,
            max_risk=2,
            minimum_evidence=1,
        ),
        investigation_id="INV-LANE2-0001",
    )

    started_at = investigation.created_at + timedelta(seconds=1)
    finished_at = investigation.created_at + timedelta(seconds=2)
    evidence_id = "diagnostic:INV-LANE2-0001:ACT-LANE2-0001"

    action = DiagnosticAction(
        diagnostic_action_id="ACT-LANE2-0001",
        investigation_id=investigation.investigation_id,
        incident_id=incident.incident_id,
        classification=DiagnosticActionClassification.OBSERVE,
        command="fixture-read-only-diagnostic",
        rationale="Read deterministic fixture state only.",
        expected_information="fixture diagnostic failure evidence",
    )
    manager.record_action(investigation.investigation_id, action)

    action.result = DiagnosticResult(
        diagnostic_action_id=action.diagnostic_action_id,
        command=action.command,
        started_at=started_at,
        finished_at=finished_at,
        stdout="fixture stdout",
        stderr="fixture diagnostic failed",
        exit_code=23,
        success=False,
        state="COMPLETED",
    )
    action.started_at = started_at
    action.finished_at = finished_at
    action.state = DiagnosticActionState.COMPLETED
    action.evidence_ids.append(evidence_id)
    manager.update_action(investigation.investigation_id, action)

    observation = Observation(
        observation_id="OBS-LANE2-0001",
        investigation_id=investigation.investigation_id,
        diagnostic_action_id=action.diagnostic_action_id,
        component_id=incident.component_id,
        observed_at=finished_at,
        source="FIXTURE",
        subject="diagnostic_exit_code",
        value=23,
        raw_evidence={
            "stderr": "fixture diagnostic failed",
            "exit_code": 23,
        },
    )
    manager.record_observation(investigation.investigation_id, observation)
    manager.add_evidence_reference(investigation.investigation_id, evidence_id)

    hypothesis = Hypothesis(
        hypothesis_id="HYP-LANE2-0001",
        investigation_id=investigation.investigation_id,
        statement="Fixture diagnostic endpoint is unavailable.",
        status=HypothesisStatus.SUPPORTED,
        supporting_evidence_ids=[evidence_id],
        created_at=investigation.created_at + timedelta(seconds=3),
        updated_at=investigation.created_at + timedelta(seconds=3),
    )
    manager.record_hypothesis(investigation.investigation_id, hypothesis)
    manager.mark_insufficient_evidence(investigation.investigation_id)
    return store


def test_evidence_complete_report_correlates_full_unattended_timeline(tmp_path):
    incident_manager = IncidentManager()
    incident = _incident(incident_manager)
    diagnostic_store = _diagnostic_store(tmp_path, incident)

    incident.add_evidence(
        _observation(),
        "Commander decision required before consequential action.",
        "COMMANDER_HANDOFF",
        {
            "commander_required": True,
            "decision": "WAIT_FOR_COMMANDER",
            "requested_action": "FIXTURE_ONLY",
        },
    )
    incident.add_evidence(
        {},
        "Simulated remediation denied; no execution performed.",
        "REMEDIATION_DENIED",
        {
            "decision": "DENY",
            "decision_reason": "fixture has no execution authority",
            "action": "FIXTURE_ONLY",
            "execution_id": "EXEC-FIXTURE-NOT-RUN",
        },
    )
    incident.add_evidence(
        {},
        "Read-only verification recorded no post-effect execution.",
        "VERIFICATION",
        {
            "verified": False,
            "reason": "remediation_not_executed",
        },
    )

    incident_manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={
            "verified": False,
            "reason": "fixture_terminalization_only",
        },
        observation=_observation(),
        final_outcome="UNRESOLVED",
    )

    before = deepcopy(incident.to_dict())
    builder = EvidenceCompleteIncidentReportBuilder(diagnostic_store)
    first = builder.build(incident)
    second = builder.build(incident)

    assert incident.to_dict() == before
    assert first.to_dict() == second.to_dict()

    data = first.to_dict()
    assert data["evidence_profile"] == "AIRIV_SENTINEL_EVIDENCE_COMPLETE_S1_V1"
    assert data["incident_id"] == incident.incident_id
    assert data["component_id"] == incident.component_id
    assert data["final_incident_status"] == "UNRESOLVED"
    assert data["commander_decision_requirement"]["required"] is True
    assert data["remediation_eligibility_status"]["known"] is True
    assert data["remediation_eligibility_status"]["eligibility"] == "DENIED"
    assert data["verification_result"] is not None
    assert data["verification_result"]["signal_type"] in {"VERIFICATION", "RECOVERY"}
    assert data["observed_states"]
    assert data["normalized_inputs"]
    assert data["diagnostics_and_understanding"]
    assert data["decisions"]
    assert data["evidence_completeness"]["complete"] is True
    assert data["evidence_completeness"]["missing"] == []

    failure = next(
        event
        for event in data["timeline"]
        if event["signal_type"] == "DIAGNOSTIC_FAILURE"
    )
    assert failure["correlation"]["incident_id"] == incident.incident_id
    assert failure["correlation"]["component_id"] == incident.component_id
    assert failure["correlation"]["investigation_id"] == "INV-LANE2-0001"
    assert failure["signal_snapshot"]["success"] is False
    assert failure["signal_snapshot"]["exit_code"] == 23
    assert failure["signal_snapshot"]["stderr"] == "fixture diagnostic failed"

    timestamps = [event["timestamp"] for event in data["timeline"]]
    assert timestamps == sorted(timestamps)
    assert [event["sequence"] for event in data["timeline"]] == list(
        range(1, len(data["timeline"]) + 1)
    )
    assert verify_timeline_integrity(data["timeline"]) is True
    assert data["timeline_sha256"] == data["timeline"][-1]["event_sha256"]

    tampered = deepcopy(data["timeline"])
    tampered[0]["reason"] = "tampered"
    assert verify_timeline_integrity(tampered) is False

    report_store = IncidentReportStore(tmp_path / "reports")
    report_store.save(first)
    recovered = report_store.get(incident.incident_id)
    assert recovered == data


def test_diagnostic_identity_mismatch_fails_closed(tmp_path):
    incident_manager = IncidentManager()
    incident = _incident(incident_manager)

    store = InvestigationStore(tmp_path / "diagnostic")
    manager = InvestigationManager(store)
    manager.start(
        incident_id=incident.incident_id,
        component_id="%999",
        trigger="FAILED",
        budget=DiagnosticBudget(
            max_duration_seconds=10,
            max_actions=1,
            max_repeated_action=1,
            max_risk=1,
            minimum_evidence=1,
        ),
        investigation_id="INV-MISMATCH",
    )

    with pytest.raises(ValueError, match="component_id mismatch"):
        EvidenceCompleteIncidentReportBuilder(store).build(incident)


def test_detection_only_report_is_explicitly_incomplete_without_diagnostics():
    incident_manager = IncidentManager()
    incident = _incident(incident_manager)

    report = EvidenceCompleteIncidentReportBuilder().build(incident).to_dict()

    assert report["evidence_completeness"]["complete"] is False
    assert "diagnostics_understanding" in report["evidence_completeness"]["missing"]
    assert report["commander_decision_requirement"]["required"] is False
    assert report["remediation_eligibility_status"]["known"] is False
    assert verify_timeline_integrity(report["timeline"]) is True
