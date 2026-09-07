"""Canonical deterministic workflow execution boundary V1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from sentinel.execution import ExecutionBoundary, ExecutionResult


class WorkflowStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    command: str
    required: bool = True


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    steps: Sequence[WorkflowStep]


@dataclass(frozen=True)
class WorkflowStepResult:
    step_id: str
    execution: ExecutionResult


@dataclass(frozen=True)
class WorkflowExecutionResult:
    workflow_id: str
    execution_id: str
    status: WorkflowStatus
    steps: tuple[WorkflowStepResult, ...]


class WorkflowValidationError(ValueError):
    """Raised when a workflow definition violates the execution boundary."""


class WorkflowExecutor:
    """Execute an explicit workflow sequentially through ExecutionBoundary."""

    def __init__(self, execution: ExecutionBoundary) -> None:
        if not isinstance(execution, ExecutionBoundary):
            raise TypeError("execution must be an ExecutionBoundary")
        self.execution = execution

    @staticmethod
    def validate(workflow: WorkflowDefinition) -> None:
        if not isinstance(workflow, WorkflowDefinition):
            raise TypeError("workflow must be a WorkflowDefinition")

        if not workflow.workflow_id:
            raise WorkflowValidationError("workflow_id is required")

        if not workflow.steps:
            raise WorkflowValidationError(
                "workflow must contain at least one step"
            )

        seen: set[str] = set()

        for step in workflow.steps:
            if not isinstance(step, WorkflowStep):
                raise WorkflowValidationError(
                    "workflow steps must be WorkflowStep instances"
                )

            if not step.step_id:
                raise WorkflowValidationError("step_id is required")

            if step.step_id in seen:
                raise WorkflowValidationError(
                    f"duplicate step_id: {step.step_id}"
                )

            if not step.command or not step.command.strip():
                raise WorkflowValidationError(
                    f"empty command for step: {step.step_id}"
                )

            seen.add(step.step_id)

    def execute(
        self,
        workflow: WorkflowDefinition,
        execution_id: str,
    ) -> WorkflowExecutionResult:
        self.validate(workflow)

        if not execution_id:
            raise ValueError("execution_id is required")

        results: list[WorkflowStepResult] = []

        for step in workflow.steps:
            execution = self.execution.execute(step.command)

            results.append(
                WorkflowStepResult(
                    step_id=step.step_id,
                    execution=execution,
                )
            )

            if not execution.success and step.required:
                return WorkflowExecutionResult(
                    workflow_id=workflow.workflow_id,
                    execution_id=execution_id,
                    status=WorkflowStatus.FAILED,
                    steps=tuple(results),
                )

        return WorkflowExecutionResult(
            workflow_id=workflow.workflow_id,
            execution_id=execution_id,
            status=WorkflowStatus.SUCCEEDED,
            steps=tuple(results),
        )
