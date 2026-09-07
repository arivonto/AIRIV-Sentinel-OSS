from sentinel.execution import ExecutionBoundary
from sentinel.workflow.executor import (
    WorkflowDefinition,
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
