from sentinel.execution import ExecutionBoundary
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_evidence_flow import EvidenceCompleteRemediationFlow
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_orchestrator import RemediationOrchestrator
from sentinel.remediation_policy import RemediationPolicy
from sentinel.remediation_verifier import RemediationVerifier


def build():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation={
            "pane_id": "%verification",
            "window_name": "test",
            "agent_identity": "TEST",
            "capture_ok": True,
            "pane_dead": True,
        },
        anomaly_type="PANE_DEAD",
        reason="Remediation verification integration test.",
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


def attach_verification(result, verification):
    return result.__class__(
        decision=result.decision,
        execution=result.execution,
        verification=verification,
        execution_id=result.execution_id,
        replayed=result.replayed,
        identity_record=result.identity_record,
    )


def test_verified_remediation_is_recorded_as_verified():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf remediation-ok",
    )

    verification = RemediationVerifier(lambda: True).verify()

    result = attach_verification(result, verification)

    updated, evidence = EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert updated is incident
    assert evidence.verification is not None
    assert evidence.verification.verified is True
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(incident.component_id) is incident

    assert incident.evidence_trail
    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_VERIFIED"


def test_failed_verification_is_recorded_and_does_not_resolve():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf remediation-executed",
    )

    verification = RemediationVerifier(lambda: False).verify()

    result = attach_verification(result, verification)

    updated, evidence = EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert updated is incident
    assert evidence.verification is not None
    assert evidence.verification.verified is False
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(incident.component_id) is incident

    assert incident.evidence_trail
    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_VERIFICATION_FAILED"


def test_execution_without_verification_is_not_claimed_success():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "printf remediation-unverified",
    )

    updated, evidence = EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert updated is incident
    assert evidence.verification is None
    assert incident.status == "INVESTIGATING"

    assert incident.evidence_trail
    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_EXECUTED_UNVERIFIED"


def test_failed_execution_remains_failed_even_if_verifier_would_pass():
    manager, incident, orchestrator = build()

    result = orchestrator.handle_incident(
        incident,
        "restart_test",
        "false",
    )

    verification = RemediationVerifier(lambda: True).verify()

    result = attach_verification(result, verification)

    EvidenceCompleteRemediationFlow().finalize(
        incident,
        result,
    )

    assert incident.evidence_trail
    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_FAILED"
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(incident.component_id) is incident
