import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sentinel.evidence import EvidenceTrail


class Incident:
    """
    AIRIV Sentinel Incident Manager V1.

    Strict lifecycle:
        OPEN -> INVESTIGATING -> RESOLVED

    Evidence is append-only.
    Resolution requires explicit recovery evidence.
    """

    VALID_STATUSES = {
        "OPEN",
        "INVESTIGATING",
        "TERMINAL",
    }

    VALID_OUTCOMES = {
        "RECOVERED",
        "UNRESOLVED",
        "ESCALATED",
        "INSUFFICIENT_EVIDENCE",
    }

    ALLOWED_TRANSITIONS = {
        "OPEN": {"INVESTIGATING"},
        "INVESTIGATING": {"TERMINAL"},
        "TERMINAL": set(),
    }

    def __init__(
        self,
        incident_id: str,
        component_id: str,
        agent_identity: str,
        anomaly_type: str,
    ):
        self.incident_id = incident_id
        self.component_id = component_id
        self.agent_identity = agent_identity
        self.anomaly_type = anomaly_type
        self.status = "OPEN"
        self.lifecycle_state = "OPEN"
        self.final_outcome = None
        self.created_at = self._now()
        self.updated_at = self.created_at
        self.evidence_store = EvidenceTrail()
        self.evidence_trail: List[Dict[str, Any]] = []

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_evidence(
        self,
        observation: Optional[Dict[str, Any]],
        reason: str,
        signal_type: str = "OBSERVATION",
        signal: Optional[Dict[str, Any]] = None,
    ) -> None:
        observation = observation or {}
        signal = signal or {}

        entry = {
            "timestamp": self._now(),
            "signal_type": signal_type,
            "reason": reason,
            "observation_snapshot": deepcopy({
                "pane_id": observation.get("pane_id"),
                "window_name": observation.get("window_name"),
                "current_command": observation.get("current_command"),
                "activity_state": observation.get("activity_state"),
                "output_sha256": observation.get("output_sha256"),
                "agent_identity": observation.get("agent_identity"),
            }),
            "signal_snapshot": deepcopy(signal),
        }

        self.evidence_store.append(
            incident_id=self.incident_id,
            component_id=self.component_id,
            evidence_type=signal_type,
            reason=reason,
            observation=observation,
            signal=signal,
        )

        self.evidence_trail.append(entry)
        self.updated_at = self._now()

    def get_evidence_records(self):
        """
        Return the canonical immutable EvidenceRecord objects.

        EvidenceTrail is the canonical structured evidence store.
        The legacy evidence_trail list remains available for serialized
        Incident snapshots and compatibility.
        """
        return self.evidence_store.records()

    def update_status(
        self,
        new_status: str,
        operator_note: Optional[str] = None,
    ) -> None:
        """
        Transition the canonical Incident lifecycle.

        V2 lifecycle:
            OPEN -> INVESTIGATING -> TERMINAL

        Final outcome is intentionally separate from lifecycle state.

        V1 compatibility:
            RESOLVED is accepted as a legacy input and normalized to
            TERMINAL. It is never stored as the V2 lifecycle state.
        """
        new_status = new_status.upper()

        if new_status == "RESOLVED":
            new_status = "TERMINAL"

        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid incident status: {new_status}")

        if new_status == self.status:
            raise ValueError(
                f"Invalid incident transition: {self.status} -> {new_status}"
            )

        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid incident transition: {self.status} -> {new_status}"
            )

        self.status = new_status
        self.lifecycle_state = new_status
        self.updated_at = self._now()

        if operator_note:
            self.add_evidence(
                {},
                "Operator note",
                "OPERATOR_NOTE",
                {"note": operator_note},
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "component_id": self.component_id,
            "agent_identity": self.agent_identity,
            "anomaly_type": self.anomaly_type,
            "status": self.status,
            "lifecycle_state": self.lifecycle_state,
            "final_outcome": self.final_outcome,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "evidence_count": len(self.evidence_trail),
            "evidence_trail": deepcopy(self.evidence_trail),
        }



