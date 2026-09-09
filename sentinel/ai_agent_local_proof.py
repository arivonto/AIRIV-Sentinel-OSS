"""Deterministic no-network AI execution resource for contract proof only.

This adapter is disabled by default and cannot execute commands, mutate Incident
state, authorize remediation, or contact a model provider. Its independent
verifier recomputes the expected deterministic proof from the canonical request.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sentinel.ai_agent_execution import (
    AgentExecutionStatus,
    AgentRequest,
    AgentVerificationDecision,
    RawAgentResult,
)
from sentinel.ai_agent_identity import fingerprint_agent_request


_PROOF_VERSION = "AIRIV_SENTINEL_AI_LOCAL_PROOF_V1"


class DeterministicLocalAgentAdapter:
    name = "DETERMINISTIC_LOCAL_PROOF"

    def __init__(self, *, enabled: bool = False) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be boolean")
        self.enabled = enabled
        self.execution_count = 0

    def execute(self, request: AgentRequest) -> RawAgentResult:
        if self.enabled is not True:
            raise RuntimeError("deterministic local AI adapter is disabled")
        if not isinstance(request, AgentRequest):
            raise TypeError("request must be an AgentRequest")

        started_at = datetime.now(timezone.utc)
        request_sha256 = fingerprint_agent_request(request)
        output = {
            "proof_version": _PROOF_VERSION,
            "request_sha256": request_sha256,
            "requested_operation": request.requested_operation,
            "proposal_only": True,
        }
        self.execution_count += 1
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


class DeterministicLocalAgentVerifier:
    """Independent verifier for the deterministic no-network proof payload."""

    def verify(
        self,
        request: AgentRequest,
        result: RawAgentResult,
    ) -> AgentVerificationDecision:
        if not isinstance(request, AgentRequest):
            raise TypeError("request must be an AgentRequest")
        if not isinstance(result, RawAgentResult):
            raise TypeError("result must be a RawAgentResult")

        expected = {
            "proof_version": _PROOF_VERSION,
            "request_sha256": fingerprint_agent_request(request),
            "requested_operation": request.requested_operation,
            "proposal_only": True,
        }
        actual = result.to_dict()["output"]
        if result.execution_status != AgentExecutionStatus.SUCCEEDED:
            return AgentVerificationDecision(False, "LOCAL_PROOF_NOT_SUCCEEDED")
        if actual != expected:
            return AgentVerificationDecision(False, "LOCAL_PROOF_MISMATCH")
        return AgentVerificationDecision(True, "LOCAL_PROOF_VERIFIED")
