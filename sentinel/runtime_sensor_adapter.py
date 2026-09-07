"""AIRIV Sentinel canonical runtime sensor adapter.

Boundary:
TMUX Sensor -> Normalization -> State Machine -> Integration Bridge

Component identity is observation.pane_id.
State is maintained independently for each observed pane.
"""

from typing import Any, Dict, List, Optional

from sentinel.sensors.tmux.parser import TmuxStateParserV11
from sentinel.normalization.resolver import (
    IdentityResolver,
    ActivityDetector,
    normalize_observations,
)
from sentinel.state.state_machine import StateMachine, classify_and_update
from sentinel.integration.bridge import SentinelIntegrationBridge
from sentinel.contract_verifier import ContractVerifier


class RuntimeSensorAdapter:
    """Canonical runtime adapter for the sensor pipeline."""

    def __init__(
        self,
        parser: Optional[TmuxStateParserV11] = None,
        identity_resolver: Optional[IdentityResolver] = None,
        activity_detector: Optional[ActivityDetector] = None,
        bridge: Optional[SentinelIntegrationBridge] = None,
    ) -> None:
        self.parser = parser or TmuxStateParserV11()
        self.identity_resolver = identity_resolver or IdentityResolver()
        self.activity_detector = activity_detector or ActivityDetector()
        self.bridge = bridge or SentinelIntegrationBridge()
        self.contract_verifier = ContractVerifier()

        # One deterministic state machine per canonical component.
        self.state_machines: Dict[str, StateMachine] = {}

    def collect(self) -> List[Dict[str, Any]]:
        """Collect raw observations from the canonical TMUX sensor."""
        return self.parser.inspect_panes()

    def normalize(
        self,
        raw_observations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Normalize observations through the canonical normalizer."""
                # PHASE_213C1C_IDENTITY_PROPAGATION
        normalized = normalize_observations(raw_observations, self.identity_resolver)

        identity_fields = (
            "server_socket",
            "server_generation",
            "session_id",
            "session_name",
            "window_id",
            "window_index",
            "window_name",
            "pane_id",
            "pane_index",
            "pane_pid",
            "captured_at",
            "output_sha256",
            "capture_ok",
            "tmux_identity",
            "tmux_identity_valid",
        )

        raw_by_pane = {
            item.get("pane_id"): item
            for item in raw_observations
            if item.get("pane_id")
        }

        for observation in normalized:
            pane_id = observation.get("pane_id")
            raw = raw_by_pane.get(pane_id)

            if raw is None:
                continue

            for key in identity_fields:
                if key in raw:
                    observation[key] = raw[key]

        return normalized

    def _get_state_machine(
        self,
        component_id: str,
    ) -> StateMachine:
        if not component_id:
            raise ValueError("component_id must not be empty")

        if component_id not in self.state_machines:
            self.state_machines[component_id] = StateMachine(
                component_id=component_id,
            )

        return self.state_machines[component_id]

    def process_tick(
        self,
        raw_observations: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Any]:
        """Execute one complete sensor -> verification -> incident pipeline tick."""
        raw = (
            raw_observations
            if raw_observations is not None
            else self.collect()
        )

        normalized = self.normalize(raw)
        incidents: List[Any] = []
        emitted_incident_ids: set[str] = set()

        for observation in normalized:
            component_id = observation.get("pane_id")

            if not component_id:
                raise ValueError(
                    "Canonical component_id requires observation.pane_id"
                )

            # Contract verification is detection-only.
            # It MUST NOT execute remediation.
            violations = self.contract_verifier.verify(observation)

            for violation in violations:
                incident = self.bridge.process_contract_violation(
                    observation=observation,
                    violation_type=violation.violation_type,
                    reason=violation.reason,
                    signal={
                        "contract_id": violation.contract_id,
                        "component_id": violation.component_id,
                        "detected_at": violation.detected_at,
                    },
                )

                # Decision B:
                # Incident is a lifecycle entity. Multiple violations
                # belonging to the same active Incident must be emitted
                # only once from this process tick.
                if (
                    incident is not None
                    and incident.incident_id not in emitted_incident_ids
                ):
                    incidents.append(incident)
                    emitted_incident_ids.add(incident.incident_id)

            # State machine remains canonical and independent.
            state_machine = self._get_state_machine(component_id)

            state = classify_and_update(
                state_machine,
                observation,
            )

            current_state = (
                state.value
                if hasattr(state, "value")
                else str(state)
            )

            # Preserve normal state-transition incident evaluation.
            if not violations:
                incident = self.bridge.process_tick(
                    observation,
                    current_state,
                )

                if (
                    incident is not None
                    and incident.incident_id not in emitted_incident_ids
                ):
                    incidents.append(incident)
                    emitted_incident_ids.add(incident.incident_id)

        return incidents
