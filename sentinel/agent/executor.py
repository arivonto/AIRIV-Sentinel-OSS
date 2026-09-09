"""Compatibility surface for AIRIV Sentinel AI agent execution V1.

The canonical implementation authority lives in ``sentinel.ai_agent_execution``.
This module preserves the earlier import surface while routing every adapter
invocation through ``AgentExecutionBoundary``. It owns no separate AI execution
authority, remediation authority, lifecycle authority, or verification authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from sentinel.ai_agent_execution import (
    AgentExecutionBoundary,
    AgentExecutionStatus,
    AgentRequest,
    RawAgentResult,
)


# Backward-compatible names. Validation is now owned by AgentRequest.
AgentExecutionError = ValueError
AgentExecutionRequest = AgentRequest


@dataclass(frozen=True)
class AgentExecutionResult:
    """Legacy-shaped observable result projected from the canonical boundary."""

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


class _LegacyAdapterBridge:
    """Adapt a legacy output-only resource to the canonical raw-result protocol."""

    name = "LEGACY_COMPAT"
    enabled = True

    def __init__(self, adapter: AgentAdapter) -> None:
        self._adapter = adapter

    def execute(self, request: AgentRequest) -> RawAgentResult:
        started_at = datetime.now(timezone.utc)
        output = self._adapter.execute(request)
        completed_at = datetime.now(timezone.utc)
        return RawAgentResult(
            request_id=request.request_id,
            agent_id=request.agent_id,
            task_id=request.task_id,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            output=output,
            execution_status=AgentExecutionStatus.SUCCEEDED,
        )


class AIAgentExecutionBoundary:
    """Backward-compatible facade over the single canonical AI boundary.

    ``success`` below means only that the AI execution resource returned a
    successful terminal execution result. It does not mean Sentinel accepted
    the output, authorized an effect, or verified resulting system state.
    """

    def __init__(self, adapter: AgentAdapter) -> None:
        if not callable(getattr(adapter, "execute", None)):
            raise TypeError("adapter must provide callable execute()")
        self.adapter = adapter
        self._boundary = AgentExecutionBoundary(
            adapter=_LegacyAdapterBridge(adapter)
        )

    @staticmethod
    def validate(request: AgentExecutionRequest) -> None:
        if not isinstance(request, AgentRequest):
            raise TypeError("request must be an AgentExecutionRequest")

    @property
    def evidence_records(self):
        """Read-only canonical execution evidence accumulated by this facade."""

        return self._boundary.evidence_trail.records

    def execute(
        self,
        request: AgentExecutionRequest,
    ) -> AgentExecutionResult:
        self.validate(request)
        boundary_started_at = datetime.now(timezone.utc)
        outcome = self._boundary.execute(request)

        if outcome.raw_result is not None:
            raw = outcome.raw_result
            snapshot = raw.to_dict()
            return AgentExecutionResult(
                request_id=raw.request_id,
                agent_id=raw.agent_id,
                task_id=raw.task_id,
                started_at=datetime.fromisoformat(raw.started_at),
                finished_at=datetime.fromisoformat(raw.completed_at),
                output=snapshot["output"],
                success=(
                    raw.execution_status == AgentExecutionStatus.SUCCEEDED
                ),
                status=raw.execution_status,
            )

        error_type = "AgentExecutionError"
        if outcome.boundary_error_code and ":" in outcome.boundary_error_code:
            error_type = outcome.boundary_error_code.rsplit(":", 1)[-1]

        return AgentExecutionResult(
            request_id=request.request_id,
            agent_id=request.agent_id,
            task_id=request.task_id,
            started_at=boundary_started_at,
            finished_at=datetime.now(timezone.utc),
            output={
                "error_type": error_type,
                "error": "AI agent execution failed.",
            },
            success=False,
            status=AgentExecutionStatus.FAILED,
        )
