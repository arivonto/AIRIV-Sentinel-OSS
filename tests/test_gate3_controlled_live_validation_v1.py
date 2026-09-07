"""Gate 3 fake-live CI: daemon wiring, durable Commander path, single effect."""

import json
import time

from sentinel.execution import ExecutionResult
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_gate3_live_validation import (
    APPROVAL_ID,
    COMPONENT,
    UNIT,
    create_gate3_live_request,
)
from sentinel.systemd_remediation_safety import (
    SystemdManagerIdentity,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


BOOT_ID = "11111111-2222-3333-4444-555555555555"


class FakeClock:
    def __init__(self, value=115.0):
        self.value = float(value)

    def __call__(self):
        return self.value


class SnapshotSequence:
    def __init__(self, *snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if not self.snapshots:
            raise AssertionError("unexpected snapshot request")
        return self.snapshots.pop(0)


class FakeArgvExecutor:
    def __init__(self):
        self.calls = []

    def execute_argv(self, argv, timeout=5.0):
        argv = tuple(argv)
        self.calls.append((argv, timeout))
        command = json.dumps(
            list(argv),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        now = time.time()
        return ExecutionResult(
            command=command,
            stdout="FAKE_GATE3_RESTART_OK",
            stderr="",
            exit_code=0,
            started_at=now,
            finished_at=now,
        )


def target():
    return SystemdUnitIdentity(
        manager=SystemdManagerIdentity(
            boot_id=BOOT_ID,
            manager_pid=1,
            manager_start_ticks=123456,
        ),
        unit_name=UNIT,
        fragment_path=(
            "/etc/systemd/system/"
            "airiv-sentinel-production-remediation-probe.service"
        ),
        fragment_sha256="a" * 64,
        fragment_device=100,
        fragment_inode=200,
        fragment_uid=0,
        fragment_gid=0,
    )


def snapshot(*, invocation, pid, started):
    return SystemdUnitSnapshot(
        identity=target(),
        load_state="loaded",
        active_state="active",
        sub_state="running",
        unit_file_state="enabled",
        main_pid=pid,
        invocation_id=invocation,
        exec_main_start_timestamp_monotonic=started,
    )


def make_runtime(tmp_path, monkeypatch):
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
    monkeypatch.setenv(
        "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR",
        str(tmp_path / "production-state"),
    )

    runtime = SentinelRuntime()
    fake = FakeArgvExecutor()
    runtime.commander.remediation_orchestrator.gate.executor = fake

    # Gate 3 is the subject of this test. Other daemon inputs are made inert.
    runtime.canary_live_execution.cycle = lambda: None
    runtime.production_probe_live_execution.cycle = lambda: None
    runtime.sensor_adapter.process_tick = lambda: []
    runtime.diagnostic.submit = lambda incidents: None

    return runtime, fake


def assert_runtime_defaults_empty(runtime):
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()
    assert runtime.policy.list_systemd_production_targets() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()
    assert runtime.systemd_production_execution_dispatch_gate.enabled is False
    assert runtime.systemd_production_runtime_invocation.enabled is False
    assert runtime.systemd_production_runtime_delegation_bridge.enabled is False
    assert runtime.systemd_production_activation_runtime_bridge.enabled is False


def test_gate3_daemon_cycle_executes_exactly_once_and_recovers(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    root = tmp_path / "gate3"
    clock = FakeClock()

    before = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
    )
    after = snapshot(
        invocation="b" * 32,
        pid=1001,
        started=200000,
    )

    request = create_gate3_live_request(
        root=root,
        clock=clock,
        snapshot_provider=lambda: before,
    )
    assert request.approval_id == APPROVAL_ID

    runtime.gate3_live_validation.root = root
    runtime.gate3_live_validation.request_path = root / "gate3-live-request.json"
    runtime.gate3_live_validation.evidence_path = root / "gate3-live-evidence.json"
    runtime.gate3_live_validation.clock = clock
    runtime.gate3_live_validation.snapshot_provider = SnapshotSequence(before, after)

    assert_runtime_defaults_empty(runtime)
    runtime.running = True
    incidents = runtime.run_once()

    assert incidents == []
    evidence = json.loads((root / "gate3-live-evidence.json").read_text())
    assert runtime.last_gate3_live_result is not None, evidence["error"]
    assert runtime.last_gate3_live_result.final_outcome == "RECOVERED"
    assert len(fake.calls) == 1
    argv, timeout = fake.calls[0]
    assert argv == (
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        UNIT,
    )
    assert timeout == 5.0

    assert not (root / "gate3-live-request.json").exists()
    assert evidence["terminal_outcome"] == "TERMINAL_SUCCESS"
    assert evidence["approval_id"] == APPROVAL_ID
    assert evidence["component_id"] == COMPONENT
    assert evidence["pre_invocation_id"] == "a" * 32
    assert evidence["post_invocation_id"] == "b" * 32
    assert evidence["policy_authorized"] is True
    assert evidence["execution_succeeded"] is True
    assert evidence["verification_succeeded"] is True
    assert evidence["final_outcome"] == "RECOVERED"
    assert evidence["cleanup_empty"] is True

    assert len(list((root / "issuance").glob("*.json"))) == 1
    assert len(list((root / "consumption").glob("*.json"))) == 1
    assert runtime.incident_manager.get_active_incident(COMPONENT) is None
    assert runtime.incident_manager.get_history()[-1]["final_outcome"] == "RECOVERED"
    assert_runtime_defaults_empty(runtime)

    # Consumed inbox means the next daemon cycle cannot replay the effect.
    runtime.run_once()
    assert len(fake.calls) == 1
    assert_runtime_defaults_empty(runtime)


def test_gate3_mid_path_failure_terminalizes_owned_incident(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    root = tmp_path / "gate3"
    clock = FakeClock()

    before = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
    )

    create_gate3_live_request(
        root=root,
        clock=clock,
        snapshot_provider=lambda: before,
    )

    runtime.gate3_live_validation.root = root
    runtime.gate3_live_validation.request_path = root / "gate3-live-request.json"
    runtime.gate3_live_validation.evidence_path = root / "gate3-live-evidence.json"
    runtime.gate3_live_validation.clock = clock
    runtime.gate3_live_validation.snapshot_provider = SnapshotSequence(before)

    def fail_prepare(*args, **kwargs):
        raise ValueError("synthetic_gate3_mid_path_failure")

    monkeypatch.setattr(
        runtime.systemd_production_preparation,
        "prepare",
        fail_prepare,
    )

    assert_runtime_defaults_empty(runtime)
    runtime.running = True

    incidents = runtime.run_once()

    assert incidents == []
    evidence = json.loads(
        (root / "gate3-live-evidence.json").read_text()
    )

    assert evidence["terminal_outcome"] == "TERMINAL_FAILURE"
    assert (
        evidence["error"]
        == "ValueError:synthetic_gate3_mid_path_failure"
    )
    assert evidence["cleanup_empty"] is True
    assert fake.calls == []

    assert (
        runtime.incident_manager.get_active_incident(COMPONENT)
        is None
    )

    history = runtime.incident_manager.get_history()
    assert len(history) == 1
    assert history[-1]["component_id"] == COMPONENT
    assert history[-1]["lifecycle_state"] == "TERMINAL"
    assert history[-1]["final_outcome"] == "UNRESOLVED"

    assert_runtime_defaults_empty(runtime)


def test_gate3_preexisting_incident_is_not_owned_or_terminalized(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    root = tmp_path / "gate3"
    clock = FakeClock()

    existing = runtime.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": COMPONENT,
            "agent_identity": "EXISTING_OWNER",
        },
        anomaly_type="PREEXISTING_INCIDENT",
        reason="Existing incident must remain untouched.",
    )
    runtime.incident_manager.investigate(COMPONENT)

    before = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
    )

    create_gate3_live_request(
        root=root,
        clock=clock,
        snapshot_provider=lambda: before,
    )

    runtime.gate3_live_validation.root = root
    runtime.gate3_live_validation.request_path = root / "gate3-live-request.json"
    runtime.gate3_live_validation.evidence_path = root / "gate3-live-evidence.json"
    runtime.gate3_live_validation.clock = clock
    runtime.gate3_live_validation.snapshot_provider = SnapshotSequence(before)

    assert_runtime_defaults_empty(runtime)
    runtime.running = True

    incidents = runtime.run_once()

    assert incidents == []

    evidence = json.loads(
        (root / "gate3-live-evidence.json").read_text()
    )

    assert evidence["terminal_outcome"] == "TERMINAL_FAILURE"
    assert (
        evidence["error"]
        == "ValueError:gate3_probe_has_existing_active_incident"
    )

    assert (
        runtime.incident_manager.get_active_incident(COMPONENT)
        is existing
    )
    assert existing.status == "INVESTIGATING"
    assert runtime.incident_manager.get_history() == []
    assert fake.calls == []

    assert_runtime_defaults_empty(runtime)


def test_gate3_absent_request_is_completely_inert(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    root = tmp_path / "missing-gate3-root"
    runtime.gate3_live_validation.root = root
    runtime.gate3_live_validation.request_path = root / "gate3-live-request.json"
    runtime.gate3_live_validation.evidence_path = root / "gate3-live-evidence.json"

    assert runtime.gate3_live_validation.cycle() is None
    assert fake.calls == []
    assert not root.exists()
    assert_runtime_defaults_empty(runtime)


def test_gate3_request_creation_performs_no_effect(
    tmp_path,
):
    root = tmp_path / "gate3"
    before = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
    )
    request = create_gate3_live_request(
        root=root,
        clock=FakeClock(),
        snapshot_provider=lambda: before,
    )
    assert request.approval_id == APPROVAL_ID
    assert (root / "gate3-live-request.json").exists()
    assert not (root / "gate3-live-evidence.json").exists()
    assert not (root / "issuance").exists()
    assert not (root / "consumption").exists()
