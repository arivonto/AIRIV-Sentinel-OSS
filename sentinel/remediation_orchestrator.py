"""AIRIV Sentinel incident-to-remediation orchestration boundary."""

from dataclasses import dataclass
import uuid

from sentinel.execution import ExecutionBoundary, ExecutionResult
from sentinel.incidents.manager import Incident
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationDecision,
    RemediationPolicy,
    RemediationRequest,
)
from sentinel.remediation_execution_identity import (
    ExecutionIdentityRecord,
    RemediationExecutionIdentityBoundary,
    RemediationExecutionIdentityJournal,
)


@dataclass(frozen=True)
class OrchestrationResult:
    decision: RemediationDecision
    execution: ExecutionResult | None
    verification: object | None = None
    execution_id: str | None = None
    replayed: bool = False
    identity_record: ExecutionIdentityRecord | None = None


class RemediationOrchestrator:
    """Canonical controller for incident-driven remediation."""

    def __init__(
        self,
        policy: RemediationPolicy,
        gate: RemediationExecutionGate,
        verifier=None,
        identity_boundary=None,
    ) -> None:
        self.policy = policy
        self.gate = gate
        self.verifier = verifier

        if identity_boundary is None:
            identity_boundary = RemediationExecutionIdentityBoundary(
                journal=RemediationExecutionIdentityJournal(),
                gate=gate,
            )

        if not isinstance(
            identity_boundary,
            RemediationExecutionIdentityBoundary,
        ):
            raise TypeError(
                "identity_boundary must be a "
                "RemediationExecutionIdentityBoundary"
            )

        self.identity_boundary = identity_boundary

    def handle_incident(
        self,
        incident: Incident,
        action: str,
        command: str,
        execution_id: str | None = None,
        authorized_decision: RemediationDecision | None = None,
    ) -> OrchestrationResult:
        """Execute remediation against canonical Incident identity."""

        if not isinstance(incident, Incident):
            raise TypeError("incident must be a canonical Incident")

        if not incident.incident_id:
            raise ValueError("canonical incident requires incident_id")

        if not incident.component_id:
            raise ValueError("canonical incident requires component_id")

        if execution_id is None:
            execution_id = str(uuid.uuid4())

        if not execution_id:
            raise ValueError("execution_id is required")

        return self.handle(
            incident_state=incident.status,
            component_id=incident.component_id,
            action=action,
            command=command,
            execution_id=execution_id,
            incident_id=incident.incident_id,
            authorized_decision=authorized_decision,
        )

    def handle(
        self,
        incident_state: str,
        component_id: str,
        action: str,
        command: str,
        execution_id: str,
        incident_id: str,
        authorized_decision: RemediationDecision | None = None,
    ) -> OrchestrationResult:
        if not incident_id:
            raise ValueError("incident_id is required")

        if not execution_id:
            raise ValueError("execution_id is required")

        request = RemediationRequest(
            incident_state=incident_state,
            component_id=component_id,
            action=action,
        )

        if authorized_decision is None:
            decision = self.policy.evaluate(request)
        else:
            decision = authorized_decision

            if decision.action != action:
                raise ValueError(
                    "authorized decision action mismatch"
                )

            if decision.component_id != component_id:
                raise ValueError(
                    "authorized decision component mismatch"
                )

            if decision.incident_state != incident_state:
                raise ValueError(
                    "authorized decision incident state mismatch"
                )

        # Authorization MUST precede identity consumption.
        if decision.decision is not PolicyDecision.ALLOW:
            return OrchestrationResult(
                decision=decision,
                execution=None,
                execution_id=execution_id,
                replayed=False,
                identity_record=None,
            )

        execution, identity_record, replayed = (
            self.identity_boundary.execute(
                execution_id=execution_id,
                incident_id=incident_id,
                component_id=component_id,
                action=action,
                command=command,
                decision=decision,
            )
        )

        verification = None

        # A replay is not a new remediation execution.
        # Do not execute post-remediation verification again here.
        if (
            not replayed
            and execution is not None
            and execution.success
            and self.verifier is not None
        ):
            verification = self.verifier.verify()

        return OrchestrationResult(
            decision=decision,
            execution=execution,
            verification=verification,
            execution_id=execution_id,
            replayed=replayed,
            identity_record=identity_record,
        )

    # PHASE_213C1B2_BOUND_ORCHESTRATOR
    @staticmethod
    def _decision_from_bound(
        *,
        incident_state: str,
        effect,
        authorization,
    ):
        from sentinel.remediation_policy import (
            PolicyDecision,
            RemediationDecision,
        )

        return RemediationDecision(
            decision=(
                PolicyDecision.ALLOW
                if authorization.authorized
                else PolicyDecision.DENY
            ),
            reason=authorization.reason,
            incident_state=incident_state,
            component_id=effect.component_id,
            action=effect.action,
        )

    def handle_bound(
        self,
        *,
        incident_state: str,
        effect,
        authorization,
        timeout: float = 5.0,
    ):
        """Consume an already-evaluated exact bound authorization.

        This method NEVER calls RemediationPolicy.evaluate() or
        evaluate_bound(). Policy evaluation has already happened.
        """

        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
            BoundRemediationEffect,
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

        if not authorization.matches(effect):
            raise PermissionError(
                "authorization_effect_binding_mismatch"
            )

        decision = self._decision_from_bound(
            incident_state=incident_state,
            effect=effect,
            authorization=authorization,
        )

        if not authorization.authorized:
            return OrchestrationResult(
                decision=decision,
                execution=None,
                execution_id=effect.execution_id,
                replayed=False,
                identity_record=None,
            )

        execution, identity_record, replayed = (
            self.identity_boundary.execute_bound(
                effect=effect,
                authorization=authorization,
                decision=decision,
                timeout=timeout,
            )
        )

        verification = None

        if (
            not replayed
            and execution is not None
            and execution.success
            and self.verifier is not None
        ):
            verification = self.verifier.verify()

        return OrchestrationResult(
            decision=decision,
            execution=execution,
            verification=verification,
            execution_id=effect.execution_id,
            replayed=replayed,
            identity_record=identity_record,
        )

    def handle_bound_incident(
        self,
        *,
        incident,
        effect,
        authorization,
        timeout: float = 5.0,
    ):
        """Bind canonical Incident identity before any effect."""

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

        return self.handle_bound(
            incident_state=incident.status,
            effect=effect,
            authorization=authorization,
            timeout=timeout,
        )
