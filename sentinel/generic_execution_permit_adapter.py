"""Generic resource execution/permit adapter.

Phase 2.13D.D4B.

This adapter owns no authorization, permit, journal, or execution
authority. It validates the generic resource binding and delegates
exactly once to the existing RemediationExecutionIdentityBoundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.bound_effect_contract import (
    validate_bound_effect_contract,
)
from sentinel.live_remediation_safety import (
    BoundRemediationAuthorization,
)
from sentinel.remediation_execution_identity import (
    ExecutionIdentityRecord,
    RemediationExecutionIdentityBoundary,
)
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationDecision,
)
from sentinel.execution import (
    ExecutionResult,
)
from sentinel.resource_bound_remediation import (
    ResourceBoundPermitBinding,
)


@dataclass(
    frozen=True,
    slots=True,
)
class GenericExecutionPermitResult:
    execution: ExecutionResult | None
    identity_record: ExecutionIdentityRecord
    replayed: bool


class GenericResourceExecutionPermitAdapter:
    """Thin generic facade over canonical permit/execution authority."""

    def __init__(
        self,
        identity_boundary:
            RemediationExecutionIdentityBoundary,
    ) -> None:
        if not isinstance(
            identity_boundary,
            RemediationExecutionIdentityBoundary,
        ):
            raise TypeError(
                "identity_boundary must be a "
                "RemediationExecutionIdentityBoundary"
            )

        self.identity_boundary = (
            identity_boundary
        )

    @staticmethod
    def _execution_decision(
        *,
        authorization:
            BoundRemediationAuthorization,
        incident_state: str,
    ) -> RemediationDecision:
        if not isinstance(
            incident_state,
            str,
        ) or not incident_state.strip():
            raise ValueError(
                "incident_state is required"
            )

        return RemediationDecision(
            decision=(
                PolicyDecision.ALLOW
                if authorization.authorized
                else PolicyDecision.DENY
            ),
            reason=authorization.reason,
            incident_state=(
                incident_state.strip()
            ),
            component_id=(
                authorization.component_id
            ),
            action=(
                authorization.action
            ),
        )

    def execute(
        self,
        *,
        effect,
        authorization:
            BoundRemediationAuthorization,
        permit_binding:
            ResourceBoundPermitBinding,
        incident_state: str,
        timeout: float = 5.0,
    ) -> GenericExecutionPermitResult:
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

        if not isinstance(
            permit_binding,
            ResourceBoundPermitBinding,
        ):
            raise TypeError(
                "permit_binding must be a "
                "ResourceBoundPermitBinding"
            )

        if not permit_binding.matches(
            effect
        ):
            raise PermissionError(
                "resource_permit_binding_mismatch"
            )

        if not authorization.authorized:
            raise PermissionError(
                "bound remediation authorization is DENY"
            )

        if not authorization.matches(
            effect
        ):
            raise PermissionError(
                "authorization_effect_binding_mismatch"
            )

        decision = (
            self._execution_decision(
                authorization=authorization,
                incident_state=incident_state,
            )
        )

        execution, record, replayed = (
            self.identity_boundary
            .execute_bound(
                effect=effect,
                authorization=authorization,
                decision=decision,
                timeout=timeout,
            )
        )

        return GenericExecutionPermitResult(
            execution=execution,
            identity_record=record,
            replayed=replayed,
        )
