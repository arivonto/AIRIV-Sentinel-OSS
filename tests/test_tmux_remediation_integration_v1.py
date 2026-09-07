from uuid import uuid4
from unittest.mock import patch

from sentinel.execution import ExecutionBoundary
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_orchestrator import RemediationOrchestrator
from sentinel.remediation_policy import RemediationPolicy
from sentinel.tmux_remediation_verifier import (
    TmuxRemediationVerifier,
    TmuxVerificationTarget,
)


def build_orchestrator():
    execution = ExecutionBoundary()
    policy = RemediationPolicy(
        allowed_actions={"restart_test"}
    )
    gate = RemediationExecutionGate(execution)

    verifier = TmuxRemediationVerifier(
        TmuxVerificationTarget(
            pane_id="%1",
            expected_alive=True,
        )
    )

    return RemediationOrchestrator(
        policy=policy,
        gate=gate,
        verifier=verifier,
    )


def test_successful_execution_requires_independent_tmux_verification():
    orchestrator = build_orchestrator()

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "0\n"
        run.return_value.stderr = ""

        result = orchestrator.handle(
            incident_state="INVESTIGATING",
            component_id="%1",
            action="restart_test",
            command="true",
            execution_id=f"tmux-test-success-{uuid4().hex}",
            incident_id=f"incident-tmux-test-success-{uuid4().hex}",
        )

    assert result.execution is not None
    assert result.execution.success is True
    assert result.verification is not None
    assert result.verification.verified is True


def test_execution_success_with_dead_tmux_pane_is_not_verified():
    orchestrator = build_orchestrator()

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "1\n"
        run.return_value.stderr = ""

        result = orchestrator.handle(
            incident_state="INVESTIGATING",
            component_id="%1",
            action="restart_test",
            command="true",
            execution_id=f"tmux-test-dead-pane-{uuid4().hex}",
            incident_id=f"incident-tmux-test-dead-pane-{uuid4().hex}",
        )

    assert result.execution is not None
    assert result.execution.success is True
    assert result.verification is not None
    assert result.verification.verified is False


def test_execution_failure_does_not_run_verification():
    orchestrator = build_orchestrator()

    with patch.object(
        orchestrator.verifier,
        "verify",
        wraps=orchestrator.verifier.verify,
    ) as verify:
        result = orchestrator.handle(
            incident_state="INVESTIGATING",
            component_id="%1",
            action="restart_test",
            command="false",
            execution_id=f"tmux-test-execution-failure-{uuid4().hex}",
            incident_id=f"incident-tmux-test-execution-failure-{uuid4().hex}",
        )

    assert result.execution is not None
    assert result.execution.success is False
    assert result.verification is None
    verify.assert_not_called()


def test_denied_remediation_does_not_run_verification():
    orchestrator = build_orchestrator()

    with patch(
        "sentinel.tmux_remediation_verifier.subprocess.run"
    ) as run:
        result = orchestrator.handle(
            incident_state="INVESTIGATING",
            component_id="%1",
            action="not_allowed",
            command="true",
            execution_id=f"tmux-test-denied-{uuid4().hex}",
            incident_id=f"incident-tmux-test-denied-{uuid4().hex}",
        )

    assert result.execution is None
    assert result.verification is None
    run.assert_not_called()
