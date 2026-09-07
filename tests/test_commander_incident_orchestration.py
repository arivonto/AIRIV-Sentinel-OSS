from sentinel.commander import CommanderOrchestrator
from sentinel.execution import ExecutionBoundary
from sentinel.incidents.manager import IncidentManager


def test_commander_can_access_canonical_incident_manager():
    manager = IncidentManager()

    commander = CommanderOrchestrator(
        incident_manager=manager,
        execution=ExecutionBoundary(),
    )

    assert commander.incident_manager is manager


def test_commander_does_not_duplicate_incident_lifecycle_authority():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
    )

    assert commander.incident_manager is not None
    assert not hasattr(commander, "create_incident")
    assert not hasattr(commander, "resolve_incident")
    assert not hasattr(commander, "update_incident_status")


def test_commander_uses_canonical_incident_intake():
    manager = IncidentManager()

    commander = CommanderOrchestrator(
        incident_manager=manager,
        execution=ExecutionBoundary(),
    )

    observation = {
        "pane_id": "commander-test-pane",
        "agent_identity": "commander-test-agent",
    }

    incident = manager.evaluate_anomaly(
        observation=observation,
        anomaly_type="COMMANDER_TEST_ANOMALY",
        reason="commander orchestration test",
    )

    assert incident is not None
    assert incident.incident_id
    assert incident.component_id == "commander-test-pane"
    assert incident.status == "OPEN"
    assert commander.incident_manager.get_active_incident(
        "commander-test-pane"
    ) is incident


def test_commander_denied_remediation_does_not_execute():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
    )

    incident = commander.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "commander-deny-pane",
            "agent_identity": "commander-test-agent",
        },
        anomaly_type="COMMANDER_TEST_ANOMALY",
        reason="remediation denial test",
    )

    result = commander.remediate(
        incident=incident,
        action="unauthorized_action",
        command="touch /tmp/airiv_commander_must_not_execute",
    )

    assert result.decision.authorized is False
    assert result.execution is None
    assert result.remediation is not None


def test_commander_allowed_remediation_executes():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
        remediation_policy=__import__(
            "sentinel.remediation_policy",
            fromlist=["RemediationPolicy"],
        ).RemediationPolicy(
            allowed_actions={"restart_test"}
        ),
    )

    incident = commander.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "commander-allow-pane",
            "agent_identity": "commander-test-agent",
        },
        anomaly_type="COMMANDER_TEST_ANOMALY",
        reason="remediation execution test",
    )

    result = commander.remediate(
        incident=incident,
        action="restart_test",
        command="printf 'commander-remediation'",
        verifier=lambda: True,
    )

    assert result.decision.authorized is True
    assert result.execution is not None
    assert result.execution.success is True
    assert result.execution.stdout == "commander-remediation"
    assert result.remediation is not None
