import json

import pytest

from sentinel.execution import ExecutionBoundary, ExecutionResult
from sentinel.workflow.executor import (
    WorkflowDefinition,
    WorkflowExecutionConflict,
    WorkflowExecutionJournal,
    WorkflowExecutor,
    WorkflowStatus,
    WorkflowStep,
    WorkflowValidationError,
)


def test_workflow_executes_steps_sequentially():
    executor = WorkflowExecutor(ExecutionBoundary())

    workflow = WorkflowDefinition(
        workflow_id="wf-001",
        steps=(
            WorkflowStep("step-1", "printf 'one'"),
            WorkflowStep("step-2", "printf 'two'"),
        ),
    )

    result = executor.execute(workflow, "exec-001")

    assert result.status is WorkflowStatus.SUCCEEDED
    assert [step.step_id for step in result.steps] == [
        "step-1",
        "step-2",
    ]
    assert result.steps[0].execution.stdout == "one"
    assert result.steps[1].execution.stdout == "two"


def test_required_failure_stops_dependent_steps():
    executor = WorkflowExecutor(ExecutionBoundary())

    workflow = WorkflowDefinition(
        workflow_id="wf-002",
        steps=(
            WorkflowStep("step-1", "sh -c 'exit 7'"),
            WorkflowStep("step-2", "printf 'must-not-run'"),
        ),
    )

    result = executor.execute(workflow, "exec-002")

    assert result.status is WorkflowStatus.FAILED
    assert len(result.steps) == 1
    assert result.steps[0].execution.exit_code == 7


def test_validation_rejects_duplicate_step_ids():
    executor = WorkflowExecutor(ExecutionBoundary())

    workflow = WorkflowDefinition(
        workflow_id="wf-003",
        steps=(
            WorkflowStep("same", "true"),
            WorkflowStep("same", "true"),
        ),
    )

    try:
        executor.execute(workflow, "exec-003")
    except WorkflowValidationError:
        pass
    else:
        raise AssertionError("duplicate step_id was not rejected")


def test_validation_rejects_empty_workflow():
    executor = WorkflowExecutor(ExecutionBoundary())

    workflow = WorkflowDefinition(
        workflow_id="wf-004",
        steps=(),
    )

    try:
        executor.execute(workflow, "exec-004")
    except WorkflowValidationError:
        pass
    else:
        raise AssertionError("empty workflow was not rejected")


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


def build_idempotent_workflow(command="synthetic-command"):
    return WorkflowDefinition(
        workflow_id="wf-idempotent",
        steps=(WorkflowStep("only", command),),
    )


def test_execution_id_replay_does_not_execute_steps_twice():
    boundary = CountingExecutionBoundary()
    executor = WorkflowExecutor(boundary)
    workflow = build_idempotent_workflow()

    first = executor.execute(workflow, "exec-idempotent")
    replay = executor.execute(workflow, "exec-idempotent")

    assert boundary.calls == ["synthetic-command"]
    assert first.status is WorkflowStatus.SUCCEEDED
    assert first.replayed is False
    assert replay.status is WorkflowStatus.SUCCEEDED
    assert replay.replayed is True
    assert replay.steps == first.steps


def test_execution_id_reuse_for_changed_workflow_fails_closed():
    boundary = CountingExecutionBoundary()
    executor = WorkflowExecutor(boundary)
    first = WorkflowDefinition(
        workflow_id="wf-conflict",
        steps=(WorkflowStep("step", "first-command"),),
    )
    changed = WorkflowDefinition(
        workflow_id="wf-conflict",
        steps=(WorkflowStep("step", "changed-command"),),
    )

    executor.execute(first, "exec-conflict")

    with pytest.raises(WorkflowExecutionConflict):
        executor.execute(changed, "exec-conflict")

    assert boundary.calls == ["first-command"]


def test_failed_execution_replay_preserves_failure_without_reexecution():
    boundary = CountingExecutionBoundary(exit_code=7)
    executor = WorkflowExecutor(boundary)
    workflow = WorkflowDefinition(
        workflow_id="wf-failed-replay",
        steps=(
            WorkflowStep("required", "synthetic-failure"),
            WorkflowStep("blocked", "must-not-run"),
        ),
    )

    first = executor.execute(workflow, "exec-failed")
    replay = executor.execute(workflow, "exec-failed")

    assert boundary.calls == ["synthetic-failure"]
    assert first.status is WorkflowStatus.FAILED
    assert replay.status is WorkflowStatus.FAILED
    assert replay.replayed is True
    assert len(replay.steps) == 1
    assert replay.steps[0].execution.exit_code == 7


