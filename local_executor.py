from __future__ import annotations

from typing import Any, Callable

from executor import ExecutionRequest, ExecutionResult, Executor


class LocalExecutor(Executor):
    """Concrete executor that runs deterministic local Python task handlers."""

    def __init__(self) -> None:
        super().__init__()
        self._handlers: dict[str, Callable[[ExecutionRequest], Any]] = {}

    def register_handler(self, task_type: str, handler: Callable[[ExecutionRequest], Any]) -> None:
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[task_type] = handler

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be ExecutionRequest")

        task_type = str(request.payload.get("task_type", "")) if isinstance(request.payload, dict) else ""
        if not task_type:
            return super().execute(request)
        handler = self._handlers.get(task_type)
        if handler is None:
            return ExecutionResult(
                task_id=request.task_id,
                task_name=request.task_name,
                status="FAIL",
                response={"error": f"unknown task type: {task_type or 'missing'}"},
                metadata={"task_type": task_type},
            )

        try:
            response = handler(request)
            return ExecutionResult(
                task_id=request.task_id,
                task_name=request.task_name,
                status="success",
                response=response,
                metadata={"task_type": task_type},
            )
        except Exception as exc:  # pragma: no cover - explicit fail path for local handler errors
            return ExecutionResult(
                task_id=request.task_id,
                task_name=request.task_name,
                status="FAIL",
                response={"error": str(exc)},
                metadata={"task_type": task_type},
            )
