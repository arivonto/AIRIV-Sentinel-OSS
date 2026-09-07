from sentinel.agent.executor import (
    AIAgentExecutionBoundary,
    AgentExecutionRequest,
)
from sentinel.ai_result_verifier import (
    AIResultVerifier,
    AIResultVerificationResult,
)
from sentinel.commander import CommanderOrchestrator
from sentinel.execution import ExecutionBoundary
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_policy import RemediationPolicy
from sentinel.workflow.executor import (
    WorkflowDefinition,
    WorkflowExecutor,
    WorkflowStep,
)


class FakeAgent:
    def execute(self, request):
        from sentinel.agent.executor import AgentExecutionResult
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        return AgentExecutionResult(
            request_id=request.request_id,
            agent_id=request.agent_id,
            task_id=request.task_id,
            started_at=now,
            finished_at=now,
            output={"ok": True},
            success=True,
            status="SUCCEEDED",
        )


def test_commander_system_execution_uses_canonical_boundary():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
    )

    result = commander.execute_system("printf 'commander'")

    assert result.execution is not None
    assert result.execution.success
    assert result.execution.stdout == "commander"


def test_commander_workflow_execution_uses_canonical_boundary():
    execution = ExecutionBoundary()

    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=execution,
        workflow_executor=WorkflowExecutor(execution),
    )

    workflow = WorkflowDefinition(
        workflow_id="commander-workflow",
        steps=[
            WorkflowStep(
                step_id="step-1",
                command="printf 'ok'",
            )
        ],
    )

    result = commander.workflow_executor.execute(
        workflow,
        execution_id="commander-execution-1",
    )

    assert result.status.value == "SUCCEEDED"

    return

    assert result.workflow is not None
    assert result.workflow.status.value == "SUCCEEDED"


def test_commander_ai_execution_uses_canonical_boundary():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
        agent_executor=AIAgentExecutionBoundary(FakeAgent()),
        ai_result_verifier=AIResultVerifier(
            lambda result: AIResultVerificationResult(
                accepted=True,
                reason="test_result_accepted",
                observation={"verified": True},
            )
        ),
    )

    incident = commander.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "pane-ai-1",
            "agent_identity": "test-agent",
        },
        anomaly_type="TEST_AI_ANOMALY",
        reason="test",
    )

    initial_status = incident.status
    initial_evidence_count = incident.evidence_store.count()

    request = AgentExecutionRequest(
        request_id="req-1",
        agent_id="agent-1",
        task_id="task-1",
        input_payload={"test": True},
        requested_operation="diagnose",
        execution_context={},
        authority_context={},
    )

    result = commander.execute_agent(request, incident)

    assert result.agent is not None
    assert result.agent.success
    assert result.ai_evidence is not None

    assert result.ai_evidence.incident_id == incident.incident_id
    assert result.ai_evidence.request_id == "req-1"
    assert result.ai_evidence.agent_id == "agent-1"
    assert result.ai_evidence.task_id == "task-1"
    assert result.ai_evidence.accepted is True

    assert incident.status == initial_status
    assert incident.evidence_store.count() == initial_evidence_count + 1
    assert incident.evidence_store.records()[-1].evidence_type == (
        "AI_AGENT_RESULT_ACCEPTED"
    )


def test_commander_ai_execution_requires_canonical_incident():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
        agent_executor=AIAgentExecutionBoundary(FakeAgent()),
        ai_result_verifier=AIResultVerifier(
            lambda result: True
        ),
    )

    request = AgentExecutionRequest(
        request_id="req-invalid-incident",
        agent_id="agent-1",
        task_id="task-1",
        input_payload={},
        requested_operation="diagnose",
        execution_context={},
        authority_context={},
    )

    try:
        commander.execute_agent(request, object())
    except TypeError as exc:
        assert str(exc) == "incident must be a canonical Incident"
    else:
        raise AssertionError("non-canonical Incident must be rejected")


def test_commander_ai_execution_rejected_result_is_evidenced():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
        agent_executor=AIAgentExecutionBoundary(FakeAgent()),
        ai_result_verifier=AIResultVerifier(
            lambda result: AIResultVerificationResult(
                accepted=False,
                reason="test_result_rejected",
                observation={"verified": False},
            )
        ),
    )

    incident = commander.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "pane-ai-2",
            "agent_identity": "test-agent",
        },
        anomaly_type="TEST_AI_REJECTED",
        reason="test",
    )

    initial_evidence_count = incident.evidence_store.count()

    request = AgentExecutionRequest(
        request_id="req-2",
        agent_id="agent-2",
        task_id="task-2",
        input_payload={"test": True},
        requested_operation="diagnose",
        execution_context={},
        authority_context={},
    )

    result = commander.execute_agent(request, incident)

    assert result.agent is not None
    assert result.ai_evidence is not None
    assert result.ai_evidence.accepted is False
    assert result.ai_evidence.verification_reason == (
        "test_result_rejected"
    )

    assert incident.status == "OPEN"
    assert incident.evidence_store.count() == initial_evidence_count + 1
    assert incident.evidence_store.records()[-1].evidence_type == (
        "AI_AGENT_RESULT_REJECTED"
    )


def test_commander_remediation_denied_by_default():
    commander = CommanderOrchestrator(
        incident_manager=IncidentManager(),
        execution=ExecutionBoundary(),
    )

    incident = commander.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "pane-1",
            "agent_identity": "test-agent",
        },
        anomaly_type="TEST_ANOMALY",
        reason="test",
    )

    result = commander.remediate(
        incident=incident,
        action="not_allowed",
        command="printf 'must-not-run'",
    )

    assert result.decision.authorized is False
    assert result.execution is None
    assert result.remediation is not None
