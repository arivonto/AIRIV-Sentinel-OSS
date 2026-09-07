from unittest.mock import patch

from sentinel.incidents.manager import IncidentManager
from sentinel.runtime import SentinelRuntime


def build_runtime_and_incident():

    runtime = SentinelRuntime()
    # PHASE_213C1_EXPLICIT_TEST_ALLOWANCE
    # E2E test-local authorization only; production defaults remain empty.
    runtime.policy.allowed_actions = {"restart_test"}

    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        {
            "pane_id": "%runtime-e2e",
            "agent_identity": "sentinel",
            "source": "runtime-e2e-test",
            "captured_at": "2026-09-03T00:00:00+00:00",
        },
        "STUCK",
        "Runtime E2E remediation test",
    )

    manager.investigate(incident.component_id)

    return runtime, manager, incident


def test_runtime_successful_remediation_records_verified_evidence():
    runtime, manager, incident = build_runtime_and_incident()

    with patch(
        "sentinel.runtime.TmuxRemediationVerifier"
    ) as verifier_cls:
        verifier = verifier_cls.return_value
        verifier.verify.return_value = type(
            "Verification",
            (),
            {
                "verified": True,
                "reason": "post_remediation_tmux_state_verified",
                "observation": {
                    "source": "tmux",
                    "pane_id": incident.component_id,
                    "capture_ok": True,
                    "pane_dead": False,
                },
            },
        )()

        with patch.object(
            runtime.orchestrator,
            "handle_incident",
            wraps=runtime.orchestrator.handle_incident,
        ):
            updated, evidence = runtime.remediate(
                incident=incident,
                action="restart_test",
                command="true",
            )

    assert updated is incident
    assert evidence.incident_id == incident.incident_id
    assert evidence.component_id == incident.component_id
    assert evidence.verification is not None
    assert evidence.verification.verified is True

    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_VERIFIED"
    assert latest["signal_snapshot"]["verification"]["verified"] is True

    # Successful remediation MUST NOT resolve the incident.
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    verifier_cls.assert_called_once()


def test_runtime_failed_execution_records_failure_without_verification():
    runtime, manager, incident = build_runtime_and_incident()

    with patch.object(
        runtime.orchestrator,
        "handle_incident",
        wraps=runtime.orchestrator.handle_incident,
    ):
        updated, evidence = runtime.remediate(
            incident=incident,
            action="restart_test",
            command="false",
        )

    assert updated is incident
    assert evidence.execution_evidence is not None
    assert evidence.execution_evidence.success is False
    assert evidence.verification is None

    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_FAILED"
    assert latest["signal_snapshot"]["execution"] is not None

    # Failed remediation MUST NOT resolve the incident.
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident


def test_runtime_failed_verification_records_failure_without_resolving():
    runtime, manager, incident = build_runtime_and_incident()

    with patch(
        "sentinel.runtime.TmuxRemediationVerifier"
    ) as verifier_cls:
        verifier = verifier_cls.return_value
        verifier.verify.return_value = type(
            "Verification",
            (),
            {
                "verified": False,
                "reason": "post_remediation_tmux_state_not_verified",
                "observation": {
                    "source": "tmux",
                    "pane_id": incident.component_id,
                    "capture_ok": True,
                    "pane_dead": True,
                },
            },
        )()

        updated, evidence = runtime.remediate(
            incident=incident,
            action="restart_test",
            command="true",
        )

    assert updated is incident
    assert evidence.execution_evidence is not None
    assert evidence.execution_evidence.success is True
    assert evidence.verification is not None
    assert evidence.verification.verified is False

    latest = incident.evidence_trail[-1]

    assert latest["signal_type"] == "REMEDIATION_VERIFICATION_FAILED"
    assert latest["signal_snapshot"]["verification"]["verified"] is False

    # Verification failure MUST NOT resolve the incident.
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    verifier_cls.assert_called_once()
