import pytest

from sentinel.execution import ExecutionResult
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_orchestrator import OrchestrationResult
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationDecision,
)
from sentinel.remediation_verifier import VerificationResult
from sentinel.workflow.lifecycle import (
    DuplicateEventConflict,
    DuplicateExecutionConflict,
    IncidentWorkflowLifecycle,
    IncidentWorkflowState,
    LifecycleFailureReason,
    LifecycleInvariantError,
)


def _decision(component_id="pane-1", allowed=True):
    return RemediationDecision(
        decision=(
            PolicyDecision.ALLOW if allowed else PolicyDecision.DENY
        ),
        reason="test",
        incident_state="INVESTIGATING",
        component_id=component_id,
        action="restart_test",
    )


def _lifecycle():
    return IncidentWorkflowLifecycle(
        workflow_id="wf-1",
        incident_id="INC-1",
        component_id="pane-1",
    )


def _ready():
    lifecycle = _lifecycle()
    lifecycle.record_diagnostics(
        event_id="diag-1",
        diagnostics_ref="diagnostic-record-1",
    )
    lifecycle.record_authorization(
        event_id="auth-1",
        decision=_decision(),
    )
    lifecycle.record_remediation_eligibility(
        event_id="elig-1",
        eligible=True,
    )
    lifecycle.mark_remediating(
        event_id="start-1",
        execution_id="exec-1",
    )
    return lifecycle


def _execution(success=True):
    return ExecutionResult(
        command="synthetic-test-only",
        stdout="",
        stderr="",
        exit_code=0 if success else 7,
        started_at=1.0,
        finished_at=2.0,
    )


def test_happy_path_requires_verification_before_recovered():
    lifecycle = _ready()

    result = OrchestrationResult(
        decision=_decision(),
        execution=_execution(success=True),
        execution_id="exec-1",
        replayed=False,
    )
    lifecycle.record_canonical_remediation_result(
        event_id="result-1",
        result=result,
    )

    assert lifecycle.state is IncidentWorkflowState.REMEDIATING

    lifecycle.record_verification(
        event_id="verify-1",
        verification=VerificationResult(
            verified=True,
            reason="postcondition satisfied",
        ),
    )

    snapshot = lifecycle.snapshot()
    assert snapshot.state is IncidentWorkflowState.RECOVERED
    assert snapshot.remediation_succeeded is True
    assert snapshot.verification_passed is True
    assert snapshot.failure_reason is None


def test_lane4_projection_does_not_mutate_canonical_incident_lifecycle():
    manager = IncidentManager()
    incident = manager.evaluate_anomaly(
        observation={
            "pane_id": "pane-1",
            "agent_identity": "test",
        },
        anomaly_type="STUCK",
    )
    manager.investigate("pane-1")

    lifecycle = IncidentWorkflowLifecycle(
        workflow_id="wf-incident",
        incident_id=incident.incident_id,
        component_id=incident.component_id,
    )
    lifecycle.record_diagnostics(
        event_id="diag",
        diagnostics_ref="opaque-diagnostics-ref",
    )
    lifecycle.record_authorization(
        event_id="auth",
        decision=_decision(),
    )

    assert lifecycle.state is IncidentWorkflowState.OPEN
    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident("pane-1") is incident


def test_exact_event_replay_is_idempotent_even_after_terminal():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result",
        execution_id="exec-1",
        success=False,
    )
    before = lifecycle.snapshot()

    first = lifecycle.history[-1]
    replay = lifecycle.record_remediation_result(
        event_id="result",
        execution_id="exec-1",
        success=False,
    )

    assert replay == first
    assert lifecycle.snapshot() == before
    assert lifecycle.state is IncidentWorkflowState.FAILED


def test_reused_event_id_with_changed_content_is_rejected():
    lifecycle = _lifecycle()
    lifecycle.record_diagnostics(
        event_id="same-event",
        diagnostics_ref="diag-a",
    )

    with pytest.raises(DuplicateEventConflict):
        lifecycle.record_diagnostics(
            event_id="same-event",
            diagnostics_ref="diag-b",
        )

    assert len(lifecycle.history) == 1


def test_same_execution_id_cannot_report_contradictory_results():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result-ok",
        execution_id="exec-1",
        success=True,
    )

    with pytest.raises(DuplicateExecutionConflict):
        lifecycle.record_remediation_result(
            event_id="result-conflict",
            execution_id="exec-1",
            success=False,
            replayed=True,
        )

    assert lifecycle.state is IncidentWorkflowState.REMEDIATING
    assert lifecycle.remediation_succeeded is True


