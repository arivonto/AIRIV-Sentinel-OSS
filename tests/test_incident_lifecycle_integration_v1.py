from sentinel.incidents.manager import IncidentManager
from sentinel.execution import ExecutionBoundary
from sentinel.remediation_evidence_flow import EvidenceCompleteRemediationFlow
from sentinel.remediation_orchestrator import RemediationOrchestrator
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_policy import RemediationPolicy


def build():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation={
            "pane_id": "%integration",
            "window_name": "test",
            "agent_identity": "TEST",
            "capture_ok": True,
            "pane_dead": True,
        },
        anomaly_type="PANE_DEAD",
        reason="Canonical remediation integration test incident.",
    )

    assert incident is not None

    manager.investigate(incident.component_id)

    orchestrator = RemediationOrchestrator(
        policy=RemediationPolicy(
            allowed_actions={"restart_test"}
        ),
        gate=RemediationExecutionGate(
            ExecutionBoundary()
        ),
    )

    return manager, incident, orchestrator


def test_successful_remediation_produces_evidence_without_auto_resolve():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf 'sentinel-remediation-ok'",
    )

    updated, evidence = EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert updated is incident
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    assert evidence.incident_id == incident.incident_id
    assert evidence.component_id == incident.component_id
    assert evidence.decision == "ALLOW"
    assert evidence.execution_evidence is not None
    assert evidence.execution_evidence.success is True


def test_denied_remediation_cannot_resolve_incident():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "unauthorized_action",
        "printf 'must-not-run'",
    )

    updated, evidence = EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert updated is incident
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    assert evidence.decision == "DENY"
    assert evidence.execution_evidence is None


def test_failed_execution_keeps_incident_active():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "false",
    )

    updated, evidence = EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert updated is incident
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    assert evidence.execution_evidence is not None
    assert evidence.execution_evidence.success is False


def test_incident_manager_requires_explicit_recovery_evidence():
    manager = IncidentManager()

    observation = {
        "pane_id": "%recovery",
        "window_name": "test",
        "agent_identity": "TEST",
        "capture_ok": True,
        "pane_dead": True,
    }

    incident = manager.evaluate_anomaly(
        observation=observation,
        anomaly_type="PANE_DEAD",
        reason="Pane is dead.",
    )

    manager.investigate("%recovery")

    try:
        manager.resolve(
            component_id="%recovery",
            recovery_evidence={},
            observation=observation,
        )
        raise AssertionError(
            "Resolution without explicit recovery evidence must fail"
        )
    except ValueError:
        pass

    assert manager.get_active_incident("%recovery") is incident
    assert incident.status == "INVESTIGATING"


def test_incident_manager_recovery_is_explicit_and_auditable():
    manager = IncidentManager()

    observation = {
        "pane_id": "%recovery-ok",
        "window_name": "test",
        "agent_identity": "TEST",
        "capture_ok": True,
        "pane_dead": True,
    }

    incident = manager.evaluate_anomaly(
        observation=observation,
        anomaly_type="PANE_DEAD",
        reason="Pane is dead.",
    )

    manager.investigate("%recovery-ok")

    resolved = manager.resolve(
        component_id="%recovery-ok",
        recovery_evidence={
            "verified": True,
            "verification": "pane_alive",
        },
        observation={
            "pane_id": "%recovery-ok",
            "window_name": "test",
            "agent_identity": "TEST",
            "capture_ok": True,
            "pane_dead": False,
        },
    )

    assert resolved is incident
    assert incident.status == "TERMINAL"
    assert incident.lifecycle_state == "TERMINAL"
    assert incident.final_outcome == "RECOVERED"
    assert manager.get_active_incident("%recovery-ok") is None
    assert incident.evidence_trail
