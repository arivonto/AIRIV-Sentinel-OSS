"""Canonical provider-agnostic AI agent execution boundary V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


class AgentExecutionError(ValueError):
    """Raised when an AI agent execution request is invalid."""


@dataclass(frozen=True)
class AgentExecutionRequest:
    request_id: str
    agent_id: str
    task_id: str
    input_payload: Any
    requested_operation: str
    execution_context: Any
    authority_context: Any


@dataclass(frozen=True)
class AgentExecutionResult:
    request_id: str
    agent_id: str
    task_id: str
    started_at: datetime
    finished_at: datetime
    output: Any
    success: bool
    status: str


class AgentAdapter(Protocol):
    def execute(self, request: AgentExecutionRequest) -> Any:
        ...


class AIAgentExecutionBoundary:
    """Execute an AI agent only through an explicit adapter boundary."""

    def __init__(self, adapter: AgentAdapter) -> None:
        if not callable(getattr(adapter, "execute", None)):
            raise TypeError("adapter must provide callable execute()")
        self.adapter = adapter

    @staticmethod
    def validate(request: AgentExecutionRequest) -> None:
        if not isinstance(request, AgentExecutionRequest):
            raise TypeError("request must be an AgentExecutionRequest")

        required = {
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "task_id": request.task_id,
            "requested_operation": request.requested_operation,
        }

        for field, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise AgentExecutionError(f"{field} is required")

    def execute(
        self,
        request: AgentExecutionRequest,
    ) -> AgentExecutionResult:
        self.validate(request)

        started_at = datetime.now(timezone.utc)

        try:
            output = self.adapter.execute(request)
            success = True
            status = "SUCCEEDED"
        except Exception as exc:
            output = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            success = False
            status = "FAILED"

        finished_at = datetime.now(timezone.utc)

        return AgentExecutionResult(
            request_id=request.request_id,
            agent_id=request.agent_id,
            task_id=request.task_id,
            started_at=started_at,
            finished_at=finished_at,
            output=output,
            success=success,
            status=status,
        )
