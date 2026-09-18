from dataclasses import dataclass

import pytest

from sentinel.workflow.lifecycle import (
    IncidentWorkflowLifecycle,
    IncidentWorkflowState,
    LifecycleFailureReason,
)
from sentinel.workflow.lifecycle_store import (
    IncidentWorkflowLifecycleFileStore,
    IncidentWorkflowLifecycleStorageError,
)


@dataclass(frozen=True)
class MockDecision:
    decision: str = "ALLOW"
    component_id: str = "pane-1"


def _ready() -> IncidentWorkflowLifecycle:
    lifecycle = IncidentWorkflowLifecycle(
        workflow_id="wf-candidate-validation",
        incident_id="INC-CANDIDATE-VALIDATION",
        component_id="pane-1",
    )
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


def test_invalid_projection_cannot_create_durable_lifecycle(tmp_path):
    path = tmp_path / "invalid-create.json"
    store = IncidentWorkflowLifecycleFileStore(path)
    lifecycle = _ready()

    lifecycle.state = IncidentWorkflowState.RECOVERED

    with pytest.raises(IncidentWorkflowLifecycleStorageError):
        store.create(lifecycle)

    assert not path.exists()


def test_invalid_projection_cannot_replace_and_destroy_valid_failure_state(tmp_path):
    path = tmp_path / "invalid-replace.json"
    store = IncidentWorkflowLifecycleFileStore(path)
    lifecycle = _ready()
    lifecycle.mark_timeout(
        event_id="timeout-1",
        stage="verification",
    )
    store.create(lifecycle)

    loaded = store.load()
    assert loaded.lifecycle.state is IncidentWorkflowState.FAILED
    assert loaded.lifecycle.failure_reason is LifecycleFailureReason.TIMEOUT

    loaded.lifecycle.state = IncidentWorkflowState.RECOVERED
    loaded.lifecycle.failure_reason = None
    loaded.lifecycle.failure_detail = None

    with pytest.raises(IncidentWorkflowLifecycleStorageError):
        store.replace(
            loaded.lifecycle,
            expected_digest=loaded.digest,
        )

    durable = store.load()
    assert durable.digest == loaded.digest
    assert durable.lifecycle.state is IncidentWorkflowState.FAILED
    assert durable.lifecycle.failure_reason is LifecycleFailureReason.TIMEOUT
    assert durable.lifecycle.failure_detail == "verification"
