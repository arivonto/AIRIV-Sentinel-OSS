from types import SimpleNamespace

from sentinel.commander_intent import CommanderIntent
from sentinel.diagnostic.runtime_coordinator import (
    RuntimeDiagnosticCoordinator,
)
from sentinel.remediation_policy import PolicyDecision


class RecordingIncidentManager:
    def __init__(self):
        self.calls = []

    def resolve(
        self,
        *,
        component_id,
        recovery_evidence,
        observation=None,
        operator_note=None,
        final_outcome="RECOVERED",
    ):
        self.calls.append(
            {
                "component_id": component_id,
                "recovery_evidence": recovery_evidence,
                "observation": observation,
                "operator_note": operator_note,
                "final_outcome": final_outcome,
            }
        )
        return SimpleNamespace(
            component_id=component_id,
            final_outcome=final_outcome,
        )


def make_coordinator():
    coordinator = object.__new__(
        RuntimeDiagnosticCoordinator
    )
    coordinator.incident_manager = RecordingIncidentManager()
    coordinator._final_outcome_by_investigation = {}
    coordinator._handoff_by_investigation = {}

    import threading

    coordinator._lock = threading.RLock()
    return coordinator


def make_incident():
    return SimpleNamespace(
        incident_id="incident-final-outcome-test",
        component_id="component-final-outcome-test",
    )


def test_no_action_does_not_terminalize_incident():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-no-action",
        incident=make_incident(),
        intent=CommanderIntent.NO_ACTION,
    )

    assert outcome is None
    assert coordinator.incident_manager.calls == []


def test_insufficient_evidence_terminalizes_via_incident_manager():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-insufficient",
        incident=make_incident(),
        intent=CommanderIntent.INSUFFICIENT_EVIDENCE,
    )

    assert outcome == "INSUFFICIENT_EVIDENCE"
    assert len(coordinator.incident_manager.calls) == 1
    assert (
        coordinator.incident_manager.calls[0]["final_outcome"]
        == "INSUFFICIENT_EVIDENCE"
    )


def test_need_commander_terminalizes_escalated():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-escalated",
        incident=make_incident(),
        intent=CommanderIntent.NEED_COMMANDER,
    )

    assert outcome == "ESCALATED"
    assert (
        coordinator.incident_manager.calls[0]["final_outcome"]
        == "ESCALATED"
    )


def test_policy_deny_terminalizes_escalated():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-deny",
        incident=make_incident(),
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.DENY,
    )

    assert outcome == "ESCALATED"
    assert (
        coordinator.incident_manager.calls[0]["final_outcome"]
        == "ESCALATED"
    )


def test_execution_failure_terminalizes_unresolved():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-execution-failure",
        incident=make_incident(),
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=False,
    )

    assert outcome == "UNRESOLVED"
    assert (
        coordinator.incident_manager.calls[0]["final_outcome"]
        == "UNRESOLVED"
    )


def test_failed_verification_terminalizes_unresolved():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-verification-failure",
        incident=make_incident(),
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
        verification_succeeded=False,
    )

    assert outcome == "UNRESOLVED"
    assert (
        coordinator.incident_manager.calls[0]["final_outcome"]
        == "UNRESOLVED"
    )


def test_verified_remediation_terminalizes_recovered():
    coordinator = make_coordinator()

    outcome = coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-recovered",
        incident=make_incident(),
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
        verification_succeeded=True,
    )

    assert outcome == "RECOVERED"

    call = coordinator.incident_manager.calls[0]

    assert call["final_outcome"] == "RECOVERED"
    assert (
        call["recovery_evidence"]["execution_succeeded"]
        is True
    )
    assert (
        call["recovery_evidence"]["verification_succeeded"]
        is True
    )


def test_terminal_outcome_is_cached_by_investigation():
    coordinator = make_coordinator()

    coordinator._map_and_terminalize_final_outcome(
        investigation_id="inv-cache",
        incident=make_incident(),
        intent=CommanderIntent.NEED_COMMANDER,
    )

    assert (
        coordinator._final_outcome_by_investigation[
            "inv-cache"
        ]
        == "ESCALATED"
    )