def test_failed_remediation_is_terminal_and_failure_is_preserved():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result-fail",
        execution_id="exec-1",
        success=False,
    )

    assert lifecycle.state is IncidentWorkflowState.FAILED
    assert (
        lifecycle.failure_reason
        is LifecycleFailureReason.REMEDIATION_FAILED
    )

    with pytest.raises(LifecycleInvariantError):
        lifecycle.record_verification(
            event_id="late-success",
            verification=True,
        )

    assert lifecycle.state is IncidentWorkflowState.FAILED
    assert (
        lifecycle.failure_reason
        is LifecycleFailureReason.REMEDIATION_FAILED
    )


def test_verification_failure_cannot_be_overwritten_by_recovery():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result-ok",
        execution_id="exec-1",
        success=True,
    )
    lifecycle.record_verification(
        event_id="verify-fail",
        verification=VerificationResult(
            verified=False,
            reason="postcondition failed",
        ),
    )

    assert lifecycle.state is IncidentWorkflowState.FAILED
    assert (
        lifecycle.failure_reason
        is LifecycleFailureReason.VERIFICATION_FAILED
    )

    with pytest.raises(LifecycleInvariantError):
        lifecycle.record_verification(
            event_id="verify-late-success",
            verification=True,
        )


def test_denied_authorization_fails_closed_before_remediation():
    lifecycle = _lifecycle()
    lifecycle.record_diagnostics(
        event_id="diag",
        diagnostics_ref="diag-ref",
    )
    lifecycle.record_authorization(
        event_id="deny",
        decision=_decision(allowed=False),
    )

    assert lifecycle.state is IncidentWorkflowState.FAILED
    assert (
        lifecycle.failure_reason
        is LifecycleFailureReason.AUTHORIZATION_DENIED
    )

    with pytest.raises(LifecycleInvariantError):
        lifecycle.record_remediation_eligibility(
            event_id="late-eligibility",
            eligible=True,
        )


def test_ineligible_remediation_fails_closed():
    lifecycle = _lifecycle()
    lifecycle.record_diagnostics(
        event_id="diag",
        diagnostics_ref="diag-ref",
    )
    lifecycle.record_authorization(
        event_id="allow",
        decision=_decision(),
    )
    lifecycle.record_remediation_eligibility(
        event_id="not-eligible",
        eligible=False,
        reason_ref="eligibility-check-7",
    )

    assert lifecycle.state is IncidentWorkflowState.FAILED
    assert (
        lifecycle.failure_reason
        is LifecycleFailureReason.REMEDIATION_INELIGIBLE
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("timeout", LifecycleFailureReason.TIMEOUT),
        ("cancel", LifecycleFailureReason.CANCELLED),
        ("retry", LifecycleFailureReason.RETRY_EXHAUSTED),
    ],
)
def test_timeout_cancellation_and_retry_exhaustion_are_failed(
    operation,
    expected,
):
    lifecycle = _ready()

    if operation == "timeout":
        lifecycle.mark_timeout(
            event_id="terminal-event",
            stage="verification",
        )
    elif operation == "cancel":
        lifecycle.cancel(
            event_id="terminal-event",
            reason="authorized cancellation",
        )
    else:
        lifecycle.mark_retry_exhausted(
            event_id="terminal-event",
            attempts=3,
        )

    assert lifecycle.state is IncidentWorkflowState.FAILED
    assert lifecycle.failure_reason is expected


def test_sequence_invariants_require_diagnostics_authorization_and_eligibility():
    lifecycle = _lifecycle()

    with pytest.raises(LifecycleInvariantError):
        lifecycle.record_authorization(
            event_id="auth-too-early",
            decision=_decision(),
        )

    lifecycle.record_diagnostics(
        event_id="diag",
        diagnostics_ref="diag-ref",
    )

    with pytest.raises(LifecycleInvariantError):
        lifecycle.mark_remediating(
            event_id="start-too-early",
            execution_id="exec-1",
        )

    lifecycle.record_authorization(
        event_id="auth",
        decision=_decision(),
    )

    with pytest.raises(LifecycleInvariantError):
        lifecycle.mark_remediating(
            event_id="start-still-too-early",
            execution_id="exec-1",
        )

    assert lifecycle.state is IncidentWorkflowState.OPEN


def test_canonical_authorization_component_mismatch_is_rejected():
    lifecycle = _lifecycle()
    lifecycle.record_diagnostics(
        event_id="diag",
        diagnostics_ref="diag-ref",
    )

    with pytest.raises(LifecycleInvariantError):
        lifecycle.record_authorization(
            event_id="bad-auth",
            decision=_decision(component_id="pane-other"),
        )

    assert lifecycle.authorization_decision is None
    assert lifecycle.state is IncidentWorkflowState.OPEN