def test_shared_journal_prevents_reexecution_after_executor_reconstruction():
    journal = WorkflowExecutionJournal()
    first_boundary = CountingExecutionBoundary()
    first_executor = WorkflowExecutor(first_boundary, journal=journal)
    workflow = build_idempotent_workflow()

    first = first_executor.execute(workflow, "exec-restart")

    second_boundary = CountingExecutionBoundary()
    second_executor = WorkflowExecutor(second_boundary, journal=journal)
    replay = second_executor.execute(workflow, "exec-restart")

    assert first_boundary.calls == ["synthetic-command"]
    assert second_boundary.calls == []
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.status is WorkflowStatus.SUCCEEDED
    assert replay.steps == first.steps


def test_serialized_journal_restoration_prevents_reexecution():
    first_boundary = CountingExecutionBoundary()
    journal = WorkflowExecutionJournal()
    first_executor = WorkflowExecutor(first_boundary, journal=journal)
    workflow = build_idempotent_workflow()

    first = first_executor.execute(workflow, "exec-snapshot")
    serialized = json.dumps(journal.to_snapshot(), sort_keys=True)
    restored = WorkflowExecutionJournal.from_snapshot(json.loads(serialized))

    second_boundary = CountingExecutionBoundary()
    second_executor = WorkflowExecutor(second_boundary, journal=restored)
    replay = second_executor.execute(workflow, "exec-snapshot")

    assert first_boundary.calls == ["synthetic-command"]
    assert second_boundary.calls == []
    assert replay.replayed is True
    assert replay.status is first.status
    assert replay.steps == first.steps


def test_restored_failed_execution_remains_failed_without_reexecution():
    first_boundary = CountingExecutionBoundary(exit_code=9)
    journal = WorkflowExecutionJournal()
    first_executor = WorkflowExecutor(first_boundary, journal=journal)
    workflow = WorkflowDefinition(
        workflow_id="wf-restored-failure",
        steps=(WorkflowStep("required", "synthetic-failure"),),
    )

    first = first_executor.execute(workflow, "exec-restored-failure")
    restored = WorkflowExecutionJournal.from_snapshot(
        json.loads(json.dumps(journal.to_snapshot()))
    )

    second_boundary = CountingExecutionBoundary(exit_code=0)
    replay = WorkflowExecutor(
        second_boundary,
        journal=restored,
    ).execute(workflow, "exec-restored-failure")

    assert first.status is WorkflowStatus.FAILED
    assert replay.status is WorkflowStatus.FAILED
    assert replay.replayed is True
    assert second_boundary.calls == []
    assert replay.steps[0].execution.exit_code == 9


def test_restored_journal_rejects_changed_workflow_before_execution():
    first_boundary = CountingExecutionBoundary()
    journal = WorkflowExecutionJournal()
    executor = WorkflowExecutor(first_boundary, journal=journal)
    original = build_idempotent_workflow("original-command")

    executor.execute(original, "exec-restored-conflict")
    restored = WorkflowExecutionJournal.from_snapshot(
        json.loads(json.dumps(journal.to_snapshot()))
    )

    changed_boundary = CountingExecutionBoundary()
    changed = build_idempotent_workflow("changed-command")

    with pytest.raises(WorkflowExecutionConflict):
        WorkflowExecutor(
            changed_boundary,
            journal=restored,
        ).execute(changed, "exec-restored-conflict")

    assert changed_boundary.calls == []


def test_snapshot_duplicate_execution_identity_conflict_fails_closed():
    boundary = CountingExecutionBoundary()
    journal = WorkflowExecutionJournal()
    executor = WorkflowExecutor(boundary, journal=journal)
    workflow = build_idempotent_workflow()

    executor.execute(workflow, "exec-duplicate-snapshot")
    snapshot = journal.to_snapshot()
    duplicate = json.loads(json.dumps(snapshot["records"][0]))
    duplicate["fingerprint"] = "different-fingerprint"
    snapshot["records"].append(duplicate)

    with pytest.raises(WorkflowExecutionConflict):
        WorkflowExecutionJournal.from_snapshot(snapshot)