class IncidentManager:
    """
    Incident Manager V1.

    Intake:
        - state transitions
        - anomaly signals
        - contract violations
        - explicit recovery evidence

    Ordinary recovery-looking states NEVER resolve incidents.
    """

    ANOMALY_STATES = {
        "STUCK",
        "FAILED",
    }

    def __init__(self):
        self.active_incidents: Dict[str, Incident] = {}
        self.incident_history: List[Dict[str, Any]] = []

    @staticmethod
    def _new_incident_id() -> str:
        return f"INC-{uuid.uuid4()}"

    def _create_incident(
        self,
        observation: Dict[str, Any],
        anomaly_type: str,
        reason: str,
        signal_type: str,
        signal: Optional[Dict[str, Any]] = None,
    ) -> Incident:
        component_id = observation.get("pane_id")

        if not component_id:
            raise ValueError(
                "Incident requires observation.pane_id"
            )

        incident = Incident(
            incident_id=self._new_incident_id(),
            component_id=component_id,
            agent_identity=observation.get(
                "agent_identity",
                "UNKNOWN",
            ),
            anomaly_type=anomaly_type,
        )

        incident.add_evidence(
            observation,
            reason,
            signal_type,
            signal,
        )

        self.active_incidents[component_id] = incident
        return incident

    def evaluate_state_transition(
        self,
        observation: Dict[str, Any],
        current_state: str,
    ) -> Optional[Incident]:
        state = (current_state or "").upper()

        if state in self.ANOMALY_STATES:
            return self.evaluate_anomaly(
                observation=observation,
                anomaly_type=state,
                reason=f"State Machine anomaly state: {state}",
            )

        # IMPORTANT:
        # OBSERVING / TASK_ACTIVE / WAITING / COMPLETED etc.
        # do NOT resolve an existing incident.
        return None

    def evaluate_anomaly(
        self,
        observation: Dict[str, Any],
        anomaly_type: str,
        reason: Optional[str] = None,
        signal: Optional[Dict[str, Any]] = None,
    ) -> Incident:
        component_id = observation.get("pane_id")

        if not component_id:
            raise ValueError(
                "Anomaly evaluation requires observation.pane_id"
            )

        anomaly_type = (
            anomaly_type or "UNKNOWN_ANOMALY"
        ).upper()

        incident = self.active_incidents.get(component_id)

        if incident is None:
            return self._create_incident(
                observation=observation,
                anomaly_type=anomaly_type,
                reason=(
                    reason
                    or f"Anomaly signal: {anomaly_type}"
                ),
                signal_type="ANOMALY",
                signal=signal,
            )

        incident.add_evidence(
            observation,
            reason or f"Confirmed ongoing anomaly: {anomaly_type}",
            "ANOMALY",
            signal,
        )

        return incident

    def evaluate_contract_violation(
        self,
        observation: Dict[str, Any],
        violation_type: str,
        reason: str,
        signal: Optional[Dict[str, Any]] = None,
    ) -> Incident:
        component_id = observation.get("pane_id")

        if not component_id:
            raise ValueError(
                "Contract violation requires observation.pane_id"
            )

        violation_type = (
            violation_type or "CONTRACT_VIOLATION"
        ).upper()

        incident = self.active_incidents.get(component_id)

        if incident is None:
            return self._create_incident(
                observation=observation,
                anomaly_type=violation_type,
                reason=reason,
                signal_type="CONTRACT_VIOLATION",
                signal=signal,
            )

        incident.add_evidence(
            observation,
            reason,
            "CONTRACT_VIOLATION",
            signal,
        )

        return incident

    def investigate(
        self,
        component_id: str,
        operator_note: Optional[str] = None,
    ) -> Incident:
        incident = self.active_incidents.get(component_id)

        if incident is None:
            raise KeyError(
                f"No active incident for component: {component_id}"
            )

        incident.update_status(
            "INVESTIGATING",
            operator_note,
        )

        return incident

    def resolve(
        self,
        component_id: str,
        recovery_evidence: Dict[str, Any],
        observation: Optional[Dict[str, Any]] = None,
        operator_note: Optional[str] = None,
        final_outcome: str = "RECOVERED",
    ) -> Incident:
        """
        Explicitly terminalize an incident with a final outcome.

        Recovery evidence is mandatory for every terminalization because
        terminal state must remain evidence-backed and auditable.
        """
        if not recovery_evidence:
            raise ValueError("Explicit recovery evidence is required")

        final_outcome = final_outcome.upper()

        if final_outcome not in Incident.VALID_OUTCOMES:
            raise ValueError(
                f"Invalid incident final outcome: {final_outcome}"
            )

        incident = self.active_incidents.get(component_id)
        if incident is None:
            raise KeyError(
                f"No active incident for component: {component_id}"
            )

        incident.add_evidence(
            observation or {},
            "Explicit recovery evidence accepted",
            "RECOVERY",
            recovery_evidence,
        )

        if incident.status == "OPEN":
            incident.update_status(
                "INVESTIGATING",
                "Recovery evidence received; investigation required.",
            )

        incident.final_outcome = final_outcome

        incident.update_status(
            "TERMINAL",
            operator_note
            or f"Incident terminalized with outcome: {final_outcome}.",
        )

        snapshot = incident.to_dict()
        self.active_incidents.pop(component_id, None)
        self.incident_history.append(deepcopy(snapshot))
        return incident

    def intake(
        self,
        observation: Dict[str, Any],
        current_state: Optional[str] = None,
        anomaly_signal: Optional[Dict[str, Any]] = None,
        contract_violation: Optional[Dict[str, Any]] = None,
        recovery_evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[Incident]:
        """
        Unified Incident Manager V1 intake boundary.
        """

        if not observation.get("pane_id"):
            raise ValueError(
                "Incident intake requires observation.pane_id"
            )

        component_id = observation["pane_id"]

        if recovery_evidence:
            return self.resolve(
                component_id=component_id,
                recovery_evidence=recovery_evidence,
                observation=observation,
            )

        if contract_violation:
            return self.evaluate_contract_violation(
                observation=observation,
                violation_type=contract_violation.get(
                    "violation_type",
                    "CONTRACT_VIOLATION",
                ),
                reason=contract_violation.get(
                    "reason",
                    "Contract violation detected.",
                ),
                signal=contract_violation,
            )

        if anomaly_signal:
            return self.evaluate_anomaly(
                observation=observation,
                anomaly_type=anomaly_signal.get(
                    "anomaly_type",
                    "UNKNOWN_ANOMALY",
                ),
                reason=anomaly_signal.get(
                    "reason",
                    "Anomaly signal detected.",
                ),
                signal=anomaly_signal,
            )

        if current_state:
            return self.evaluate_state_transition(
                observation,
                current_state,
            )

        return None

    def get_active_incident(
        self,
        component_id: str,
    ) -> Optional[Incident]:
        return self.active_incidents.get(component_id)

    def get_incident_by_id(self, incident_id: str) -> Optional[Incident]:
        """Read an active incident by incident identity, never component key."""
        return next((incident for incident in self.active_incidents.values()
                     if incident.incident_id == incident_id), None)

    def get_history(self) -> List[Dict[str, Any]]:
        return deepcopy(self.incident_history)
