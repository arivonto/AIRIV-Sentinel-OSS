import json

import pytest

from sentinel.execution import ExecutionBoundary, ExecutionResult
from sentinel.workflow.executor import (
    WorkflowDefinition,
    WorkflowExecutionJournal,
    WorkflowExecutor,
    WorkflowStatus,
    WorkflowStep,
)
from sentinel.workflow.journal_store import (
    WorkflowExecutionJournalFileStore,
    WorkflowJournalStorageConflict,
    WorkflowJournalStorageError,
)


class CountingExecutionBoundary(ExecutionBoundary):
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.calls = []

    def execute(self, command: str) -> ExecutionResult:
        self.calls.append(command)
        return ExecutionResult(
            command=command,
            stdout="synthetic",
            stderr="",
            exit_code=self.exit_code,
            started_at=1.0,
            finished_at=2.0,
        )


def workflow(command="synthetic-command"):
    return WorkflowDefinition(
        workflow_id="wf-durable-replay",
        steps=(WorkflowStep("only", command),),
    )


def test_store_round_trip_preserves_replay_across_executor_reconstruction(tmp_path):
    path = tmp_path / "workflow-replay.json"
    store = WorkflowExecutionJournalFileStore(path)
    stored = store.create()

    first_boundary = CountingExecutionBoundary()
    first_executor = WorkflowExecutor(
        first_boundary,
        journal=stored.journal,
    )
    first = first_executor.execute(workflow(), "exec-durable")

    committed = store.replace(
        stored.journal,
        expected_digest=stored.digest,
    )
    assert committed.digest != stored.digest
    assert first.status is WorkflowStatus.SUCCEEDED
    assert first_boundary.calls == ["synthetic-command"]

    restored = store.load()
    second_boundary = CountingExecutionBoundary()
    second_executor = WorkflowExecutor(
        second_boundary,
        journal=restored.journal,
    )
    replay = second_executor.execute(workflow(), "exec-durable")

    assert replay.status is WorkflowStatus.SUCCEEDED
    assert replay.replayed is True
    assert second_boundary.calls == []


def test_store_preserves_failed_replay_without_reexecution(tmp_path):
    path = tmp_path / "workflow-failure.json"
    store = WorkflowExecutionJournalFileStore(path)
    stored = store.create()

    first_boundary = CountingExecutionBoundary(exit_code=9)
    first_executor = WorkflowExecutor(
        first_boundary,
        journal=stored.journal,
    )
    first = first_executor.execute(workflow("synthetic-failure"), "exec-failed")
    store.replace(stored.journal, expected_digest=stored.digest)

    restored = store.load()
    second_boundary = CountingExecutionBoundary(exit_code=0)
    replay = WorkflowExecutor(
        second_boundary,
        journal=restored.journal,
    ).execute(workflow("synthetic-failure"), "exec-failed")

    assert first.status is WorkflowStatus.FAILED
    assert replay.status is WorkflowStatus.FAILED
    assert replay.replayed is True
    assert second_boundary.calls == []


def test_load_missing_store_fails_closed_instead_of_returning_empty(tmp_path):
    store = WorkflowExecutionJournalFileStore(
        tmp_path / "missing-workflow-replay.json"
    )

    with pytest.raises(
        WorkflowJournalStorageError,
        match="does not exist",
    ):
        store.load()


def test_create_refuses_to_overwrite_existing_store(tmp_path):
    path = tmp_path / "workflow-replay.json"
    store = WorkflowExecutionJournalFileStore(path)
    store.create()

    with pytest.raises(
        WorkflowJournalStorageConflict,
        match="already exists",
    ):
        store.create()


def test_integrity_failure_rejects_tampered_snapshot(tmp_path):
    path = tmp_path / "workflow-replay.json"
    store = WorkflowExecutionJournalFileStore(path)
    stored = store.create()

    boundary = CountingExecutionBoundary()
    WorkflowExecutor(boundary, journal=stored.journal).execute(
        workflow(),
        "exec-tamper",
    )
    store.replace(stored.journal, expected_digest=stored.digest)

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["journal"]["records"][0]["result"]["status"] = "FAILED"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(
        WorkflowJournalStorageError,
        match="integrity check failed",
    ):
        store.load()


def test_stale_replace_is_rejected_without_erasing_newer_replay_state(tmp_path):
    path = tmp_path / "workflow-replay.json"
    store = WorkflowExecutionJournalFileStore(path)
    initial = store.create()

    writer_one = store.load()
    writer_two = store.load()

    WorkflowExecutor(
        CountingExecutionBoundary(),
        journal=writer_one.journal,
    ).execute(workflow("writer-one"), "exec-one")
    latest = store.replace(
        writer_one.journal,
        expected_digest=writer_one.digest,
    )

    WorkflowExecutor(
        CountingExecutionBoundary(),
        journal=writer_two.journal,
    ).execute(workflow("writer-two"), "exec-two")

    with pytest.raises(
        WorkflowJournalStorageConflict,
        match="changed since it was loaded",
    ):
        store.replace(
            writer_two.journal,
            expected_digest=writer_two.digest,
        )

    preserved = store.load()
    assert preserved.digest == latest.digest
    assert preserved.journal.get("exec-one") is not None
    assert preserved.journal.get("exec-two") is None
    assert initial.digest != latest.digest


def test_store_rejects_snapshot_that_is_valid_json_but_invalid_journal(tmp_path):
    path = tmp_path / "workflow-replay.json"
    store = WorkflowExecutionJournalFileStore(path)

    invalid_snapshot = {
        "version": WorkflowExecutionJournal.SNAPSHOT_VERSION,
        "records": [
            {
                "execution_id": "exec-invalid",
                "fingerprint": "f" * 64,
                "result": {
                    "workflow_id": "wf-invalid",
                    "execution_id": "different-execution-id",
                    "status": "SUCCEEDED",
                    "steps": [],
                },
            }
        ],
    }
    payload = store._canonical_payload(invalid_snapshot)
    import hashlib

    envelope = {
        "store_version": store.STORE_VERSION,
        "digest": hashlib.sha256(payload).hexdigest(),
        "journal": invalid_snapshot,
    }
    path.write_text(
        json.dumps(envelope, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(
        WorkflowJournalStorageError,
        match="snapshot failed validation",
    ):
        store.load()
