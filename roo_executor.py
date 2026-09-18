from __future__ import annotations

from typing import Any, Callable

from executor import ExecutionRequest, ExecutionResult, Executor


class RooExecutor(Executor):
    """Executor adapter that invokes an injected Roo callable."""

    def __init__(self, roo: Callable[[ExecutionRequest], Any]) -> None:
        if not callable(roo):
            raise TypeError("roo must be callable")
        super().__init__(backend=roo)

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return super().execute(request)


__all__ = ["RooExecutor"]
