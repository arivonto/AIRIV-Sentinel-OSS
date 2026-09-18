"""Canonical deterministic workflow execution boundary V1."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence

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
    replayed: bool = False


class WorkflowValidationError(ValueError):
    """Raised when a workflow definition violates the execution boundary."""


class WorkflowExecutionConflict(RuntimeError):
    """Raised when an execution identity conflicts with recorded content."""


class WorkflowExecutionJournal:
    """Replay journal independent from any one WorkflowExecutor instance.

    The journal intentionally owns no filesystem, database, or runtime side
    effect. Callers may retain the object across executor reconstruction or
    persist ``to_snapshot()`` through an authority-appropriate storage layer.
    Restoring a snapshot reconstructs immutable execution evidence and keeps
    execution-id conflict detection fail-closed.
    """

    SNAPSHOT_VERSION = 1

    def __init__(self) -> None:
        self._records: dict[
            str,
            tuple[str, WorkflowExecutionResult],
        ] = {}

    def get(
        self,
        execution_id: str,
    ) -> tuple[str, WorkflowExecutionResult] | None:
        return self._records.get(execution_id)

    def record(
        self,
        *,
        execution_id: str,
        fingerprint: str,
        result: WorkflowExecutionResult,
    ) -> WorkflowExecutionResult:
        if not execution_id:
            raise ValueError("execution_id is required")
        if not fingerprint:
            raise ValueError("workflow fingerprint is required")
        if not isinstance(result, WorkflowExecutionResult):
            raise TypeError("result must be a WorkflowExecutionResult")
        if result.execution_id != execution_id:
            raise WorkflowExecutionConflict(
                "journal result execution_id mismatch"
            )

        existing = self._records.get(execution_id)
        candidate = (fingerprint, result)

        if existing is not None:
            if existing != candidate:
                raise WorkflowExecutionConflict(
                    "execution_id already recorded with different content"
                )
            return existing[1]

        self._records[execution_id] = candidate
        return result

    def to_snapshot(self) -> dict[str, Any]:
        """Return a deterministic JSON-serializable replay snapshot."""
        records = []

        for execution_id in sorted(self._records):
            fingerprint, result = self._records[execution_id]
            records.append(
                {
                    "execution_id": execution_id,
                    "fingerprint": fingerprint,
                    "result": {
                        "workflow_id": result.workflow_id,
                        "execution_id": result.execution_id,
                        "status": result.status.value,
                        "steps": [
                            {
                                "step_id": step.step_id,
                                "execution": {
                                    "command": step.execution.command,
                                    "stdout": step.execution.stdout,
                                    "stderr": step.execution.stderr,
                                    "exit_code": step.execution.exit_code,
                                    "started_at": step.execution.started_at,
                                    "finished_at": step.execution.finished_at,
                                },
                            }
                            for step in result.steps
                        ],
                    },
                }
            )

        return {
            "version": self.SNAPSHOT_VERSION,
            "records": records,
        }

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
    ) -> "WorkflowExecutionJournal":
        """Restore a replay journal from untrusted serialized state.

        Malformed, duplicate, or contradictory records fail closed before the
        returned journal can be used for workflow execution.
        """
        if not isinstance(snapshot, Mapping):
            raise TypeError("workflow journal snapshot must be a mapping")

        if snapshot.get("version") != cls.SNAPSHOT_VERSION:
            raise WorkflowValidationError(
                "unsupported workflow journal snapshot version"
            )

        records = snapshot.get("records")
        if not isinstance(records, list):
            raise WorkflowValidationError(
                "workflow journal snapshot records must be a list"
            )

        journal = cls()

        for entry in records:
            if not isinstance(entry, Mapping):
                raise WorkflowValidationError(
                    "workflow journal record must be a mapping"
                )

            execution_id = entry.get("execution_id")
            fingerprint = entry.get("fingerprint")
            result_data = entry.get("result")

            if not isinstance(execution_id, str) or not execution_id:
                raise WorkflowValidationError(
                    "workflow journal execution_id is required"
                )
            if not isinstance(fingerprint, str) or not fingerprint:
                raise WorkflowValidationError(
                    "workflow journal fingerprint is required"
                )
            if not isinstance(result_data, Mapping):
                raise WorkflowValidationError(
                    "workflow journal result must be a mapping"
                )

            if result_data.get("execution_id") != execution_id:
                raise WorkflowExecutionConflict(
                    "snapshot result execution_id mismatch"
                )

            workflow_id = result_data.get("workflow_id")
            if not isinstance(workflow_id, str) or not workflow_id:
                raise WorkflowValidationError(
                    "workflow journal workflow_id is required"
                )

            try:
                status = WorkflowStatus(result_data.get("status"))
            except (TypeError, ValueError) as exc:
                raise WorkflowValidationError(
                    "invalid workflow journal status"
                ) from exc

            if status not in {
                WorkflowStatus.SUCCEEDED,
                WorkflowStatus.FAILED,
            }:
                raise WorkflowValidationError(
                    "journal may restore only terminal workflow results"
                )

            steps_data = result_data.get("steps")
            if not isinstance(steps_data, list):
                raise WorkflowValidationError(
                    "workflow journal steps must be a list"
                )

            steps: list[WorkflowStepResult] = []

            for step_data in steps_data:
                if not isinstance(step_data, Mapping):
                    raise WorkflowValidationError(
                        "workflow journal step must be a mapping"
                    )

                step_id = step_data.get("step_id")
                execution_data = step_data.get("execution")

                if not isinstance(step_id, str) or not step_id:
                    raise WorkflowValidationError(
                        "workflow journal step_id is required"
                    )
                if not isinstance(execution_data, Mapping):
                    raise WorkflowValidationError(
                        "workflow journal execution must be a mapping"
                    )

                required_execution_fields = {
                    "command",
                    "stdout",
                    "stderr",
                    "exit_code",
                    "started_at",
                    "finished_at",
                }
                if not required_execution_fields.issubset(execution_data):
                    raise WorkflowValidationError(
                        "workflow journal execution evidence is incomplete"
                    )

                try:
                    execution = ExecutionResult(
                        command=execution_data["command"],
                        stdout=execution_data["stdout"],
                        stderr=execution_data["stderr"],
                        exit_code=execution_data["exit_code"],
                        started_at=execution_data["started_at"],
                        finished_at=execution_data["finished_at"],
                    )
                except (TypeError, ValueError, KeyError) as exc:
                    raise WorkflowValidationError(
                        "invalid workflow journal execution evidence"
                    ) from exc

                steps.append(
                    WorkflowStepResult(
                        step_id=step_id,
                        execution=execution,
                    )
                )

            result = WorkflowExecutionResult(
                workflow_id=workflow_id,
                execution_id=execution_id,
                status=status,
                steps=tuple(steps),
            )

            journal.record(
                execution_id=execution_id,
                fingerprint=fingerprint,
                result=result,
            )

        return journal


class WorkflowExecutor:
    """Execute an explicit workflow sequentially through ExecutionBoundary.

    Completed execution identities are replay-safe through an explicit journal.
    Reusing the same execution_id with the same workflow returns the recorded
    result without executing commands again. Reusing it for different workflow
    content fails closed.
    """

    def __init__(
        self,
        execution: ExecutionBoundary,
        journal: WorkflowExecutionJournal | None = None,
    ) -> None:
        if not isinstance(execution, ExecutionBoundary):
            raise TypeError("execution must be an ExecutionBoundary")
        if journal is not None and not isinstance(
            journal,
            WorkflowExecutionJournal,
        ):
            raise TypeError("journal must be a WorkflowExecutionJournal")

        self.execution = execution
        self.journal = journal or WorkflowExecutionJournal()

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

    @staticmethod
    def _fingerprint(workflow: WorkflowDefinition) -> str:
        canonical = json.dumps(
            {
                "workflow_id": workflow.workflow_id,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "command": step.command,
                        "required": step.required,
                    }
                    for step in workflow.steps
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _record_result(
        self,
        *,
        execution_id: str,
        fingerprint: str,
        result: WorkflowExecutionResult,
    ) -> WorkflowExecutionResult:
        return self.journal.record(
            execution_id=execution_id,
            fingerprint=fingerprint,
            result=result,
        )

    def execute(
        self,
        workflow: WorkflowDefinition,
        execution_id: str,
    ) -> WorkflowExecutionResult:
        self.validate(workflow)

        if not execution_id:
            raise ValueError("execution_id is required")

        fingerprint = self._fingerprint(workflow)
        recorded = self.journal.get(execution_id)

        if recorded is not None:
            recorded_fingerprint, recorded_result = recorded

            if recorded_fingerprint != fingerprint:
                raise WorkflowExecutionConflict(
                    "execution_id reused for different workflow content"
                )

            return replace(recorded_result, replayed=True)

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
                return self._record_result(
                    execution_id=execution_id,
                    fingerprint=fingerprint,
                    result=WorkflowExecutionResult(
                        workflow_id=workflow.workflow_id,
                        execution_id=execution_id,
                        status=WorkflowStatus.FAILED,
                        steps=tuple(results),
                    ),
                )

        return self._record_result(
            execution_id=execution_id,
            fingerprint=fingerprint,
            result=WorkflowExecutionResult(
                workflow_id=workflow.workflow_id,
                execution_id=execution_id,
                status=WorkflowStatus.SUCCEEDED,
                steps=tuple(results),
            ),
        )
