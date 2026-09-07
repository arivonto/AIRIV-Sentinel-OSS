from dataclasses import dataclass
from typing import Any

from .models import Diagnosis


@dataclass(frozen=True, slots=True)
class RemediationActionRequest:
    """
    Explicit orchestration handoff from diagnosis to Commander.

    The request carries operational intent and evidence references only.
    It deliberately contains no executable command.
    """

    incident_id: str
    investigation_id: str
    diagnosis_id: str
    action: str
    reason: str
    supporting_evidence_ids: tuple[str, ...]

    @classmethod
    def from_diagnosis(
        cls,
        *,
        incident_id: str,
        diagnosis: Diagnosis,
        action: str,
        reason: str | None = None,
    ) -> "RemediationActionRequest":
        if not incident_id:
            raise ValueError("incident_id must not be empty")

        if diagnosis.status.value != "ESTABLISHED":
            raise ValueError(
                "only ESTABLISHED diagnosis may be handed off"
            )

        if not diagnosis.diagnosis_id:
            raise ValueError("diagnosis must have a diagnosis_id")

        if not diagnosis.investigation_id:
            raise ValueError("diagnosis must have an investigation_id")

        if not action:
            raise ValueError("action must not be empty")

        return cls(
            incident_id=incident_id,
            investigation_id=diagnosis.investigation_id,
            diagnosis_id=diagnosis.diagnosis_id,
            action=action,
            reason=reason or diagnosis.conclusion,
            supporting_evidence_ids=tuple(
                diagnosis.supporting_evidence_ids
            ),
        )


class CommanderHandoff:
    """
    Explicit orchestration boundary between Diagnosis and Commander.

    Decision flow:
        Diagnosis
          -> Action Request
          -> Commander decision
          -> ALLOW
          -> Commander.remediate()

    The handoff adapter never executes commands itself.
    """

    def __init__(self, commander: Any) -> None:
        self.commander = commander

    def decide(
        self,
        request: RemediationActionRequest,
        incident: Any,
    ) -> Any:
        if incident.incident_id != request.incident_id:
            raise ValueError("incident_id mismatch")

        return self.commander.decide_remediation(
            incident=incident,
            action=request.action,
        )

    def remediate(
        self,
        request: RemediationActionRequest,
        incident: Any,
        *,
        command: str,
        decision: Any,
        execution_id: str | None = None,
        verifier: Any | None = None,
    ) -> Any:
        """
        Execute an already-authorized remediation through Commander.

        The decision MUST be supplied by the preceding canonical
        Commander decision boundary. This method never calls
        decide_remediation() and never executes commands itself.
        """
        if incident.incident_id != request.incident_id:
            raise ValueError("incident_id mismatch")

        if not command:
            raise ValueError("command must not be empty")

        if decision is None:
            raise ValueError("decision must not be empty")

        if not decision.authorized:
            return decision

        return self.commander.remediate(
            incident=incident,
            action=request.action,
            command=command,
            execution_id=execution_id,
            verifier=verifier,
            decision=decision,
        )

    # PHASE_213C1B2_BOUND_HANDOFF
    def decide_bound(
        self,
        *,
        request,
        incident,
        effect,
    ):
        """Delegate one exact effect to Commander policy authority."""

        if incident.incident_id != request.incident_id:
            raise ValueError("incident_id mismatch")

        if effect.incident_id != request.incident_id:
            raise ValueError(
                "effect incident_id mismatch"
            )

        if effect.action != request.action:
            raise ValueError(
                "effect action mismatch"
            )

        return self.commander.decide_bound_remediation(
            incident=incident,
            effect=effect,
        )

    def remediate_bound(
        self,
        *,
        request,
        incident,
        effect,
        authorization,
        verifier=None,
        timeout: float = 5.0,
    ):
        """Execute an exact already-authorized immutable effect."""

        if incident.incident_id != request.incident_id:
            raise ValueError("incident_id mismatch")

        if effect.incident_id != request.incident_id:
            raise ValueError(
                "effect incident_id mismatch"
            )

        if effect.action != request.action:
            raise ValueError(
                "effect action mismatch"
            )

        return self.commander.remediate_bound(
            incident=incident,
            effect=effect,
            authorization=authorization,
            verifier=verifier,
            timeout=timeout,
        )
