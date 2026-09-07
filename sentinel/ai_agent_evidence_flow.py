"""AIRIV Sentinel canonical AI agent evidence integration V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sentinel.agent.executor import AgentExecutionResult
from sentinel.ai_result_verifier import AIResultVerificationResult
from sentinel.incidents.manager import Incident


@dataclass(frozen=True)
class AIAgentEvidenceRecord:
    """Immutable audit representation of one AI execution."""

    incident_id: str
    component_id: str
    request_id: str
    agent_id: str
    task_id: str
    started_at: Any
    finished_at: Any
    status: str
    success: bool
    output: Any
    accepted: bool
    verification_reason: str
    verification_observation: Any


class AIAgentEvidenceFlow:
    """
    Sentinel-owned integration from AI execution to canonical evidence.

    The AI boundary never writes evidence directly.
    """

    def finalize(
        self,
        incident: Incident,
        result: AgentExecutionResult,
        verification: AIResultVerificationResult,
    ) -> tuple[Incident, AIAgentEvidenceRecord]:
        if not isinstance(incident, Incident):
            raise TypeError(
                "incident must be a canonical Incident"
            )

        if not isinstance(result, AgentExecutionResult):
            raise TypeError(
                "result must be an AgentExecutionResult"
            )

        if not isinstance(
            verification,
            AIResultVerificationResult,
        ):
            raise TypeError(
                "verification must be an "
                "AIResultVerificationResult"
            )

        signal = {
            "request_id": result.request_id,
            "agent_id": result.agent_id,
            "task_id": result.task_id,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "status": result.status,
            "success": result.success,
            "output": result.output,
            "accepted": verification.accepted,
            "verification_reason": verification.reason,
            "verification_observation": (
                verification.observation
            ),
        }

        if not result.success:
            signal_type = "AI_AGENT_EXECUTION_FAILED"
            reason = "AI agent execution failed."

        elif verification.accepted:
            signal_type = "AI_AGENT_RESULT_ACCEPTED"
            reason = (
                "AI agent execution completed and "
                "Sentinel accepted the result."
            )

        else:
            signal_type = "AI_AGENT_RESULT_REJECTED"
            reason = (
                "AI agent execution completed but "
                "Sentinel rejected the result."
            )

        incident.add_evidence(
            observation={
                "agent_identity": result.agent_id,
            },
            reason=reason,
            signal_type=signal_type,
            signal=signal,
        )

        evidence = AIAgentEvidenceRecord(
            incident_id=incident.incident_id,
            component_id=incident.component_id,
            request_id=result.request_id,
            agent_id=result.agent_id,
            task_id=result.task_id,
            started_at=result.started_at,
            finished_at=result.finished_at,
            status=result.status,
            success=result.success,
            output=result.output,
            accepted=verification.accepted,
            verification_reason=verification.reason,
            verification_observation=(
                verification.observation
            ),
        )

        return incident, evidence
