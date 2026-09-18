"""Focused S1 tests for the canonical sensor observability path."""

from sentinel.normalization.resolver import IdentityResolver
from sentinel.runtime_sensor_adapter import (
    SENSOR_OBSERVABILITY_SCHEMA,
    RuntimeSensorAdapter,
)


class FakeParser:
    def __init__(self, observations):
        self.observations = observations
        self.calls = 0

    def inspect_panes(self):
        self.calls += 1
        return [dict(item) for item in self.observations]


class ForcedActivityDetector:
    def __init__(self, result="OUTPUT_CHANGED"):
        self.result = result
        self.seen = []

    def classify_activity(self, observation):
        self.seen.append(dict(observation))
        return self.result


def observation(
    *,
    pane_id="%1",
    window_name="worker-a",
    captured_at="2026-09-10T00:00:00+00:00",
    first_observation=True,
    current_command="pytest",
    previous_command=None,
    output_changed=False,
    capture_ok=True,
    pane_dead=False,
    tmux_identity_valid=True,
):
    return {
        "source": "TMUX",
        "captured_at": captured_at,
        "server_socket": "/tmp/private-tmux.sock",
        "server_generation": "uid=1000;pid=1234;start=987654",
        "session_id": "$1",
        "session_name": "airiv",
        "window_id": "@1",
        "window_index": 0,
        "window_name": window_name,
        "pane_id": pane_id,
        "pane_index": 0,
        "pane_pid": 4321,
        "pane_dead": pane_dead,
        "capture_ok": capture_ok,
        "first_observation": first_observation,
        "current_command": current_command,
        "previous_command": previous_command,
        "output_changed": output_changed,
        "output_sha256": "a" * 64,
        "tmux_identity": {
            "server_socket": "/tmp/private-tmux.sock",
            "server_generation": "uid=1000;pid=1234;start=987654",
            "session_id": "$1",
            "session_name": "airiv",
            "window_id": "@1",
            "pane_id": pane_id,
        },
        "tmux_identity_valid": tmux_identity_valid,
    }


def build_adapter(parser, activity_detector=None):
    return RuntimeSensorAdapter(
        parser=parser,
        identity_resolver=IdentityResolver({"worker-a": "agent-a"}),
        activity_detector=activity_detector,
        # A plain object proves the read-only path has no bridge dependency.
        bridge=object(),
    )


def test_normalization_honors_injected_activity_detector():
    detector = ForcedActivityDetector("PROCESS_CHANGED")
    adapter = build_adapter(FakeParser([]), activity_detector=detector)
    raw = observation(first_observation=False)

    normalized = adapter.normalize([raw])

    assert len(detector.seen) == 1
    assert detector.seen[0]["pane_id"] == "%1"
    assert normalized[0]["agent_identity"] == "agent-a"
    assert normalized[0]["activity_state"] == "PROCESS_CHANGED"


def test_observe_tick_collects_normalizes_resolves_and_projects_state_read_only():
    parser = FakeParser([observation()])
    adapter = build_adapter(parser)

    # A plain object proves observe_tick never calls incident verification.
    adapter.contract_verifier = object()

    result = adapter.observe_tick()

    assert parser.calls == 1
    assert result == [
        {
            "schema": SENSOR_OBSERVABILITY_SCHEMA,
            "source": "TMUX",
            "observed_at": "2026-09-10T00:00:00+00:00",
            "component_id": "%1",
            "agent_identity": "agent-a",
            "activity_state": "INITIALIZED",
            "state_input": {
                "activity_state": "INITIALIZED",
                "output_changed": False,
                "completion_evidence": None,
                "waiting_evidence": None,
            },
            "previous_state": "IDLE",
            "current_state": "OBSERVING",
            "state_transitioned": True,
            "job_type": "PYTEST",
            "sensor_facts": {
                "capture_ok": True,
                "first_observation": True,
                "output_changed": False,
                "pane_dead": False,
                "tmux_identity_valid": True,
            },
        }
    ]

    projection = result[0]
    assert "current_command" not in projection
    assert "server_socket" not in projection
    assert "server_generation" not in projection
    assert "output_sha256" not in projection
    assert "tmux_identity" not in projection


def test_observe_tick_exposes_activity_driven_state_transition_per_component():
    adapter = build_adapter(FakeParser([]))
    adapter.contract_verifier = object()

    initialized = adapter.observe_tick([observation()])[0]
    active = adapter.observe_tick(
        [
            observation(
                first_observation=False,
                current_command="python",
                previous_command="bash",
                output_changed=False,
                captured_at="2026-09-10T00:00:01+00:00",
            )
        ]
    )[0]
    second_component = adapter.observe_tick(
        [
            observation(
                pane_id="%2",
                captured_at="2026-09-10T00:00:02+00:00",
            )
        ]
    )[0]

    assert initialized["current_state"] == "OBSERVING"
    assert active["activity_state"] == "PROCESS_CHANGED"
    assert active["previous_state"] == "OBSERVING"
    assert active["current_state"] == "TASK_ACTIVE"
    assert active["state_transitioned"] is True
    assert second_component["previous_state"] == "IDLE"
    assert second_component["current_state"] == "OBSERVING"
    assert set(adapter.observability_state_machines) == {"%1", "%2"}
    assert adapter.state_machines == {}


def test_observability_projection_preserves_unknown_sensor_facts():
    adapter = build_adapter(FakeParser([]))
    adapter.contract_verifier = object()

    result = adapter.observe_tick(
        [
            observation(
                capture_ok=None,
                tmux_identity_valid=None,
            )
        ]
    )[0]

    assert result["sensor_facts"]["capture_ok"] is None
    assert result["sensor_facts"]["tmux_identity_valid"] is None
    assert result["state_input"]["completion_evidence"] is None
    assert result["state_input"]["waiting_evidence"] is None


def test_same_fixed_initial_observation_projects_same_semantics():
    raw = observation()

    first = build_adapter(FakeParser([]))
    first.contract_verifier = object()
    second = build_adapter(FakeParser([]))
    second.contract_verifier = object()

    assert first.observe_tick([raw]) == second.observe_tick([raw])
