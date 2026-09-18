from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    task_id: str
    task_name: str
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    task_id: str
    task_name: str
    status: str
    response: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status,
            "response": self.response,
            "metadata": self.metadata,
        }


class Executor:
    """Abstract deterministic executor that invokes a backend callable and returns a result."""

    def __init__(self, backend: Callable[[ExecutionRequest], Any] | None = None) -> None:
        self.backend = backend

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be ExecutionRequest")
        if not request.task_id.strip():
            raise ValueError("task_id must not be empty")
        if not request.task_name.strip():
            raise ValueError("task_name must not be empty")

        backend = self.backend
        if backend is None:
            response = {"status": "noop"}
        else:
            response = backend(request)

        return ExecutionResult(
            task_id=request.task_id,
            task_name=request.task_name,
            status="success",
            response=response,
            metadata={"backend": backend.__name__ if backend is not None else "noop"},
        )

    def invoke_backend(self, request: ExecutionRequest) -> Any:
        if self.backend is None:
            return {"status": "noop"}
        return self.backend(request)
