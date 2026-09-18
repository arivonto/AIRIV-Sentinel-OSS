import json
from dataclasses import dataclass

import pytest

from sentinel.workflow.lifecycle import (
    IncidentWorkflowLifecycle,
    IncidentWorkflowState,
    LifecycleFailureReason,
    LifecycleInvariantError,
)
from sentinel.workflow.lifecycle_store import (
    IncidentWorkflowLifecycleFileStore,
    IncidentWorkflowLifecycleStorageConflict,
    IncidentWorkflowLifecycleStorageError,
)


@dataclass(frozen=True)
class MockDecision:
    decision: str = "ALLOW"
    component_id: str = "pane-1"


@dataclass(frozen=True)
class MockVerification:
    verified: bool
    reason: str | None = None


def _lifecycle(
    *,
    workflow_id: str = "wf-store",
    incident_id: str = "INC-STORE",
    component_id: str = "pane-1",
) -> IncidentWorkflowLifecycle:
    return IncidentWorkflowLifecycle(
        workflow_id=workflow_id,
        incident_id=incident_id,
        component_id=component_id,
    )


def _ready() -> IncidentWorkflowLifecycle:
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


def test_durable_open_remediating_recovered_roundtrip_preserves_idempotency(
    tmp_path,
):
    store = IncidentWorkflowLifecycleFileStore(tmp_path / "lifecycle.json")
    created = store.create(_lifecycle())

    opened = store.load()
    assert opened.lifecycle.state is IncidentWorkflowState.OPEN
    assert opened.lifecycle.snapshot().event_count == 0
    assert opened.digest == created.digest

    lifecycle = opened.lifecycle
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
    remediating = store.replace(
        lifecycle,
        expected_digest=opened.digest,
    )

    restored = store.load()
    assert restored.digest == remediating.digest
    assert restored.lifecycle.state is IncidentWorkflowState.REMEDIATING
    assert restored.lifecycle.execution_id == "exec-1"

    restored.lifecycle.record_remediation_result(
        event_id="result-1",
        execution_id="exec-1",
        success=True,
    )
    restored.lifecycle.record_verification(
        event_id="verify-1",
        verification=MockVerification(
            verified=True,
            reason="synthetic postcondition satisfied",
        ),
    )
    recovered = store.replace(
        restored.lifecycle,
        expected_digest=restored.digest,
    )

    final = store.load()
    assert final.digest == recovered.digest
    assert final.lifecycle.state is IncidentWorkflowState.RECOVERED
    assert final.lifecycle.failure_reason is None
    assert final.lifecycle.verification_passed is True

    before = len(final.lifecycle.history)
    replay = final.lifecycle.record_verification(
        event_id="verify-1",
        verification=MockVerification(
            verified=True,
            reason="synthetic postcondition satisfied",
        ),
    )
    assert replay == final.lifecycle.history[-1]
    assert len(final.lifecycle.history) == before
    assert final.lifecycle.state is IncidentWorkflowState.RECOVERED


@pytest.mark.parametrize(
    ("operation", "expected_reason"),
    [
        ("timeout", LifecycleFailureReason.TIMEOUT),
        ("cancel", LifecycleFailureReason.CANCELLED),
        ("retry", LifecycleFailureReason.RETRY_EXHAUSTED),
        ("remediation", LifecycleFailureReason.REMEDIATION_FAILED),
        ("verification", LifecycleFailureReason.VERIFICATION_FAILED),
    ],
)
def test_durable_terminal_failures_survive_reconstruction_and_remain_terminal(
    tmp_path,
    operation,
    expected_reason,
):
    lifecycle = _ready()

    if operation == "timeout":
        lifecycle.mark_timeout(
            event_id="terminal-1",
            stage="verification",
        )
    elif operation == "cancel":
        lifecycle.cancel(
            event_id="terminal-1",
            reason="synthetic cancellation",
        )
    elif operation == "retry":
        lifecycle.mark_retry_exhausted(
            event_id="terminal-1",
            attempts=3,
            detail="bounded retries exhausted",
        )
    elif operation == "remediation":
        lifecycle.record_remediation_result(
            event_id="terminal-1",
            execution_id="exec-1",
            success=False,
        )
    else:
        lifecycle.record_remediation_result(
            event_id="result-1",
            execution_id="exec-1",
            success=True,
        )
        lifecycle.record_verification(
            event_id="terminal-1",
            verification=MockVerification(
                verified=False,
                reason="synthetic verification failure",
            ),
        )

    store = IncidentWorkflowLifecycleFileStore(
        tmp_path / f"{operation}.json"
    )
    store.create(lifecycle)
    restored = store.load().lifecycle

    assert restored.state is IncidentWorkflowState.FAILED
    assert restored.failure_reason is expected_reason

    preserved_detail = restored.failure_detail
    with pytest.raises(LifecycleInvariantError):
        restored.record_verification(
            event_id="late-recovery",
            verification=True,
        )
    assert restored.state is IncidentWorkflowState.FAILED
    assert restored.failure_reason is expected_reason
    assert restored.failure_detail == preserved_detail


