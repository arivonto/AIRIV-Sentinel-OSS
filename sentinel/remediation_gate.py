"""AIRIV Sentinel remediation-to-execution authorization gate."""

from sentinel.bound_effect_contract import (
    bound_effect_policy_run_id,
    bound_effect_target_fingerprint,
    validate_bound_effect_contract,
)


from dataclasses import dataclass

from sentinel.execution import ExecutionBoundary, ExecutionResult
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationDecision,
)


@dataclass(frozen=True)
class RemediationExecutionResult:
    decision: RemediationDecision
    execution: ExecutionResult | None


class RemediationExecutionGate:
    """Allows execution only after an explicit ALLOW decision."""

    def __init__(self, executor: ExecutionBoundary) -> None:
        self.executor = executor

    def execute(
        self,
        decision: RemediationDecision,
        command: str,
    ) -> RemediationExecutionResult:

        if decision.decision is not PolicyDecision.ALLOW:
            return RemediationExecutionResult(
                decision=decision,
                execution=None,
            )

        result = self.executor.execute(command)

        return RemediationExecutionResult(
            decision=decision,
            execution=result,
        )

    # PHASE_213C1B2_BOUND_GATE
    def execute_bound(
        self,
        *,
        decision,
        effect,
        authorization,
        timeout: float = 5.0,
    ):
        """Execute only an exactly authorized immutable effect."""

        from sentinel.live_remediation_safety import (
            BoundRemediationAuthorization,
            BoundRemediationEffect,
        )
        from sentinel.remediation_policy import PolicyDecision

        validate_bound_effect_contract(
            effect
        )

        if not isinstance(
            authorization,
            BoundRemediationAuthorization,
        ):
            raise TypeError(
                "authorization must be a "
                "BoundRemediationAuthorization"
            )

        if not authorization.authorized:
            raise PermissionError(
                "bound remediation authorization is DENY"
            )

        if not authorization.matches(effect):
            raise PermissionError(
                "authorization_effect_binding_mismatch"
            )

        if decision.decision is not PolicyDecision.ALLOW:
            raise PermissionError(
                "remediation decision is not ALLOW"
            )

        if decision.component_id != effect.component_id:
            raise PermissionError(
                "decision_component_binding_mismatch"
            )

        if decision.action != effect.action:
            raise PermissionError(
                "decision_action_binding_mismatch"
            )

        result = self.executor.execute_argv(
            effect.argv,
            timeout=timeout,
        )

        return RemediationExecutionResult(
            decision=decision,
            execution=result,
        )
