import pytest

from sentinel.agent.executor import (
    AIAgentExecutionBoundary,
    AgentExecutionError,
    AgentExecutionRequest,
)
from sentinel.ai_agent_execution import AgentExecutionBoundary


class StubAgent:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.output


class FailingAgent:
    def execute(self, request):
        raise RuntimeError("provider detail must not escape")


def make_request():
    return AgentExecutionRequest(
        request_id="req-001",
        agent_id="agent-test",
        task_id="task-001",
        input_payload={"observation": "test"},
        requested_operation="diagnose",
        execution_context={"mode": "test"},
        authority_context={"level": "L1"},
    )


def test_legacy_surface_routes_through_canonical_boundary():
    boundary = AIAgentExecutionBoundary(StubAgent("diagnosis"))

    assert isinstance(boundary._boundary, AgentExecutionBoundary)

    result = boundary.execute(make_request())

    assert result.success is True
    assert len(boundary.evidence_records) == 1
    assert boundary.evidence_records[0].verification_accepted is False


def test_agent_execution_returns_observable_result():
    adapter = StubAgent({"diagnosis": "test"})
    boundary = AIAgentExecutionBoundary(adapter)

    result = boundary.execute(make_request())

    assert result.success is True
    assert result.request_id == "req-001"
    assert result.agent_id == "agent-test"
    assert result.task_id == "task-001"
    assert result.output == {"diagnosis": "test"}
    assert result.started_at <= result.finished_at
    assert adapter.requests == [make_request()]


def test_agent_failure_is_not_reported_as_success_or_raw_exception_text():
    boundary = AIAgentExecutionBoundary(FailingAgent())

    result = boundary.execute(make_request())

    assert result.success is False
    assert result.status == "FAILED"
    assert result.output["error_type"] == "RuntimeError"
    assert result.output["error"] == "AI agent execution failed."
    assert "provider detail" not in str(result.output)
    assert len(boundary.evidence_records) == 1
    assert boundary.evidence_records[0].verification_accepted is False


def test_missing_execution_identity_is_rejected_at_canonical_request_boundary():
    with pytest.raises(AgentExecutionError):
        AgentExecutionRequest(
            request_id="",
            agent_id="agent-test",
            task_id="task-001",
            input_payload={},
            requested_operation="diagnose",
            execution_context={},
            authority_context={},
        )


def test_agent_output_is_returned_without_becoming_sentinel_state():
    adapter = StubAgent(
        {
            "action": "restart_service",
            "status": "RESOLVED",
        }
    )
    boundary = AIAgentExecutionBoundary(adapter)

    result = boundary.execute(make_request())

    assert result.success is True
    assert result.output["status"] == "RESOLVED"
    assert not hasattr(result, "incident_status")
    assert not hasattr(result, "verification")
    assert not hasattr(result, "remediation_authorized")


def test_authority_context_is_explicit_and_immutable():
    adapter = StubAgent("diagnosis")
    boundary = AIAgentExecutionBoundary(adapter)
    request = make_request()

    boundary.execute(request)

    assert dict(adapter.requests[0].authority_context) == {"level": "L1"}
    with pytest.raises(TypeError):
        adapter.requests[0].authority_context["level"] = "self-granted"
