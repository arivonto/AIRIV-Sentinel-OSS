from unittest.mock import patch

from sentinel.runtime import SentinelRuntime
from sentinel.incidents.manager import IncidentManager


def build_incident(manager: IncidentManager):
    incident = manager.evaluate_anomaly(
        observation={
            "pane_id": "%commander-lifecycle",
            "capture_ok": True,
            "pane_dead": False,
        },
        anomaly_type="COMMANDER_LIFECYCLE_TEST",
        reason="Canonical Autonomous Commander lifecycle E2E test.",
    )

    assert incident is not None
    assert incident.status == "OPEN"

    manager.investigate(incident.component_id)

    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    return incident


def test_autonomous_commander_full_remediation_recovery_lifecycle():

    runtime = SentinelRuntime()
    # PHASE_213C1_EXPLICIT_TEST_ALLOWANCE
    # E2E test-local authorization only; production defaults remain empty.
    runtime.policy.allowed_actions = {"restart_test"}

    manager = runtime.incident_manager
    incident = build_incident(manager)

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
                    "raw_value": "0",
                },
            },
        )()

        updated, evidence = runtime.remediate(
            incident=incident,
            action="restart_test",
            command="true",
        )

        assert updated is incident

        # Remediation must not resolve the incident.
        assert incident.status == "INVESTIGATING"
        assert manager.get_active_incident(
            incident.component_id
        ) is incident

        # Evidence must prove verified remediation.
        assert evidence.incident_id == incident.incident_id
        assert evidence.component_id == incident.component_id
        assert evidence.execution_evidence is not None
        assert evidence.execution_evidence.success is True
        assert evidence.verification is not None
        assert evidence.verification.verified is True

        latest = incident.evidence_trail[-1]

        assert latest["signal_type"] == "REMEDIATION_VERIFIED"
        assert (
            latest["signal_snapshot"]["verification"]["verified"]
            is True
        )

        verifier_cls.assert_called_once()

    # Verification is not lifecycle authority.
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident

    # Explicit recovery evidence is required for resolution.
    resolved = manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={
            "verified": True,
            "verification": "post_remediation_state_verified",
            "source": "canonical_autonomous_commander_e2e",
        },
        observation={
            "pane_id": incident.component_id,
            "capture_ok": True,
            "pane_dead": False,
        },
        operator_note="Explicit recovery confirmation after verified remediation.",
    )

    assert resolved is incident
    assert incident.status == "TERMINAL"
    assert incident.lifecycle_state == "TERMINAL"
    assert incident.final_outcome == "RECOVERED"

    # Resolved incidents must no longer be active.
    assert manager.get_active_incident(
        incident.component_id
    ) is None

    # Evidence must remain append-only and auditable.
    assert len(incident.evidence_trail) >= 2

    recovery_records = [
        record
        for record in incident.evidence_trail
        if record["signal_type"] == "RECOVERY"
    ]

    assert recovery_records

    recovery = recovery_records[-1]

    assert recovery["reason"] == "Explicit recovery evidence accepted"
    assert recovery["signal_snapshot"]["verified"] is True
    assert (
        recovery["signal_snapshot"]["verification"]
        == "post_remediation_state_verified"
    )
    assert (
        recovery["signal_snapshot"]["source"]
        == "canonical_autonomous_commander_e2e"
    )

    assert any(
        record["signal_type"] == "OPERATOR_NOTE"
        for record in incident.evidence_trail
    )


def test_failed_verification_never_reaches_resolved_state():

    runtime = SentinelRuntime()
    # PHASE_213C1_EXPLICIT_TEST_ALLOWANCE
    # E2E test-local authorization only; production defaults remain empty.
    runtime.policy.allowed_actions = {"restart_test"}

    manager = runtime.incident_manager
    incident = build_incident(manager)

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
                    "raw_value": "1",
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
    assert (
        latest["signal_snapshot"]["verification"]["verified"]
        is False
    )

    # Failed verification MUST keep the incident active.
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident(
        incident.component_id
    ) is incident
