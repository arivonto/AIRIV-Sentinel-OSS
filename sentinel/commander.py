"""AIRIV Sentinel canonical Commander orchestration boundary."""

from dataclasses import dataclass
from typing import Any, Callable

from sentinel.agent.executor import (
    AIAgentExecutionBoundary,
    AgentExecutionRequest,
    AgentExecutionResult,
)
from sentinel.ai_agent_evidence_flow import (
    AIAgentEvidenceFlow,
    AIAgentEvidenceRecord,
)
from sentinel.ai_result_verifier import (
    AIResultVerifier,
    AIResultVerificationResult,
)
from sentinel.execution import ExecutionBoundary, ExecutionResult
from sentinel.incidents.manager import Incident, IncidentManager
from sentinel.remediation_evidence_flow import (
    EvidenceCompleteRemediationFlow,
    RemediationEvidenceRecord,
)
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationPolicy,
)
from sentinel.remediation_orchestrator import (
    OrchestrationResult,
    RemediationOrchestrator,
)
from sentinel.workflow.executor import (
    WorkflowDefinition,
    WorkflowExecutionResult,
    WorkflowExecutor,
)


@dataclass(frozen=True)
class CommanderDecision:
    action: str
    reason: str
    authorized: bool


@dataclass(frozen=True)
class CommanderResult:
    decision: CommanderDecision
    execution: ExecutionResult | None = None
    workflow: WorkflowExecutionResult | None = None
    agent: AgentExecutionResult | None = None
    ai_evidence: AIAgentEvidenceRecord | None = None
    remediation: RemediationEvidenceRecord | None = None


