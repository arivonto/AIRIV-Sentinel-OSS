from typing import Dict, Optional
from sentinel.incidents.manager import IncidentManager, Incident


class SentinelIntegrationBridge:
    """
    Integration boundary:
    Normalizer -> StateMachine -> IncidentManager.
    No incident lifecycle semantics are owned here.
    """

    def __init__(self, incident_manager: Optional[IncidentManager] = None):
        self.incident_manager = incident_manager or IncidentManager()

    def process_tick(
        self,
        observation: Dict,
        current_state: str,
    ) -> Optional[Incident]:
        return self.incident_manager.evaluate_state_transition(
            observation,
            current_state,
        )

    def process_contract_violation(
        self,
        observation: Dict,
        violation_type: str,
        reason: str,
        signal: Optional[Dict] = None,
    ) -> Incident:
        return self.incident_manager.evaluate_contract_violation(
            observation,
            violation_type,
            reason,
            signal,
        )
