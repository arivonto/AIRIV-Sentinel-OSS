from dataclasses import dataclass

import pytest

from sentinel.workflow.lifecycle import (
    IncidentWorkflowLifecycle,
    IncidentWorkflowState,
)


@dataclass(frozen=True)
class VerificationProbe:
    verified: object
    reason: str = "verification_probe"


def _ready_for_verification() -> IncidentWorkflowLifecycle:
    lifecycle = IncidentWorkflowLifecycle(
        workflow_id="wf-verification-type-integrity",
        incident_id="inc-verification-type-integrity",
        component_id="component-verification-type-integrity",
    )
    lifecycle.record_diagnostics(
        event_id="evt-diagnostics",
        diagnostics_ref="diagnostics://verification-type-integrity",
    )
    lifecycle.record_authorization(
        event_id="evt-authorization",
        decision="ALLOW",
    )
    lifecycle.record_remediation_eligibility(
        event_id="evt-eligibility",
        eligible=True,
    )
    lifecycle.mark_remediating(
        event_id="evt-remediation-started",
        execution_id="execution-verification-type-integrity",
    )
    lifecycle.record_remediation_result(
        event_id="evt-remediation-result",
        execution_id="execution-verification-type-integrity",
        success=True,
    )
    return lifecycle


@pytest.mark.parametrize(
    "malformed_verified",
    [
        pytest.param("false", id="string-false"),
        pytest.param("true", id="string-true"),
        pytest.param(1, id="integer-one"),
        pytest.param(0, id="integer-zero"),
        pytest.param(None, id="none"),
        pytest.param([], id="list"),
    ],
)
def test_non_boolean_verification_fails_closed_without_mutation(
    malformed_verified,
):
    lifecycle = _ready_for_verification()
    snapshot_before = lifecycle.snapshot()
    history_before = lifecycle.history

    with pytest.raises(
        TypeError,
        match=r"verification\.verified must be bool",
    ):
        lifecycle.record_verification(
            event_id="evt-malformed-verification",
            verification=VerificationProbe(malformed_verified),
        )

    assert lifecycle.snapshot() == snapshot_before
    assert lifecycle.history == history_before
    assert lifecycle.state is IncidentWorkflowState.REMEDIATING
    assert lifecycle.verification_passed is None


def test_valid_verification_can_follow_rejected_malformed_outcome():
    lifecycle = _ready_for_verification()

    with pytest.raises(TypeError):
        lifecycle.record_verification(
            event_id="evt-malformed-verification",
            verification=VerificationProbe("false"),
        )

    event = lifecycle.record_verification(
        event_id="evt-valid-verification",
        verification=VerificationProbe(True, "verified"),
    )

    snapshot = lifecycle.snapshot()
    assert event.state_before is IncidentWorkflowState.REMEDIATING
    assert event.state_after is IncidentWorkflowState.RECOVERED
    assert snapshot.state is IncidentWorkflowState.RECOVERED
    assert snapshot.verification_passed is True
    assert snapshot.failure_reason is None


def test_valid_false_verification_still_fails_deterministically():
    lifecycle = _ready_for_verification()

    event = lifecycle.record_verification(
        event_id="evt-valid-verification-failure",
        verification=VerificationProbe(False, "post-state-mismatch"),
    )

    snapshot = lifecycle.snapshot()
    assert event.state_before is IncidentWorkflowState.REMEDIATING
    assert event.state_after is IncidentWorkflowState.FAILED
    assert snapshot.state is IncidentWorkflowState.FAILED
    assert snapshot.verification_passed is False
    assert snapshot.failure_detail == "post-state-mismatch"
