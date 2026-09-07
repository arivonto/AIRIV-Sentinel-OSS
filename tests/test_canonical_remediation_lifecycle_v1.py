from sentinel.incidents.manager import IncidentManager, Incident
from sentinel.execution import ExecutionBoundary
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_orchestrator import RemediationOrchestrator
from sentinel.remediation_policy import RemediationPolicy
from sentinel.remediation_evidence_flow import EvidenceCompleteRemediationFlow


def build():
    manager = IncidentManager()
    incident = manager.intake(
        {
            "pane_id": "pane-1",
            "agent_identity": "chatgpt",
            "source": "canonical-remediation-test",
            "captured_at": "2026-09-03T00:00:00+00:00",
        },
        anomaly_signal={
            "anomaly_type": "STUCK",
            "reason": "Canonical remediation lifecycle test incident",
        },
    )

    assert incident is not None

    orchestrator = RemediationOrchestrator(
        policy=RemediationPolicy(allowed_actions={"restart_test"}),
        gate=RemediationExecutionGate(ExecutionBoundary()),
    )

    return manager, incident, orchestrator


def test_successful_remediation_updates_canonical_incident_without_auto_resolve():
    manager, incident, orchestrator = build()

    manager.investigate(incident.component_id)

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf remediation-ok",
    )

    assert result.execution is not None
    assert result.execution.success is True
    assert incident.status == "INVESTIGATING"

    assert manager.get_active_incident(incident.component_id) is incident


def test_failed_remediation_keeps_canonical_incident_active():
    manager, incident, orchestrator = build()

    manager.investigate(incident.component_id)

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "false",
    )

    assert result.execution is not None
    assert result.execution.success is False
    assert manager.get_active_incident(incident.component_id) is incident
    assert incident.status == "INVESTIGATING"


def test_denied_remediation_does_not_change_canonical_incident():
    manager, incident, orchestrator = build()

    manager.investigate(incident.component_id)

    result = orchestrator.handle_incident(
        incident,
        "forbidden_action",
        "printf should-not-run",
    )

    assert result.execution is None
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(incident.component_id) is incident


def test_remediation_evidence_can_be_attached_to_canonical_incident():
    manager, incident, orchestrator = build()

    manager.investigate(incident.component_id)

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf evidence-ok",
    )

    flow = EvidenceCompleteRemediationFlow()
    updated_incident, evidence = flow.finalize(
        incident,
        result,
    )

    assert updated_incident is incident
    assert evidence.incident_id == incident.incident_id
    assert evidence.component_id == incident.component_id
    assert evidence.execution_evidence is not None
    assert evidence.execution_evidence.exit_code == 0


def test_explicit_recovery_is_required_after_successful_remediation():
    manager, incident, orchestrator = build()

    manager.investigate(incident.component_id)

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf recovered",
    )

    assert result.execution is not None
    assert result.execution.success is True
    assert incident.status == "INVESTIGATING"

    manager.resolve(
        incident.component_id,
        recovery_evidence={"verified": True},
    )

    assert manager.get_active_incident(incident.component_id) is None
