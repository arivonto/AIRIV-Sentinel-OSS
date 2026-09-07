"""Gate 4 daemon wiring: inert default and explicit simulated recovery."""

import json
import time

from sentinel.execution import ExecutionResult
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_bounded_autonomous import (
    ARGV,
    COMPONENT,
    BoundedAutonomousSystemdCapability,
)
from sentinel.systemd_remediation_safety import (
    SystemdManagerIdentity,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


UNIT = "airiv-sentinel-production-remediation-probe.service"
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
            raise AssertionError("unexpected Gate 4 snapshot request")
        return self.snapshots.pop(0)


class ForbiddenSnapshot:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise AssertionError("disabled Gate 4 performed host observation")


class FakeArgvExecutor:
    def __init__(self, *, success=True):
        self.calls = []
        self.success = success

    def execute_argv(self, argv, timeout=5.0):
        argv = tuple(argv)
        self.calls.append((argv, timeout))
        now = time.time()
        return ExecutionResult(
            command=json.dumps(list(argv), separators=(",", ":")),
            stdout="FAKE_GATE4_OK" if self.success else "",
            stderr="" if self.success else "FAKE_GATE4_FAILURE",
            exit_code=0 if self.success else 1,
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


def snapshot(
    *,
    invocation,
    pid,
    started,
    active_state="active",
    sub_state="running",
):
    return SystemdUnitSnapshot(
        identity=target(),
        load_state="loaded",
        active_state=active_state,
        sub_state=sub_state,
        unit_file_state="enabled",
        main_pid=pid,
        invocation_id=invocation,
        exec_main_start_timestamp_monotonic=started,
    )


def make_runtime(tmp_path, monkeypatch, *, success=True):
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
    fake = FakeArgvExecutor(success=success)
    runtime.commander.remediation_orchestrator.gate.executor = fake

    runtime.canary_live_execution.cycle = lambda: None
    runtime.production_probe_live_execution.cycle = lambda: None
    runtime.gate3_live_validation.cycle = lambda: None
    runtime.sensor_adapter.process_tick = lambda: []
    runtime.diagnostic.submit = lambda incidents: None

    runtime.running = True
    return runtime, fake


def assert_policy_empty(runtime):
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()
    assert runtime.policy.list_systemd_production_targets() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()


def test_gate4_daemon_wiring_is_observation_inert_by_default(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    forbidden = ForbiddenSnapshot()
    runtime.gate4_autonomous_remediation.snapshot_provider = forbidden

    assert runtime.gate4_autonomous_remediation.capability.enabled is False
    assert runtime.last_gate4_autonomous_result is None

    incidents = runtime.run_once()

    assert incidents == []
    assert forbidden.calls == 0
    assert fake.calls == []
    assert runtime.last_gate4_autonomous_result is None
    assert_policy_empty(runtime)


def test_gate4_enabled_simulation_recovers_unhealthy_exact_probe(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    root = tmp_path / "gate4"

    unhealthy = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
        active_state="failed",
        sub_state="failed",
    )
    recovered = snapshot(
        invocation="b" * 32,
        pid=1001,
        started=200000,
    )
    healthy_next_cycle = snapshot(
        invocation="b" * 32,
        pid=1001,
        started=200000,
    )

    provider = SnapshotSequence(
        unhealthy,
        recovered,
        healthy_next_cycle,
    )
    gate4 = runtime.gate4_autonomous_remediation
    gate4.capability = BoundedAutonomousSystemdCapability(enabled=True)
    gate4.root = root
    gate4.clock = FakeClock()
    gate4.snapshot_provider = provider

    incidents = runtime.run_once()

    assert incidents == []
    result = runtime.last_gate4_autonomous_result
    assert result is not None
    assert result.component_id == COMPONENT
    assert result.final_outcome == "RECOVERED"
    assert result.policy_authorized is True
    assert result.execution_succeeded is True
    assert result.verification_succeeded is True
    assert result.error is None
    assert result.execution_id.startswith("gate4-execution-")

    assert len(fake.calls) == 1
    argv, timeout = fake.calls[0]
    assert argv == ARGV
    assert timeout == 5.0
    assert provider.calls == 2

    assert runtime.incident_manager.get_active_incident(COMPONENT) is None
    history = runtime.incident_manager.get_history()
    assert history[-1]["component_id"] == COMPONENT
    assert history[-1]["final_outcome"] == "RECOVERED"
    assert_policy_empty(runtime)

    evidence = list((root / "trusted_evidence").glob("*.json"))
    outcomes = list(root.glob("outcome-*.json"))
    assert len(evidence) == 1
    assert len(outcomes) == 1

    # Healthy next daemon cycle observes but performs no second remediation.
    runtime.run_once()
    assert provider.calls == 3
    assert len(fake.calls) == 1
    assert_policy_empty(runtime)


def test_gate4_failed_execution_terminalizes_without_automatic_retry(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch, success=False)
    root = tmp_path / "gate4"

    unhealthy = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
        active_state="failed",
        sub_state="failed",
    )
    still_unhealthy = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
        active_state="failed",
        sub_state="failed",
    )

    provider = SnapshotSequence(unhealthy, still_unhealthy)
    gate4 = runtime.gate4_autonomous_remediation
    gate4.capability = BoundedAutonomousSystemdCapability(enabled=True)
    gate4.root = root
    gate4.clock = FakeClock()
    gate4.snapshot_provider = provider

    runtime.run_once()

    result = runtime.last_gate4_autonomous_result
    assert result.final_outcome == "UNRESOLVED"
    assert result.policy_authorized is True
    assert result.execution_succeeded is False
    assert result.verification_succeeded is False
    assert len(fake.calls) == 1
    assert runtime.incident_manager.get_active_incident(COMPONENT) is None
    assert runtime.incident_manager.get_history()[-1]["final_outcome"] == "UNRESOLVED"
    assert_policy_empty(runtime)

    # A subsequent cycle may observe the still unhealthy target, but the
    # durable production-attempt budget must deny execution before a retry.
    runtime.run_once()
    assert len(fake.calls) == 1
    assert runtime.last_gate4_autonomous_result.final_outcome == "UNRESOLVED"
    assert runtime.last_gate4_autonomous_result.policy_authorized is False
    assert_policy_empty(runtime)
