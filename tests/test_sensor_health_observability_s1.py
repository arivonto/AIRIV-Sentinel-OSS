"""Focused S1 tests for read-only TMUX sensor health projection."""

from sentinel.normalization.resolver import IdentityResolver
from sentinel.runtime_sensor_adapter import (
    SENSOR_HEALTH_SCHEMA,
    RuntimeSensorAdapter,
)


class FakeParser:
    def __init__(self, observations):
        self.observations = observations
        self.calls = 0

    def inspect_panes(self):
        self.calls += 1
        return [dict(item) for item in self.observations]


def observation(
    *,
    pane_id,
    window_name,
    captured_at,
    capture_ok,
    pane_dead,
    tmux_identity_valid,
    first_observation,
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
        "current_command": "bash",
        "previous_command": "bash",
        "output_changed": False,
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


def build_adapter(observations):
    parser = FakeParser(observations)
    adapter = RuntimeSensorAdapter(
        parser=parser,
        identity_resolver=IdentityResolver({"worker-a": "agent-a"}),
        # Plain objects prove the health path cannot call these authorities.
        bridge=object(),
    )
    adapter.contract_verifier = object()
    return adapter, parser


def test_observe_health_tick_summarizes_explicit_sensor_facts_without_policy():
    adapter, parser = build_adapter(
        [
            observation(
                pane_id="%1",
                window_name="worker-a",
                captured_at="2026-09-10T00:00:00+00:00",
                capture_ok=True,
                pane_dead=False,
                tmux_identity_valid=True,
                first_observation=True,
            ),
            observation(
                pane_id="%2",
                window_name="worker-b",
                captured_at="2026-09-10T00:00:01+00:00",
                capture_ok=False,
                pane_dead=True,
                tmux_identity_valid=False,
                first_observation=False,
            ),
            observation(
                pane_id="%3",
                window_name="worker-b",
                captured_at="2026-09-10T00:00:02+00:00",
                capture_ok=None,
                pane_dead=None,
                tmux_identity_valid=None,
                first_observation=False,
            ),
        ]
    )

    result = adapter.observe_health_tick()

    assert parser.calls == 1
    assert result == {
        "schema": SENSOR_HEALTH_SCHEMA,
        "sources": ["TMUX"],
        "observation_times": [
            "2026-09-10T00:00:00+00:00",
            "2026-09-10T00:00:01+00:00",
            "2026-09-10T00:00:02+00:00",
        ],
        "observation_count": 3,
        "distinct_component_count": 3,
        "component_identity": {"present": 3, "unknown": 0},
        "agent_identity": {"resolved": 1, "unknown": 2},
        "activity_counts": {
            "INITIALIZED": 1,
            "OUTPUT_SILENT": 1,
            "PANE_DEAD": 1,
        },
        "state_counts": {
            "FAILED": 1,
            "IDLE": 1,
            "OBSERVING": 1,
        },
        "capture_ok": {"true": 1, "false": 1, "unknown": 1},
        "tmux_identity_valid": {"true": 1, "false": 1, "unknown": 1},
        "pane_dead": {"true": 1, "false": 1, "unknown": 1},
        "state_transitioned": {"true": 2, "false": 1, "unknown": 0},
    }

    # No policy/readiness verdict and no host-private/raw command material.
    assert "status" not in result
    assert "ready" not in result
    assert "component_ids" not in result
    assert "current_command" not in result
    assert "server_socket" not in result
    assert "tmux_identity" not in result


def test_empty_sensor_tick_remains_empty_instead_of_manufacturing_health():
    adapter, parser = build_adapter([])

    result = adapter.observe_health_tick()

    assert parser.calls == 1
    assert result["observation_count"] == 0
    assert result["distinct_component_count"] == 0
    assert result["sources"] == []
    assert result["observation_times"] == []
    assert result["activity_counts"] == {}
    assert result["state_counts"] == {}
    assert result["capture_ok"] == {"true": 0, "false": 0, "unknown": 0}
    assert result["agent_identity"] == {"resolved": 0, "unknown": 0}
    assert "status" not in result


def test_malformed_projection_facts_are_counted_as_unknown_not_healthy():
    result = RuntimeSensorAdapter.project_sensor_health(
        [
            {
                "source": None,
                "observed_at": None,
                "component_id": None,
                "agent_identity": {},
                "activity_state": None,
                "current_state": 123,
                "state_transitioned": None,
                "sensor_facts": "malformed",
            }
        ]
    )

    assert result["sources"] == []
    assert result["observation_times"] == []
    assert result["distinct_component_count"] == 0
    assert result["component_identity"] == {"present": 0, "unknown": 1}
    assert result["agent_identity"] == {"resolved": 0, "unknown": 1}
    assert result["activity_counts"] == {"UNKNOWN": 1}
    assert result["state_counts"] == {"UNKNOWN": 1}
    assert result["capture_ok"] == {"true": 0, "false": 0, "unknown": 1}
    assert result["tmux_identity_valid"] == {
        "true": 0,
        "false": 0,
        "unknown": 1,
    }
    assert result["pane_dead"] == {"true": 0, "false": 0, "unknown": 1}
    assert result["state_transitioned"] == {
        "true": 0,
        "false": 0,
        "unknown": 1,
    }


def test_fixed_sensor_health_inputs_project_deterministically():
    raw = [
        observation(
            pane_id="%1",
            window_name="worker-a",
            captured_at="2026-09-10T00:00:00+00:00",
            capture_ok=True,
            pane_dead=False,
            tmux_identity_valid=True,
            first_observation=True,
        )
    ]

    first, _ = build_adapter(raw)
    second, _ = build_adapter(raw)

    assert first.observe_health_tick() == second.observe_health_tick()
