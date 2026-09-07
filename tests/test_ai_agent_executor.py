from sentinel.agent.executor import (
    AIAgentExecutionBoundary,
    AgentExecutionError,
    AgentExecutionRequest,
)


class StubAgent:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.output


class FailingAgent:
    def execute(self, request):
        raise RuntimeError("agent unavailable")


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


def test_agent_failure_is_not_reported_as_success():
    boundary = AIAgentExecutionBoundary(FailingAgent())

    result = boundary.execute(make_request())

    assert result.success is False
    assert result.output["error_type"] == "RuntimeError"
    assert "agent unavailable" in result.output["error"]


def test_missing_execution_identity_is_rejected():
    boundary = AIAgentExecutionBoundary(StubAgent("ok"))

    request = AgentExecutionRequest(
        request_id="",
        agent_id="agent-test",
        task_id="task-001",
        input_payload={},
        requested_operation="diagnose",
        execution_context={},
        authority_context={},
    )

    try:
        boundary.execute(request)
    except AgentExecutionError:
        pass
    else:
        raise AssertionError("missing request_id was not rejected")


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


def test_authority_context_is_explicit():
    adapter = StubAgent("diagnosis")

    boundary = AIAgentExecutionBoundary(adapter)
    request = make_request()

    boundary.execute(request)

    assert adapter.requests[0].authority_context == {"level": "L1"}