class CommanderOrchestrator:
    """Compose canonical Sentinel boundaries without duplicating authority."""

    def __init__(
        self,
        incident_manager: IncidentManager,
        execution: ExecutionBoundary,
        workflow_executor: WorkflowExecutor | None = None,
        agent_executor: AIAgentExecutionBoundary | None = None,
        remediation_policy: RemediationPolicy | None = None,
        ai_result_verifier: AIResultVerifier | None = None,
        ai_evidence_flow: AIAgentEvidenceFlow | None = None,
    ) -> None:
        if not isinstance(incident_manager, IncidentManager):
            raise TypeError("incident_manager must be an IncidentManager")

        if not isinstance(execution, ExecutionBoundary):
            raise TypeError("execution must be an ExecutionBoundary")

        if workflow_executor is not None and not isinstance(
            workflow_executor,
            WorkflowExecutor,
        ):
            raise TypeError(
                "workflow_executor must be a WorkflowExecutor or None"
            )

        if agent_executor is not None and not isinstance(
            agent_executor,
            AIAgentExecutionBoundary,
        ):
            raise TypeError(
                "agent_executor must be an AIAgentExecutionBoundary or None"
            )

        if ai_result_verifier is not None and not isinstance(
            ai_result_verifier,
            AIResultVerifier,
        ):
            raise TypeError(
                "ai_result_verifier must be an AIResultVerifier or None"
            )

        if ai_evidence_flow is not None and not isinstance(
            ai_evidence_flow,
            AIAgentEvidenceFlow,
        ):
            raise TypeError(
                "ai_evidence_flow must be an AIAgentEvidenceFlow or None"
            )

        if remediation_policy is None:
            remediation_policy = RemediationPolicy(
                allowed_actions=set()
            )

        if not isinstance(remediation_policy, RemediationPolicy):
            raise TypeError(
                "remediation_policy must be a RemediationPolicy"
            )

        self.incident_manager = incident_manager
        self.execution = execution
        self.workflow_executor = workflow_executor
        self.agent_executor = agent_executor
        self.remediation_policy = remediation_policy
        self.ai_result_verifier = ai_result_verifier
        self.ai_evidence_flow = (
            ai_evidence_flow
            if ai_evidence_flow is not None
            else AIAgentEvidenceFlow()
        )

        self.remediation_gate = RemediationExecutionGate(
            self.execution
        )

        self.remediation_orchestrator = RemediationOrchestrator(
            policy=self.remediation_policy,
            gate=self.remediation_gate,
        )

        self.remediation_flow = EvidenceCompleteRemediationFlow()

    def execute_system(
        self,
        command: str,
    ) -> CommanderResult:
        """Execute system work exclusively through ExecutionBoundary."""

        if not command or not command.strip():
            raise ValueError("command must not be empty")

        decision = CommanderDecision(
            action="system_execution",
            reason="system execution requested",
            authorized=True,
        )

        result = self.execution.execute(command)

        return CommanderResult(
            decision=decision,
            execution=result,
        )

    def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        execution_id: str,
    ) -> CommanderResult:
        """Execute a workflow exclusively through WorkflowExecutor."""

        if self.workflow_executor is None:
            raise RuntimeError(
                "workflow execution boundary is not configured"
            )

        if not execution_id:
            raise ValueError("execution_id is required")

        result = self.workflow_executor.execute(
            workflow,
            execution_id,
        )

        decision = CommanderDecision(
            action="workflow_execution",
            reason="workflow execution requested",
            authorized=True,
        )

        return CommanderResult(
            decision=decision,
            workflow=result,
        )

    def execute_agent(
        self,
        request: AgentExecutionRequest,
        incident: Incident,
    ) -> CommanderResult:
        """Execute, verify, and evidence an AI agent against an Incident."""

        if self.agent_executor is None:
            raise RuntimeError(
                "AI agent execution boundary is not configured"
            )

        if not isinstance(incident, Incident):
            raise TypeError(
                "incident must be a canonical Incident"
            )

        if not incident.incident_id:
            raise ValueError("incident must have an incident_id")

        if self.ai_result_verifier is None:
            raise RuntimeError(
                "AI result verification boundary is not configured"
            )

        result = self.agent_executor.execute(request)

        verification = self.ai_result_verifier.verify(result)

        _, ai_evidence = self.ai_evidence_flow.finalize(
            incident=incident,
            result=result,
            verification=verification,
        )

        decision = CommanderDecision(
            action="ai_agent_execution",
            reason="AI agent execution requested",
            authorized=True,
        )

        return CommanderResult(
            decision=decision,
            agent=result,
            ai_evidence=ai_evidence,
        )

    def decide_remediation(
        self,
        incident: Incident,
        action: str,
    ) -> CommanderDecision:
        """Ask the canonical remediation policy for authorization."""

        if not isinstance(incident, Incident):
            raise TypeError("incident must be a canonical Incident")

        if not incident.incident_id:
            raise ValueError("incident must have an incident_id")

        if not incident.component_id:
            raise ValueError("incident must have a component_id")

        request = self.remediation_orchestrator.policy.evaluate

        policy_result = request(
            self._remediation_request(
                incident=incident,
                action=action,
            )
        )

        return CommanderDecision(
            action=action,
            reason=policy_result.reason,
            authorized=policy_result.decision is PolicyDecision.ALLOW,
        )

    def remediate(
        self,
        incident: Incident,
        action: str,
        command: str,
        execution_id: str | None = None,
        verifier: Callable[[], Any] | None = None,
        decision: CommanderDecision | None = None,
    ) -> CommanderResult:
        """Coordinate remediation through the canonical decision.

        When a decision is supplied, it MUST be the decision produced
        by the preceding Commander decision boundary. This prevents
        policy evaluation from being repeated during execution.

        When no decision is supplied, Commander performs the canonical
        decision itself before execution. This preserves the direct
        Commander API while maintaining exactly one policy evaluation.
        """

        if not isinstance(incident, Incident):
            raise TypeError("incident must be a canonical Incident")

        if not incident.incident_id:
            raise ValueError("incident must have an incident_id")

        if not incident.component_id:
            raise ValueError("incident must have a component_id")

        if not action or not action.strip():
            raise ValueError("action must not be empty")

        if not command or not command.strip():
            raise ValueError("command must not be empty")

        if execution_id is None:
            import uuid

            execution_id = str(uuid.uuid4())

        if not execution_id or not execution_id.strip():
            raise ValueError("execution_id is required")

        if decision is None:
            decision = self.decide_remediation(
                incident=incident,
                action=action,
            )

        if not decision.authorized:
            _incident, evidence = self.remediation_flow.finalize(
                incident,
                OrchestrationResult(
                    decision=self._policy_decision_from_commander(
                        incident=incident,
                        decision=decision,
                    ),
                    execution=None,
                    execution_id=execution_id,
                    replayed=False,
                    identity_record=None,
                ),
            )

            return CommanderResult(
                decision=decision,
                execution=None,
                remediation=evidence,
            )

        original_verifier = self.remediation_orchestrator.verifier

        if verifier is not None:
            from sentinel.remediation_verifier import RemediationVerifier

            self.remediation_orchestrator.verifier = RemediationVerifier(
                verifier
            )

        try:
            result = self.remediation_orchestrator.handle_incident(
                incident=incident,
                action=action,
                command=command,
                execution_id=execution_id,
                authorized_decision=self._policy_decision_from_commander(
                    incident=incident,
                    decision=decision,
                ),
            )
        finally:
            self.remediation_orchestrator.verifier = original_verifier

        _incident, evidence = self.remediation_flow.finalize(
            incident,
            result,
        )

        decision = CommanderDecision(
            action=action,
            reason=result.decision.reason,
            authorized=(
                result.decision.decision is PolicyDecision.ALLOW
            ),
        )

        return CommanderResult(
            decision=decision,
            execution=result.execution,
            remediation=evidence,
        )

    @staticmethod
    def _policy_decision_from_commander(
        incident: Incident,
        decision: CommanderDecision,
    ):
        from sentinel.remediation_policy import RemediationDecision

        return RemediationDecision(
            decision=(
                PolicyDecision.ALLOW
                if decision.authorized
                else PolicyDecision.DENY
            ),
            reason=decision.reason,
            incident_state=incident.status,
            component_id=incident.component_id,
            action=decision.action,
        )

    @staticmethod
    def _remediation_request(
        incident: Incident,
        action: str,
    ):
        from sentinel.remediation_policy import RemediationRequest

        return RemediationRequest(
            incident_state=incident.status,
            component_id=incident.component_id,
            action=action,
        )

    # PHASE_213C1B2_BOUND_COMMANDER
    def decide_bound_remediation(
        self,
        *,
        incident,
        effect,
    ):
        """Perform the sole policy evaluation for one exact effect."""

        from sentinel.incidents.manager import Incident
        from sentinel.live_remediation_safety import (
            BoundRemediationEffect,
        )

        if not isinstance(incident, Incident):
            raise TypeError(
                "incident must be a canonical Incident"
            )

        if not isinstance(effect, BoundRemediationEffect):
            raise TypeError(
                "effect must be a BoundRemediationEffect"
            )

        if incident.incident_id != effect.incident_id:
            raise ValueError(
                "bound incident_id mismatch"
            )

        if incident.component_id != effect.component_id:
            raise ValueError(
                "bound component_id mismatch"
            )

        return self.remediation_orchestrator.policy.evaluate_bound(
            incident_state=incident.status,
            effect=effect,
        )

    def remediate_bound(
        self,
        *,
        incident,
        effect,
        authorization,
        verifier=None,
        timeout: float = 5.0,
    ):
        """Execute exactly the effect authorized by policy.

        No command or execution ID may be substituted at this API.
        """

        from sentinel.incidents.manager import Incident
        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
            BoundRemediationEffect,
        )
        from sentinel.remediation_policy import PolicyDecision

        if not isinstance(incident, Incident):
            raise TypeError(
                "incident must be a canonical Incident"
            )

        if not isinstance(effect, BoundRemediationEffect):
            raise TypeError(
                "effect must be a BoundRemediationEffect"
            )

        if not isinstance(
            authorization,
            BoundRemediationAuthorization,
        ):
            raise TypeError(
                "authorization must be a "
                "BoundRemediationAuthorization"
            )

        if incident.incident_id != effect.incident_id:
            raise ValueError(
                "bound incident_id mismatch"
            )

        if incident.component_id != effect.component_id:
            raise ValueError(
                "bound component_id mismatch"
            )

        if not authorization.matches(effect):
            raise PermissionError(
                "authorization_effect_binding_mismatch"
            )

        decision = CommanderDecision(
            action=effect.action,
            reason=authorization.reason,
            authorized=authorization.authorized,
        )

        translated = (
            self.remediation_orchestrator
            ._decision_from_bound(
                incident_state=incident.status,
                effect=effect,
                authorization=authorization,
            )
        )

        if not authorization.authorized:
            _incident, evidence = self.remediation_flow.finalize(
                incident,
                OrchestrationResult(
                    decision=translated,
                    execution=None,
                    execution_id=effect.execution_id,
                    replayed=False,
                    identity_record=None,
                ),
            )

            return CommanderResult(
                decision=decision,
                execution=None,
                remediation=evidence,
            )

        original_verifier = (
            self.remediation_orchestrator.verifier
        )

        if verifier is not None:
            from sentinel.remediation_verifier import (
                RemediationVerifier,
            )

            self.remediation_orchestrator.verifier = (
                RemediationVerifier(verifier)
            )

        try:
            result = (
                self.remediation_orchestrator
                .handle_bound_incident(
                    incident=incident,
                    effect=effect,
                    authorization=authorization,
                    timeout=timeout,
                )
            )
        finally:
            self.remediation_orchestrator.verifier = (
                original_verifier
            )

        _incident, evidence = self.remediation_flow.finalize(
            incident,
            result,
        )

        decision = CommanderDecision(
            action=effect.action,
            reason=result.decision.reason,
            authorized=(
                result.decision.decision
                is PolicyDecision.ALLOW
            ),
        )

        return CommanderResult(
            decision=decision,
            execution=result.execution,
            remediation=evidence,
        )
