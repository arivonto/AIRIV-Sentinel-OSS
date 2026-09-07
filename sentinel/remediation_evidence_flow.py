"""AIRIV Sentinel canonical remediation evidence flow."""

from dataclasses import dataclass

from sentinel.execution_evidence import ExecutionEvidence
from sentinel.incidents.manager import Incident
from sentinel.remediation_orchestrator import OrchestrationResult
from sentinel.remediation_verifier import VerificationResult


@dataclass(frozen=True)
class RemediationEvidenceRecord:
    incident_id: str
    component_id: str
    decision: str
    decision_reason: str
    action: str
    execution_id: str
    execution_evidence: ExecutionEvidence | None
    verification: VerificationResult | None


class EvidenceCompleteRemediationFlow:
    """Attach complete remediation evidence to canonical Incident."""

    def finalize(
        self,
        incident: Incident,
        result: OrchestrationResult,
    ) -> tuple[Incident, RemediationEvidenceRecord]:
        if not isinstance(incident, Incident):
            raise TypeError(
                "incident must be a canonical Incident"
            )

        if not result.execution_id:
            raise ValueError(
                "remediation result requires execution_id"
            )

        execution_evidence = None

        if result.execution is not None:
            execution_evidence = ExecutionEvidence.from_result(
                result.execution
            )

        signal = {
            "decision": result.decision.decision.value,
            "decision_reason": result.decision.reason,
            "action": result.decision.action,
            "execution_id": result.execution_id,
            "replayed": result.replayed,
        }

        if execution_evidence is not None:
            signal["execution"] = {
                "command": execution_evidence.command,
                "stdout": execution_evidence.stdout,
                "stderr": execution_evidence.stderr,
                "exit_code": execution_evidence.exit_code,
                "started_at": execution_evidence.started_at,
                "finished_at": execution_evidence.finished_at,
                "success": execution_evidence.success,
            }

        if result.replayed:
            signal_type = "REMEDIATION_REPLAYED"
            reason = (
                "Remediation execution identity was already consumed; "
                "no duplicate remediation execution was performed."
            )

        elif execution_evidence is None:
            signal_type = "REMEDIATION_DENIED"
            reason = "Remediation was denied by policy."

        elif not execution_evidence.success:
            signal_type = "REMEDIATION_FAILED"
            reason = "Remediation execution failed."

        elif result.verification is None:
            signal_type = "REMEDIATION_EXECUTED_UNVERIFIED"
            reason = (
                "Remediation execution completed, "
                "but post-remediation state was not verified."
            )

        elif result.verification.verified:
            signal["verification"] = {
                "verified": result.verification.verified,
                "reason": result.verification.reason,
                "observation": result.verification.observation,
            }

            signal_type = "REMEDIATION_VERIFIED"
            reason = (
                "Remediation execution completed and "
                "post-remediation state was independently verified."
            )

        else:
            signal["verification"] = {
                "verified": result.verification.verified,
                "reason": result.verification.reason,
                "observation": result.verification.observation,
            }

            signal_type = "REMEDIATION_VERIFICATION_FAILED"
            reason = (
                "Remediation execution completed, "
                "but post-remediation state verification failed."
            )

        incident.add_evidence(
            observation={},
            reason=reason,
            signal_type=signal_type,
            signal=signal,
        )

        evidence = RemediationEvidenceRecord(
            incident_id=incident.incident_id,
            component_id=incident.component_id,
            decision=result.decision.decision.value,
            decision_reason=result.decision.reason,
            action=result.decision.action,
            execution_id=result.execution_id,
            execution_evidence=execution_evidence,
            verification=result.verification,
        )

        return incident, evidence
