"""Execution result to evidence normalization boundary."""

from dataclasses import dataclass

from sentinel.execution import ExecutionResult


@dataclass(frozen=True)
class ExecutionEvidence:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    success: bool
    started_at: float
    finished_at: float

    @classmethod
    def from_result(cls, result: ExecutionResult) -> "ExecutionEvidence":
        return cls(
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            success=result.success,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
