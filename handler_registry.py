from __future__ import annotations

from typing import Any, Callable


class HandlerRegistry:
    """Deterministic registry for local task handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, task_type: str, handler: Callable[..., Any]) -> None:
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if task_type in self._handlers:
            raise ValueError(f"handler already registered for task type: {task_type}")
        self._handlers[task_type] = handler

    def unregister(self, task_type: str) -> Callable[..., Any]:
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        if task_type not in self._handlers:
            raise KeyError(f"unknown task type: {task_type}")
        return self._handlers.pop(task_type)

    def get(self, task_type: str) -> Callable[..., Any]:
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        if task_type not in self._handlers:
            raise KeyError(f"unknown task type: {task_type}")
        return self._handlers[task_type]

    def list_handlers(self) -> list[str]:
        return sorted(self._handlers.keys())
