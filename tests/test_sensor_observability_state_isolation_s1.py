"""Lane 1 regression tests for passive observability state isolation."""

from sentinel.normalization.resolver import IdentityResolver
from sentinel.runtime_sensor_adapter import RuntimeSensorAdapter


GEN_A = "uid=1000;pid=1234;start=111"
GEN_B = "uid=1000;pid=5678;start=222"


def observation(
    *,
    generation=GEN_A,
    pane_id="%1",
    window_id="@1",
    first_observation=True,
    current_command="pytest",
    previous_command=None,
    output_changed=False,
    tmux_identity_valid=True,
):
    return {
        "source": "TMUX",
        "captured_at": "2026-09-10T00:00:00+00:00",
        "server_socket": "/tmp/private-tmux.sock",
        "server_generation": generation,
        "session_id": "$1",
        "session_name": "airiv",
        "window_id": window_id,
        "window_index": 0,
        "window_name": "worker-a",
        "pane_id": pane_id,
        "pane_index": 0,
        "pane_pid": 4321,
        "pane_dead": False,
        "capture_ok": True,
        "first_observation": first_observation,
        "current_command": current_command,
        "previous_command": previous_command,
        "output_changed": output_changed,
        "output_sha256": "a" * 64,
        "tmux_identity": {
            "server_socket": "/tmp/private-tmux.sock",
            "server_generation": generation,
            "session_id": "$1",
            "session_name": "airiv",
            "window_id": window_id,
            "pane_id": pane_id,
        },
        "tmux_identity_valid": tmux_identity_valid,
    }


def build_adapter():
    return RuntimeSensorAdapter(
        identity_resolver=IdentityResolver({"worker-a": "agent-a"}),
        bridge=object(),
    )


def test_observe_tick_cannot_mutate_canonical_process_state_store():
    adapter = build_adapter()
    canonical = adapter._get_state_machine("%1")
    canonical.state = "FAILED"

    projection = adapter.observe_tick([observation()])[0]

    assert projection["previous_state"] == "IDLE"
    assert projection["current_state"] == "OBSERVING"
    assert adapter.state_machines["%1"] is canonical
    assert canonical.state == "FAILED"
    assert adapter.observability_state_machines["%1"] is not canonical


def test_observability_state_is_retained_for_same_strong_identity():
    adapter = build_adapter()

    initialized = adapter.observe_tick([observation()])[0]
    active = adapter.observe_tick(
        [
            observation(
                first_observation=False,
                current_command="python",
                previous_command="bash",
            )
        ]
    )[0]

    assert initialized["previous_state"] == "IDLE"
    assert initialized["current_state"] == "OBSERVING"
    assert active["previous_state"] == "OBSERVING"
    assert active["current_state"] == "TASK_ACTIVE"
    assert set(adapter.observability_state_machines) == {"%1"}


def test_reused_pane_id_in_new_tmux_generation_resets_observability_state():
    adapter = build_adapter()

    adapter.observe_tick([observation()])
    active = adapter.observe_tick(
        [
            observation(
                first_observation=False,
                current_command="python",
                previous_command="bash",
            )
        ]
    )[0]
    restarted = adapter.observe_tick(
        [
            observation(
                generation=GEN_B,
                first_observation=True,
            )
        ]
    )[0]

    assert active["current_state"] == "TASK_ACTIVE"
    assert restarted["previous_state"] == "IDLE"
    assert restarted["current_state"] == "OBSERVING"
    assert adapter._observability_state_identities["%1"][0] == GEN_B


def test_unvalidated_tmux_identity_is_ephemeral_and_cannot_poison_next_tick():
    adapter = build_adapter()
    weak = observation(
        first_observation=False,
        current_command="python",
        previous_command="bash",
        tmux_identity_valid=False,
    )

    first = adapter.observe_tick([weak])[0]
    second = adapter.observe_tick([weak])[0]
    strong = adapter.observe_tick([observation()])[0]

    assert first["activity_state"] == "PROCESS_CHANGED"
    assert first["previous_state"] == "IDLE"
    assert first["current_state"] == "TASK_ACTIVE"
    assert second["previous_state"] == "IDLE"
    assert second["current_state"] == "TASK_ACTIVE"
    assert strong["previous_state"] == "IDLE"
    assert strong["current_state"] == "OBSERVING"
    assert set(adapter.observability_state_machines) == {"%1"}
    assert adapter.state_machines == {}
