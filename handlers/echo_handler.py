from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    success: bool = True
    message: str = ""


def echo(message: str) -> ExecutionResult:
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    return ExecutionResult(success=True, message=message)


def echo_handler(message: str) -> ExecutionResult:
    return echo(message)


__all__ = ["ExecutionResult", "echo", "echo_handler"]