def test_missing_corrupt_and_tampered_store_fail_closed(tmp_path):
    missing = IncidentWorkflowLifecycleFileStore(tmp_path / "missing.json")
    with pytest.raises(IncidentWorkflowLifecycleStorageError):
        missing.load()

    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{not-json", encoding="utf-8")
    corrupt = IncidentWorkflowLifecycleFileStore(corrupt_path)
    with pytest.raises(IncidentWorkflowLifecycleStorageError):
        corrupt.load()

    tampered_path = tmp_path / "tampered.json"
    tampered = IncidentWorkflowLifecycleFileStore(tampered_path)
    tampered.create(_ready())
    envelope = json.loads(tampered_path.read_text(encoding="utf-8"))
    envelope["lifecycle"]["projection"]["state"] = "RECOVERED"
    tampered_path.write_text(
        json.dumps(envelope, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(IncidentWorkflowLifecycleStorageError):
        tampered.load()


def test_recomputed_digest_cannot_bypass_lifecycle_replay_validation(tmp_path):
    path = tmp_path / "recomputed.json"
    store = IncidentWorkflowLifecycleFileStore(path)
    store.create(_ready())

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["lifecycle"]["projection"]["state"] = "RECOVERED"
    payload = store._canonical_payload(envelope["lifecycle"])

    import hashlib

    envelope["digest"] = hashlib.sha256(payload).hexdigest()
    path.write_text(
        json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(IncidentWorkflowLifecycleStorageError):
        store.load()


def test_stale_writer_cannot_erase_newer_lifecycle_events(tmp_path):
    store = IncidentWorkflowLifecycleFileStore(tmp_path / "lifecycle.json")
    store.create(_lifecycle())

    writer_a = store.load()
    writer_b = store.load()

    writer_a.lifecycle.record_diagnostics(
        event_id="diag-a",
        diagnostics_ref="writer-a",
    )
    committed = store.replace(
        writer_a.lifecycle,
        expected_digest=writer_a.digest,
    )

    writer_b.lifecycle.record_diagnostics(
        event_id="diag-b",
        diagnostics_ref="writer-b",
    )
    with pytest.raises(IncidentWorkflowLifecycleStorageConflict):
        store.replace(
            writer_b.lifecycle,
            expected_digest=writer_b.digest,
        )

    durable = store.load()
    assert durable.digest == committed.digest
    assert [event.event_id for event in durable.lifecycle.history] == ["diag-a"]


def test_store_identity_cannot_switch_incident_workflow_or_component(tmp_path):
    store = IncidentWorkflowLifecycleFileStore(tmp_path / "lifecycle.json")
    current = store.create(_lifecycle())

    candidates = [
        _lifecycle(workflow_id="wf-other"),
        _lifecycle(incident_id="INC-OTHER"),
        _lifecycle(component_id="pane-other"),
    ]
    for candidate in candidates:
        with pytest.raises(IncidentWorkflowLifecycleStorageConflict):
            store.replace(
                candidate,
                expected_digest=current.digest,
            )

    durable = store.load().lifecycle
    assert durable.workflow_id == "wf-store"
    assert durable.incident_id == "INC-STORE"
    assert durable.component_id == "pane-1"


def test_current_digest_cannot_authorize_history_rollback_or_rewrite(tmp_path):
    store = IncidentWorkflowLifecycleFileStore(tmp_path / "lifecycle.json")
    current = store.create(_ready())

    rollback = _lifecycle()
    with pytest.raises(IncidentWorkflowLifecycleStorageConflict):
        store.replace(
            rollback,
            expected_digest=current.digest,
        )

    rewrite = _lifecycle()
    rewrite.record_diagnostics(
        event_id="diag-1",
        diagnostics_ref="different-diagnostics",
    )
    rewrite.record_authorization(
        event_id="auth-1",
        decision=MockDecision(),
    )
    rewrite.record_remediation_eligibility(
        event_id="elig-1",
        eligible=True,
    )
    rewrite.mark_remediating(
        event_id="start-1",
        execution_id="exec-1",
    )
    with pytest.raises(IncidentWorkflowLifecycleStorageConflict):
        store.replace(
            rewrite,
            expected_digest=current.digest,
        )

    durable = store.load().lifecycle
    assert durable.state is IncidentWorkflowState.REMEDIATING
    assert durable.to_replay_snapshot() == _ready().to_replay_snapshot()
