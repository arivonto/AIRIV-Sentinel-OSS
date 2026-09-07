import pytest

from sentinel.live_remediation_safety import TmuxTargetIdentity
from sentinel.runtime import SentinelRuntime
from sentinel.sensors.tmux.parser import TmuxStateParserV11


GEN = "uid=1000;pid=321;start=654"
HASH = "a" * 64


def observation(pane_id="%1"):
    return {
        "source": "TMUX",
        "captured_at": "2026-09-06T00:00:00+00:00",
        "server_socket": "/tmp/tmux-1000/default",
        "server_generation": GEN,
        "session_id": "$1",
        "session_name": "airiv",
        "window_id": "@1",
        "window_index": 0,
        "window_name": "sentinel",
        "pane_index": 0,
        "pane_id": pane_id,
        "pane_active": True,
        "pane_dead": True,
        "current_command": "bash",
        "previous_command": None,
        "pane_pid": 100,
        "capture_ok": True,
        "output_length": 1,
        "output_sha256": HASH,
        "output_changed": False,
        "first_observation": True,
        "tmux_identity": {
            "server_socket": "/tmp/tmux-1000/default",
            "server_generation": GEN,
            "session_id": "$1",
            "session_name": "airiv",
            "window_id": "@1",
            "pane_id": pane_id,
        },
        "tmux_identity_valid": True,
        "agent_identity": None,
    }


def test_sensor_does_not_own_remediation_run_id():
    assert not hasattr(TmuxStateParserV11(), "run_id")


def test_target_from_strong_observation():
    target = TmuxTargetIdentity.from_observation(
        observation(),
        run_id="RUN-1",
    )

    assert target.run_id == "RUN-1"
    assert target.session_id == "$1"
    assert target.window_id == "@1"
    assert target.pane_id == "%1"
    assert target.server_generation == GEN
    assert target.live_eligible


def test_identity_snapshot_tamper_fails_closed():
    raw = observation()
    raw["tmux_identity"] = dict(raw["tmux_identity"])
    raw["tmux_identity"]["window_id"] = "@999"

    with pytest.raises(
        ValueError,
        match="tmux_identity_snapshot_mismatch",
    ):
        TmuxTargetIdentity.from_observation(
            raw,
            run_id="RUN-2",
        )


@pytest.mark.parametrize(
    "key",
    [
        "server_socket",
        "server_generation",
        "session_id",
        "session_name",
        "window_id",
        "pane_id",
        "captured_at",
        "output_sha256",
    ],
)
def test_missing_identity_fails_closed(key):
    raw = observation()
    raw[key] = None

    with pytest.raises(ValueError):
        TmuxTargetIdentity.from_observation(
            raw,
            run_id="RUN-FAIL",
        )


def test_diagnostic_preserves_full_raw_identity(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "diagnostic"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "execution"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "runtime"),
    )

    runtime = SentinelRuntime()
    raw = observation("%strong")

    incident = runtime.incident_manager.evaluate_anomaly(
        observation=raw,
        anomaly_type="PANE_DEAD",
        reason="strong identity preservation",
    )

    investigation = runtime.diagnostic.register_incident(incident)

    saved = runtime.diagnostic.store.get_investigation(
        investigation.investigation_id
    )

    obs = runtime.diagnostic.store.get_observation(
        saved.investigation_id,
        saved.observation_ids[0],
    )

    assert obs.value == {
        "pane_id": "%strong",
        "pane_dead": True,
    }

    assert obs.raw_evidence["session_id"] == "$1"
    assert obs.raw_evidence["session_name"] == "airiv"
    assert obs.raw_evidence["window_id"] == "@1"
    assert obs.raw_evidence["pane_id"] == "%strong"
    assert obs.raw_evidence["server_generation"] == GEN

    target = TmuxTargetIdentity.from_evidence(
        obs.raw_evidence,
        run_id="RUN-PERSISTED",
    )

    assert target.live_eligible
    assert target.pane_id == "%strong"


def test_unavailable_tmux_fails_before_identity_resolution(
    monkeypatch,
):
    parser = TmuxStateParserV11()

    calls = []

    def list_panes(*, server_socket=None):
        calls.append("list")
        return None

    def resolve():
        calls.append("resolve")
        raise AssertionError(
            "identity resolution must not run "
            "after unavailable list-panes"
        )

    monkeypatch.setattr(
        parser,
        "_list_panes",
        list_panes,
    )

    monkeypatch.setattr(
        parser,
        "_resolve_server_identity",
        resolve,
    )

    assert parser.inspect_panes() == []
    assert calls == ["list"]


def test_strong_identity_relists_on_exact_resolved_socket(
    monkeypatch,
):
    parser = TmuxStateParserV11()

    calls = []

    def list_panes(*, server_socket=None):
        calls.append(
            ("list", server_socket)
        )

        return (
            "$1\tairiv\t@1\t0\t"
            "sentinel\t0\t%1\t"
            "1\t1\tbash\t100\n"
        )

    def resolve():
        calls.append(
            ("resolve", None)
        )

        return (
            "/tmp/tmux-1000/default",
            GEN,
        )

    monkeypatch.setattr(
        parser,
        "_list_panes",
        list_panes,
    )

    monkeypatch.setattr(
        parser,
        "_resolve_server_identity",
        resolve,
    )

    monkeypatch.setattr(
        parser,
        "_server_generation_matches",
        lambda socket, generation: True,
    )

    monkeypatch.setattr(
        parser,
        "capture_pane_content",
        lambda pane_id, *, server_socket=None: "x",
    )

    result = parser.inspect_panes()

    assert result

    assert calls[:3] == [
        ("list", None),
        ("resolve", None),
        (
            "list",
            "/tmp/tmux-1000/default",
        ),
    ]

    assert (
        result[0]["server_socket"]
        == "/tmp/tmux-1000/default"
    )

    assert (
        result[0]["server_generation"]
        == GEN
    )

    assert (
        result[0]["tmux_identity_valid"]
        is True
    )
