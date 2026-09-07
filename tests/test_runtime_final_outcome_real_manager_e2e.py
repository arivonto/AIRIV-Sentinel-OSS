from sentinel.commander_intent import CommanderIntent
from sentinel.diagnostic.runtime_coordinator import (
    RuntimeDiagnosticCoordinator,
)
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_policy import PolicyDecision


def make_runtime_boundary():
    manager = IncidentManager()

    coordinator = RuntimeDiagnosticCoordinator(
        incident_lookup=manager.get_active_incident,
        incident_manager=manager,
    )

    assert coordinator.incident_manager is manager

    return manager, coordinator


def create_incident(
    manager: IncidentManager,
    *,
    component_id: str,
):
    incident = manager.evaluate_anomaly(
        observation={
            "component_id": component_id,
            "pane_id": f"%{component_id}",
            "source": "runtime_final_outcome_real_manager_e2e",
        },
        anomaly_type="FINAL_OUTCOME_E2E",
        reason="Real RuntimeDiagnosticCoordinator lifecycle E2E.",
    )

    assert incident.component_id
    assert manager.get_active_incident(incident.component_id) is incident

    return incident


def assert_terminalized(
    *,
    manager,
    coordinator,
    incident,
    investigation_id,
    expected_outcome,
):
    assert incident.status == "TERMINAL"
    assert incident.lifecycle_state == "TERMINAL"
    assert incident.final_outcome == expected_outcome

    assert manager.get_active_incident(
        incident.component_id
    ) is None

    assert (
        coordinator._final_outcome_by_investigation[
            investigation_id
        ]
        == expected_outcome
    )

    history = manager.get_history()

    assert history
    assert history[-1]["incident_id"] == incident.incident_id
    assert history[-1]["component_id"] == incident.component_id
    assert history[-1]["final_outcome"] == expected_outcome


def test_no_action_remains_active_with_real_incident_manager():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-no-action",
    )

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-e2e-no-action",
        incident=incident,
        intent=CommanderIntent.NO_ACTION,
    )

    assert outcome is None

    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    assert incident.status != "TERMINAL"
    assert incident.final_outcome is None

    assert (
        "inv-e2e-no-action"
        not in coordinator._final_outcome_by_investigation
    )


def test_insufficient_evidence_terminalizes_real_incident():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-insufficient-evidence",
    )

    investigation_id = "inv-e2e-insufficient-evidence"

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id=investigation_id,
        incident=incident,
        intent=CommanderIntent.INSUFFICIENT_EVIDENCE,
    )

    assert outcome == "INSUFFICIENT_EVIDENCE"

    assert_terminalized(
        manager=manager,
        coordinator=coordinator,
        incident=incident,
        investigation_id=investigation_id,
        expected_outcome="INSUFFICIENT_EVIDENCE",
    )


def test_need_commander_terminalizes_real_incident_escalated():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-need-commander",
    )

    investigation_id = "inv-e2e-need-commander"

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id=investigation_id,
        incident=incident,
        intent=CommanderIntent.NEED_COMMANDER,
    )

    assert outcome == "ESCALATED"

    assert_terminalized(
        manager=manager,
        coordinator=coordinator,
        incident=incident,
        investigation_id=investigation_id,
        expected_outcome="ESCALATED",
    )


def test_autonomous_policy_deny_terminalizes_real_incident_escalated():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-policy-deny",
    )

    investigation_id = "inv-e2e-policy-deny"

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id=investigation_id,
        incident=incident,
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.DENY,
    )

    assert outcome == "ESCALATED"

    assert_terminalized(
        manager=manager,
        coordinator=coordinator,
        incident=incident,
        investigation_id=investigation_id,
        expected_outcome="ESCALATED",
    )


def test_execution_failure_terminalizes_real_incident_unresolved():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-execution-failure",
    )

    investigation_id = "inv-e2e-execution-failure"

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id=investigation_id,
        incident=incident,
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=False,
        verification_succeeded=None,
    )

    assert outcome == "UNRESOLVED"

    assert_terminalized(
        manager=manager,
        coordinator=coordinator,
        incident=incident,
        investigation_id=investigation_id,
        expected_outcome="UNRESOLVED",
    )


def test_verification_failure_terminalizes_real_incident_unresolved():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-verification-failure",
    )

    investigation_id = "inv-e2e-verification-failure"

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id=investigation_id,
        incident=incident,
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
        verification_succeeded=False,
    )

    assert outcome == "UNRESOLVED"

    assert_terminalized(
        manager=manager,
        coordinator=coordinator,
        incident=incident,
        investigation_id=investigation_id,
        expected_outcome="UNRESOLVED",
    )


def test_verified_success_terminalizes_real_incident_recovered():
    manager, coordinator = make_runtime_boundary()

    incident = create_incident(
        manager,
        component_id="e2e-verified-recovery",
    )

    investigation_id = "inv-e2e-verified-recovery"

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id=investigation_id,
        incident=incident,
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
        verification_succeeded=True,
    )

    assert outcome == "RECOVERED"

    assert_terminalized(
        manager=manager,
        coordinator=coordinator,
        incident=incident,
        investigation_id=investigation_id,
        expected_outcome="RECOVERED",
    )
