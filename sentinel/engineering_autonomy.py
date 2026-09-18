"""Bounded autonomous engineering decisions with no production authority."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class EngineeringDecision(str, Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    ESCALATE = "ESCALATE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EngineeringDecisionRecord:
    decision_id: str
    request_identity: str
    decision: EngineeringDecision
    authority_basis: str
    reason: str
    production_effect: str = "NONE"


_SAFE_OPERATIONS = frozenset({
    "inspect", "select_roadmap_slice", "edit_code", "edit_tests",
    "run_tests", "compile", "validate_docs", "security_scan",
    "create_branch", "commit", "push_branch", "open_pr", "monitor_ci",
    "update_evidence", "local_shell_execution", "refactor",
    "debug_failures", "retry", "docker_development_operation",
    "development_service_restart", "development_database_operation",
    "ci_failure_repair", "documentation_update",
})
_DENIED_OPERATIONS = frozenset({
    "provider_live", "external_delivery", "unrestricted_shell",
    "bypass_ci", "privilege_expansion", "production_fault_injection",
})
_ESCALATE_OPERATIONS = frozenset({
    "production_restart", "production_start", "production_stop",
    "production_upgrade", "production_rollback", "deployment",
    "contract_amendment", "architecture_change", "governance_change",
    "remediation_authority",
})


def classify_engineering_request(
    request: Mapping[str, Any],
) -> EngineeringDecisionRecord:
    """Classify a caller-supplied request without executing it or granting authority."""
    decision_id = request.get("decision_id")
    request_identity = request.get("request_identity")
    operation = request.get("operation")
    basis = request.get("authority_basis")

    if not all(isinstance(value, str) and value.strip() for value in (
        decision_id, request_identity, operation, basis,
    )):
        return EngineeringDecisionRecord(
            decision_id=decision_id if isinstance(decision_id, str) else "UNKNOWN",
            request_identity=request_identity if isinstance(request_identity, str) else "UNKNOWN",
            decision=EngineeringDecision.UNKNOWN,
            authority_basis=basis if isinstance(basis, str) else "UNKNOWN",
            reason="required decision facts are missing or malformed",
        )

    operation = operation.strip().lower()
    if operation in _SAFE_OPERATIONS:
        trusted_v11 = (
            request.get("authority_profile")
            == "TRUSTED_AUTONOMOUS_ENGINEERING"
        )
        return EngineeringDecisionRecord(
            decision_id=decision_id,
            request_identity=request_identity,
            decision=EngineeringDecision.ALLOWED,
            authority_basis=basis,
            reason=(
                "routine development operation is allowed by "
                "constitution v1.1"
                if trusted_v11
                else "bounded engineering operation is within the approved foundation"
            ),
        )
    if operation in _DENIED_OPERATIONS:
        decision = EngineeringDecision.DENIED
        reason = "operation is explicitly outside the engineering authority boundary"
    elif operation in _ESCALATE_OPERATIONS:
        decision = EngineeringDecision.ESCALATE
        reason = "operation requires Commander-level authority"
    else:
        decision = EngineeringDecision.UNKNOWN
        reason = "operation is not recognized by the bounded allowlist"
    return EngineeringDecisionRecord(
        decision_id=decision_id,
        request_identity=request_identity,
        decision=decision,
        authority_basis=basis,
        reason=reason,
    )
