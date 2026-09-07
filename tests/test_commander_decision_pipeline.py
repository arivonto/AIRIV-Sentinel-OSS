from sentinel.commander import CommanderOrchestrator
from sentinel.execution import ExecutionBoundary
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_policy import RemediationPolicy


def make_commander(allowed_actions=None):
    return CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
        remediation_policy=RemediationPolicy(
            allowed_actions=set(allowed_actions or [])
        ),
    )


def make_incident(commander, pane_id="decision-pane"):
    return commander.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": pane_id,
            "agent_identity": "commander-test-agent",
        },
        anomaly_type="COMMANDER_DECISION_TEST",
        reason="commander decision pipeline test",
    )


def test_denied_action_is_deterministically_denied():
    commander = make_commander()
    incident = make_incident(commander)

    first = commander.decide_remediation(
        incident,
        "unauthorized_action",
    )
    second = commander.decide_remediation(
        incident,
        "unauthorized_action",
    )

    assert first.authorized is False
    assert second.authorized is False
    assert first.reason == second.reason


def test_allowed_action_is_deterministically_authorized():
    commander = make_commander({"restart_test"})
    incident = make_incident(commander)

    decision = commander.decide_remediation(
        incident,
        "restart_test",
    )

    assert decision.authorized is True
    assert decision.action == "restart_test"


def test_commander_does_not_override_policy():
    commander = make_commander()
    incident = make_incident(commander)

    decision = commander.decide_remediation(
        incident,
        "restart_test",
    )

    assert decision.authorized is False


def test_remediation_evidence_contains_authorization_result():
    commander = make_commander()
    incident = make_incident(commander)

    result = commander.remediate(
        incident=incident,
        action="unauthorized_action",
        command="printf 'must-not-run'",
    )

    assert result.remediation is not None
    assert result.remediation.decision == "DENY"

def test_authorized_remediation_requires_verification_for_success():
    commander = make_commander({"restart_test"})
    incident = make_incident(
        commander,
        pane_id="verification-pane",
    )

    result = commander.remediate(
        incident=incident,
        action="restart_test",
        command="printf 'executed'",
    )

    assert result.decision.authorized is True
    assert result.execution is not None
    assert result.execution.success is True
    assert result.remediation is not None
    assert result.remediation.execution_evidence is not None
    assert result.remediation.verification is None

def test_verified_remediation_is_distinguished_from_execution():
    commander = make_commander({"restart_test"})
    incident = make_incident(
        commander,
        pane_id="verified-pane",
    )

    result = commander.remediate(
        incident=incident,
        action="restart_test",
        command="printf 'executed'",
        verifier=lambda: True,
    )

    assert result.decision.authorized is True
    assert result.execution is not None
    assert result.execution.success is True
    assert result.remediation is not None
    assert result.remediation.verification is not None
    assert result.remediation.verification.verified is True
