import copy
import json
from dataclasses import dataclass

import pytest

from sentinel.workflow.lifecycle import (
    DuplicateEventConflict,
    IncidentWorkflowLifecycle,
    IncidentWorkflowState,
    LifecycleFailureReason,
    LifecycleInvariantError,
)


@dataclass(frozen=True)
class MockDecision:
    decision: str = "ALLOW"
    component_id: str = "pane-1"


@dataclass(frozen=True)
class MockVerification:
    verified: bool
    reason: str | None = None


def _lifecycle():
    return IncidentWorkflowLifecycle(
        workflow_id="wf-replay",
        incident_id="INC-REPLAY",
        component_id="pane-1",
    )


def _ready():
    lifecycle = _lifecycle()
    lifecycle.record_diagnostics(
        event_id="diag-1",
        diagnostics_ref="diag-ref-1",
    )
    lifecycle.record_authorization(
        event_id="auth-1",
        decision=MockDecision(),
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


def test_recovered_lifecycle_roundtrip_preserves_history_and_event_idempotency():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result-1",
        execution_id="exec-1",
        success=True,
    )
    lifecycle.record_verification(
        event_id="verify-1",
        verification=MockVerification(
            verified=True,
            reason="postcondition satisfied",
        ),
    )

    replay_snapshot = lifecycle.to_replay_snapshot()
    encoded = json.dumps(
        replay_snapshot,
        sort_keys=True,
        separators=(",", ":"),
    )
    restored = IncidentWorkflowLifecycle.from_replay_snapshot(
        replay_snapshot
    )

    assert restored.snapshot() == lifecycle.snapshot()
    assert restored.history == lifecycle.history
    assert restored.to_replay_snapshot() == replay_snapshot
    assert json.dumps(
        restored.to_replay_snapshot(),
        sort_keys=True,
        separators=(",", ":"),
    ) == encoded

    before_count = len(restored.history)
    replay = restored.record_verification(
        event_id="verify-1",
        verification=MockVerification(
            verified=True,
            reason="postcondition satisfied",
        ),
    )
    assert replay == restored.history[-1]
    assert len(restored.history) == before_count
    assert restored.state is IncidentWorkflowState.RECOVERED

    with pytest.raises(DuplicateEventConflict):
        restored.record_verification(
            event_id="verify-1",
            verification=MockVerification(
                verified=False,
                reason="changed replay content",
            ),
        )


def test_remediating_snapshot_can_resume_with_verification_after_reconstruction():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result-ok",
        execution_id="exec-1",
        success=True,
    )
    assert lifecycle.state is IncidentWorkflowState.REMEDIATING

    restored = IncidentWorkflowLifecycle.from_replay_snapshot(
        lifecycle.to_replay_snapshot()
    )
    assert restored.state is IncidentWorkflowState.REMEDIATING
    assert restored.remediation_succeeded is True

    restored.record_verification(
        event_id="verify-after-restore",
        verification=MockVerification(
            verified=True,
            reason="deterministic simulation passed",
        ),
    )

    assert restored.state is IncidentWorkflowState.RECOVERED
    assert restored.failure_reason is None


@pytest.mark.parametrize(
    ("operation", "expected_reason", "expected_detail"),
    [
        ("timeout", LifecycleFailureReason.TIMEOUT, "verification"),
        (
            "cancel",
            LifecycleFailureReason.CANCELLED,
            "synthetic cancellation",
        ),
        (
            "retry",
            LifecycleFailureReason.RETRY_EXHAUSTED,
            "bounded retries exhausted",
        ),
    ],
)
def test_terminal_control_failures_survive_reconstruction_and_remain_terminal(
    operation,
    expected_reason,
    expected_detail,
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
            reason="synthetic cancellation",
        )
    else:
        lifecycle.mark_retry_exhausted(
            event_id="terminal-event",
            attempts=3,
            detail="bounded retries exhausted",
        )

    restored = IncidentWorkflowLifecycle.from_replay_snapshot(
        lifecycle.to_replay_snapshot()
    )
    assert restored.state is IncidentWorkflowState.FAILED
    assert restored.failure_reason is expected_reason
    assert restored.failure_detail == expected_detail

    before_count = len(restored.history)
    if operation == "timeout":
        restored.mark_timeout(
            event_id="terminal-event",
            stage="verification",
        )
    elif operation == "cancel":
        restored.cancel(
            event_id="terminal-event",
            reason="synthetic cancellation",
        )
    else:
        restored.mark_retry_exhausted(
            event_id="terminal-event",
            attempts=3,
            detail="bounded retries exhausted",
        )
    assert len(restored.history) == before_count

    with pytest.raises(LifecycleInvariantError):
        restored.record_verification(
            event_id="late-recovery",
            verification=True,
        )
    assert restored.failure_reason is expected_reason
    assert restored.failure_detail == expected_detail


def test_remediation_failure_survives_reconstruction_and_cannot_be_overwritten():
    lifecycle = _ready()
    lifecycle.record_remediation_result(
        event_id="result-failed",
        execution_id="exec-1",
        success=False,
    )

    restored = IncidentWorkflowLifecycle.from_replay_snapshot(
        lifecycle.to_replay_snapshot()
    )
    assert restored.state is IncidentWorkflowState.FAILED
    assert (
        restored.failure_reason
        is LifecycleFailureReason.REMEDIATION_FAILED
    )

    replay = restored.record_remediation_result(
        event_id="result-failed",
        execution_id="exec-1",
        success=False,
    )
    assert replay == restored.history[-1]

    with pytest.raises(LifecycleInvariantError):
        restored.record_remediation_result(
            event_id="late-success",
            execution_id="exec-1",
            success=True,
        )
    assert (
        restored.failure_reason
        is LifecycleFailureReason.REMEDIATION_FAILED
    )


def test_reordered_history_fails_closed_during_reconstruction():
    replay_snapshot = _ready().to_replay_snapshot()
    reordered = copy.deepcopy(replay_snapshot)
    reordered["events"][0], reordered["events"][1] = (
        reordered["events"][1],
        reordered["events"][0],
    )

    with pytest.raises(LifecycleInvariantError):
        IncidentWorkflowLifecycle.from_replay_snapshot(reordered)


def test_truncated_history_cannot_claim_later_projection_state():
    replay_snapshot = _ready().to_replay_snapshot()
    truncated = copy.deepcopy(replay_snapshot)
    truncated["events"].pop()

    with pytest.raises(LifecycleInvariantError):
        IncidentWorkflowLifecycle.from_replay_snapshot(truncated)


def test_tampered_event_metadata_and_duplicate_history_fail_closed():
    replay_snapshot = _ready().to_replay_snapshot()

    tampered = copy.deepcopy(replay_snapshot)
    tampered["events"][0]["state_after"] = "FAILED"
    with pytest.raises(LifecycleInvariantError):
        IncidentWorkflowLifecycle.from_replay_snapshot(tampered)

    duplicated = copy.deepcopy(replay_snapshot)
    duplicated["events"].append(copy.deepcopy(duplicated["events"][0]))
    with pytest.raises(DuplicateEventConflict):
        IncidentWorkflowLifecycle.from_replay_snapshot(duplicated)
