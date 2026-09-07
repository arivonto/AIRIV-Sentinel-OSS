from sentinel.execution import ExecutionBoundary
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_orchestrator import RemediationOrchestrator
from sentinel.remediation_policy import RemediationPolicy


def observation():
    return {
        "pane_id": "%canonical-remediation",
        "window_name": "chatgpt",
        "current_command": "bash",
        "activity_state": "STUCK",
        "output_sha256": "remediation-test",
        "agent_identity": "chatgpt",
    }


def create_incident():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation(),
        "STUCK",
        "Canonical remediation boundary test",
    )

    manager.investigate(incident.component_id)

    return manager, incident


def create_orchestrator():
    executor = ExecutionBoundary()
    gate = RemediationExecutionGate(executor)

    policy = RemediationPolicy(
        allowed_actions={"restart_test"}
    )

    return RemediationOrchestrator(
        policy=policy,
        gate=gate,
    )


def test_remediation_accepts_canonical_incident():
    manager, incident = create_incident()
    orchestrator = create_orchestrator()

    result = orchestrator.handle_incident(
        incident=incident,
        action="restart_test",
        command="printf canonical-remediation",
    )

    assert result.decision.action == "restart_test"
    assert result.execution is not None
    assert result.execution.success is True

    assert manager.get_active_incident(
        incident.component_id
    ) is incident


def test_remediation_preserves_canonical_incident_identity():
    manager, incident = create_incident()
    orchestrator = create_orchestrator()

    result = orchestrator.handle_incident(
        incident=incident,
        action="restart_test",
        command="printf identity-preserved",
    )

    assert result.execution is not None
    assert result.execution.success is True

    active = manager.get_active_incident(
        incident.component_id
    )

    assert active is incident
    assert active.incident_id == incident.incident_id


def test_denied_remediation_does_not_execute_against_canonical_incident():
    manager, incident = create_incident()
    orchestrator = create_orchestrator()

    result = orchestrator.handle_incident(
        incident=incident,
        action="unapproved_action",
        command="printf SHOULD_NOT_EXECUTE",
    )

    assert result.execution is None
    assert result.decision.decision.value == "DENY"

    active = manager.get_active_incident(
        incident.component_id
    )

    assert active is incident
    assert active.status == "INVESTIGATING"


def test_successful_remediation_does_not_auto_resolve_incident():
    manager, incident = create_incident()
    orchestrator = create_orchestrator()

    result = orchestrator.handle_incident(
        incident=incident,
        action="restart_test",
        command="printf recovery-candidate",
    )

    assert result.execution is not None
    assert result.execution.success is True

    active = manager.get_active_incident(
        incident.component_id
    )

    assert active is incident
    assert active.status == "INVESTIGATING"


def test_failed_remediation_keeps_incident_active():
    manager, incident = create_incident()
    orchestrator = create_orchestrator()

    result = orchestrator.handle_incident(
        incident=incident,
        action="restart_test",
        command="false",
    )

    assert result.execution is not None
    assert result.execution.success is False

    active = manager.get_active_incident(
        incident.component_id
    )

    assert active is incident
    assert active.status == "INVESTIGATING"
