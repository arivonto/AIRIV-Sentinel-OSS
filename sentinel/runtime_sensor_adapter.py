"""AIRIV Sentinel canonical runtime sensor adapter.

Boundary:
TMUX Sensor -> Normalization -> State Machine -> Integration Bridge

Externally projected component identity remains observation.pane_id.
Canonical process state and read-only observability state are isolated.
Observability state is retained across ticks only for validated strong TMUX
component identity so pane-ID reuse cannot inherit state across generations.
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


SENSOR_OBSERVABILITY_SCHEMA = "AIRIV_SENTINEL_SENSOR_OBSERVABILITY_V1"
SENSOR_HEALTH_SCHEMA = "AIRIV_SENTINEL_SENSOR_HEALTH_V1"


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

        # Canonical process_tick state. Read-only observability must never
        # mutate this store because doing so could affect incident behavior.
        self.state_machines: Dict[str, StateMachine] = {}

        # Passive observability state is isolated from the canonical process
        # path. Retention is allowed only while strong TMUX component identity
        # remains stable for the pane ID.
        self.observability_state_machines: Dict[str, StateMachine] = {}
        self._observability_state_identities: Dict[
            str,
            tuple[str, str, str, str],
        ] = {}

    def collect(self) -> List[Dict[str, Any]]:
        """Collect raw observations from the canonical TMUX sensor."""
        return self.parser.inspect_panes()

    def normalize(
        self,
        raw_observations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Normalize observations through the canonical normalizer."""
        # PHASE_213C1C_IDENTITY_PROPAGATION
        normalized = normalize_observations(
            raw_observations,
            self.identity_resolver,
            self.activity_detector,
        )

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

    @staticmethod
    def _strong_observability_identity(
        observation: Dict[str, Any],
    ) -> Optional[tuple[str, str, str, str]]:
        """Return validated generation-scoped TMUX identity for state retention.

        The tuple is process-local correlation data only. It is never emitted
        by the minimized observability projection.
        """

        if observation.get("tmux_identity_valid") is not True:
            return None

        identity = observation.get("tmux_identity")

        if not isinstance(identity, dict):
            return None

        values = tuple(
            identity.get(key)
            for key in (
                "server_generation",
                "session_id",
                "window_id",
                "pane_id",
            )
        )

        if not all(
            isinstance(value, str) and bool(value)
            for value in values
        ):
            return None

        if observation.get("pane_id") != values[-1]:
            return None

        return values

    def _get_observability_state_machine(
        self,
        observation: Dict[str, Any],
    ) -> StateMachine:
        """Return state isolated from canonical process state.

        Strong identity allows deterministic cross-tick retention. Unknown,
        malformed, or unvalidated identity is handled with an ephemeral state
        machine so uncertain observations cannot poison later projections.
        """

        component_id = observation.get("pane_id")

        if not isinstance(component_id, str) or not component_id:
            raise ValueError(
                "Canonical component_id requires observation.pane_id"
            )

        strong_identity = self._strong_observability_identity(
            observation
        )

        if strong_identity is None:
            return StateMachine(component_id=component_id)

        previous_identity = self._observability_state_identities.get(
            component_id
        )

        if (
            previous_identity != strong_identity
            or component_id not in self.observability_state_machines
        ):
            self.observability_state_machines[
                component_id
            ] = StateMachine(component_id=component_id)
            self._observability_state_identities[
                component_id
            ] = strong_identity

        return self.observability_state_machines[component_id]

    @staticmethod
    def _state_value(state: Any) -> str:
        return (
            state.value
            if hasattr(state, "value")
            else str(state)
        )

    @staticmethod
    def _project_observability(
        observation: Dict[str, Any],
        state_machine: StateMachine,
        previous_state: str,
        current_state: str,
    ) -> Dict[str, Any]:
        """Project minimized, authority-free facts for one observed pane."""

        return {
            "schema": SENSOR_OBSERVABILITY_SCHEMA,
            "source": observation.get("source"),
            "observed_at": observation.get("captured_at"),
            "component_id": observation.get("pane_id"),
            "agent_identity": observation.get("agent_identity"),
            "activity_state": observation.get("activity_state"),
            "state_input": {
                "activity_state": observation.get("activity_state"),
                "output_changed": observation.get("output_changed"),
                "completion_evidence": observation.get("completion_evidence"),
                "waiting_evidence": observation.get("waiting_evidence"),
            },
            "previous_state": previous_state,
            "current_state": current_state,
            "state_transitioned": previous_state != current_state,
            "job_type": state_machine.current_job_type,
            "sensor_facts": {
                "capture_ok": observation.get("capture_ok"),
                "first_observation": observation.get("first_observation"),
                "output_changed": observation.get("output_changed"),
                "pane_dead": observation.get("pane_dead"),
                "tmux_identity_valid": observation.get("tmux_identity_valid"),
            },
        }

    @staticmethod
    def _boolean_fact_counts(values: List[Any]) -> Dict[str, int]:
        """Count explicit true/false/unknown facts without truthiness coercion."""

        return {
            "true": sum(value is True for value in values),
            "false": sum(value is False for value in values),
            "unknown": sum(
                value is not True and value is not False
                for value in values
            ),
        }

    @staticmethod
    def _categorical_fact_counts(values: List[Any]) -> Dict[str, int]:
        """Count string facts while preserving malformed/missing as UNKNOWN."""

        counts: Dict[str, int] = {}

        for value in values:
            key = (
                value
                if isinstance(value, str) and value
                else "UNKNOWN"
            )
            counts[key] = counts.get(key, 0) + 1

        return {
            key: counts[key]
            for key in sorted(counts)
        }

    @classmethod
    def project_sensor_health(
        cls,
        projections: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Summarize one sensor tick without manufacturing health semantics.

        The result reports only observed counts and explicit unknowns. It does
        not infer HEALTHY/UNHEALTHY, readiness, remediation permission, or any
        lifecycle outcome from the sensor facts.
        """

        sensor_facts = [
            projection.get("sensor_facts")
            if isinstance(projection.get("sensor_facts"), dict)
            else {}
            for projection in projections
        ]
        component_ids = [
            projection.get("component_id")
            for projection in projections
        ]
        distinct_component_ids = {
            component_id
            for component_id in component_ids
            if isinstance(component_id, str) and component_id
        }
        observation_times = sorted(
            {
                observed_at
                for observed_at in (
                    projection.get("observed_at")
                    for projection in projections
                )
                if isinstance(observed_at, str) and observed_at
            }
        )
        sources = sorted(
            {
                source
                for source in (
                    projection.get("source")
                    for projection in projections
                )
                if isinstance(source, str) and source
            }
        )
        agent_identities = [
            projection.get("agent_identity")
            for projection in projections
        ]

        resolved_identity_count = sum(
            isinstance(identity, str)
            and bool(identity)
            and identity != "UNKNOWN"
            for identity in agent_identities
        )

        return {
            "schema": SENSOR_HEALTH_SCHEMA,
            "sources": sources,
            "observation_times": observation_times,
            "observation_count": len(projections),
            "distinct_component_count": len(distinct_component_ids),
            "component_identity": {
                "present": sum(
                    isinstance(component_id, str) and bool(component_id)
                    for component_id in component_ids
                ),
                "unknown": sum(
                    not isinstance(component_id, str) or not component_id
                    for component_id in component_ids
                ),
            },
            "agent_identity": {
                "resolved": resolved_identity_count,
                "unknown": len(agent_identities) - resolved_identity_count,
            },
            "activity_counts": cls._categorical_fact_counts(
                [
                    projection.get("activity_state")
                    for projection in projections
                ]
            ),
            "state_counts": cls._categorical_fact_counts(
                [
                    projection.get("current_state")
                    for projection in projections
                ]
            ),
            "capture_ok": cls._boolean_fact_counts(
                [facts.get("capture_ok") for facts in sensor_facts]
            ),
            "tmux_identity_valid": cls._boolean_fact_counts(
                [facts.get("tmux_identity_valid") for facts in sensor_facts]
            ),
            "pane_dead": cls._boolean_fact_counts(
                [facts.get("pane_dead") for facts in sensor_facts]
            ),
            "state_transitioned": cls._boolean_fact_counts(
                [
                    projection.get("state_transitioned")
                    for projection in projections
                ]
            ),
        }

    def observe_tick(
        self,
        raw_observations: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Run one sensor-to-state tick with passive observability output.

        This path deliberately does not invoke ContractVerifier, the incident
        integration bridge, remediation policy, execution, or host mutation.
        It uses an isolated observability-only state store so reading this view
        cannot alter canonical process_tick state. Cross-tick state is retained
        only when strong TMUX component identity is validated.
        """

        raw = (
            raw_observations
            if raw_observations is not None
            else self.collect()
        )

        normalized = self.normalize(raw)
        projections: List[Dict[str, Any]] = []

        for observation in normalized:
            state_machine = self._get_observability_state_machine(
                observation
            )
            previous_state = self._state_value(state_machine.state)

            state = classify_and_update(
                state_machine,
                observation,
            )
            current_state = self._state_value(state)

            projections.append(
                self._project_observability(
                    observation=observation,
                    state_machine=state_machine,
                    previous_state=previous_state,
                    current_state=current_state,
                )
            )

        return projections

    def observe_health_tick(
        self,
        raw_observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Run exactly one read-only sensor tick and return its health facts."""

        return self.project_sensor_health(
            self.observe_tick(raw_observations)
        )

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

            current_state = self._state_value(state)

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
