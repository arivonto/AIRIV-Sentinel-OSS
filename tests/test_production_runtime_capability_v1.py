"""Production capability integration, with isolated persistence and sensor I/O."""

import ast
from dataclasses import fields, replace
import inspect
import runpy
import subprocess
import sys
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from sentinel.runtime import SentinelRuntime
from sentinel.worker import (
    DaemonState, HealthMonitor, OperationalDaemon, RuntimeScheduler,
    RuntimeSupervisor, WorkerProtocol, WorkerState, WorkerTransitionError,
)
from sentinel.worker import capability_worker as module, composition, entrypoint
from sentinel.worker.capability_worker import SentinelCapabilityWorker
from sentinel.worker.composition import build_production_supervision


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from sentinel.worker import observability
    monkeypatch.setattr(observability, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("AIRIV_SENTINEL_DIAGNOSTIC_DIR", str(tmp_path / "diagnostic"))
    return SentinelRuntime()


def join_worker(worker):
    if worker.state() is WorkerState.RUNNING:
        worker.stop()
    if worker._thread is not None:
        worker._thread.join(2)
        assert not worker._thread.is_alive()


def test_one_runtime_and_unchanged_authorities(runtime, monkeypatch):
    original = vars(runtime).copy()
    diagnostic = vars(runtime.diagnostic).copy()
    monkeypatch.setattr(SentinelRuntime, "__init__", Mock(side_effect=AssertionError))
    bundle = build_production_supervision(runtime, entrypoint.build_production_config())
    assert bundle.runtime is bundle.runtime_worker.runtime is bundle.capability_worker.runtime
    assert vars(runtime) == original
    observer = runtime.diagnostic.decision_observer
    assert observer.__self__ is bundle.capability_worker._observability
    assert observer.__name__ == "commander_decision"
    assert {key: value for key, value in vars(runtime.diagnostic).items()
            if key != "decision_observer"} == {
                key: value for key, value in diagnostic.items()
                if key != "decision_observer"}
    manager = runtime.incident_manager
    assert runtime.sensor_adapter.bridge.incident_manager is manager
    assert runtime.commander.incident_manager is manager
    assert runtime.diagnostic.incident_manager is manager
    assert runtime.diagnostic.commander_handoff.commander is runtime.commander
    assert bundle.registry.worker_ids() == (
        bundle.runtime_worker.worker_id(), bundle.capability_worker.worker_id(),
    )
    assert type(bundle.health_monitor) is HealthMonitor
    assert type(bundle.supervisor) is RuntimeSupervisor
    assert type(bundle.daemon) is OperationalDaemon
    assert RuntimeScheduler(bundle.daemon)._daemon is bundle.daemon
    assert bundle.health_monitor._registry is bundle.registry
    assert bundle.supervisor._health_monitor is bundle.health_monitor
    assert bundle.daemon._supervisor is bundle.supervisor
    assert runtime.diagnostic.commander_semantic_policy.list_triggers() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.diagnostic.remediation_action_catalog is runtime.remediation_action_catalog
    facts = runtime.diagnostic.commander_semantic_policy.assess("UNKNOWN_PRODUCTION_INPUT")
    assert not facts.configured and not facts.remediation_required
    assert facts.commander_action_required


def test_worker_lifecycle_protocol_and_passive_heartbeat(runtime):
    runtime.running = True
    worker = SentinelCapabilityWorker(runtime, interval=60)
    assert isinstance(worker, WorkerProtocol)
    assert worker.worker_id().value == "sentinel.capability"
    assert worker.worker_id() is SentinelCapabilityWorker(runtime).worker_id()
    assert worker.state() is WorkerState.REGISTERED
    assert worker.last_error is worker.last_cycle_at is worker.last_cycle_status is None
    with pytest.raises(WorkerTransitionError):
        worker.stop()
    for _ in range(2):
        worker.start()
        try:
            assert worker.state() is WorkerState.RUNNING
            assert not worker._thread.daemon
            with pytest.raises(WorkerTransitionError):
                worker.start()
            first, second = worker.heartbeat(), worker.heartbeat()
            assert first.iteration == second.iteration == 0
            assert second.healthy
            assert {field.name for field in fields(second)} == {
                "worker_id", "state", "timestamp", "uptime", "iteration", "healthy",
            }
        finally:
            join_worker(worker)
        assert worker.state() is WorkerState.STOPPED
        assert not worker.health()
        assert runtime.running  # Runtime lifecycle belongs to its other worker.


@pytest.mark.parametrize("name", ["interval", "shutdown_timeout"])
@pytest.mark.parametrize("value", [0, -1, True, None, float("inf"), float("nan")])
def test_invalid_timing(runtime, name, value):
    with pytest.raises(ValueError, match=name):
        SentinelCapabilityWorker(runtime, **{name: value})


def test_start_requires_running_runtime(runtime):
    worker = SentinelCapabilityWorker(runtime)
    with pytest.raises(RuntimeError, match="started"):
        worker.start()
    assert worker.state() is WorkerState.FAILED
    assert worker._thread is None


def test_thread_start_failure_surfaces(runtime, monkeypatch):
    runtime.running = True
    worker = SentinelCapabilityWorker(runtime)
    monkeypatch.setattr(Thread, "start", Mock(side_effect=RuntimeError("private payload")))
    with pytest.raises(RuntimeError):
        worker.start()
    assert worker.state() is WorkerState.FAILED
    assert worker.last_error == "RuntimeError"


def test_cycles_are_serial_and_each_waits_interval(runtime, monkeypatch):
    runtime.running = True
    worker = SentinelCapabilityWorker(runtime, interval=0.25)
    order = []

    def wait(interval):
        assert interval == 0.25
        order.append("wait")
        return len(order) == 5

    def cycle():
        order.append("cycle")
        assert worker.heartbeat().iteration == order.count("cycle")

    monkeypatch.setattr(worker._stop_event, "wait", wait)
    monkeypatch.setattr(runtime, "run_once", cycle)
    worker.start()
    worker._thread.join(2)
    try:
        assert not worker._thread.is_alive()
        assert order == ["wait", "cycle", "wait", "cycle", "wait"]
        assert worker.heartbeat().iteration == 2
        assert worker.last_cycle_status == "OK"
        assert worker.last_cycle_at.tzinfo is not None
    finally:
        worker.stop()


@pytest.mark.parametrize("error", [RuntimeError("private sensor data"), KeyboardInterrupt()])
def test_cycle_exception_fails_and_can_restart_after_exit(runtime, monkeypatch, error):
    runtime.running = True
    worker = SentinelCapabilityWorker(runtime, interval=0.001)
    cycle = Mock(side_effect=error)
    monkeypatch.setattr(runtime, "run_once", cycle)
    worker.start()
    worker._thread.join(2)
    assert not worker._thread.is_alive()
    assert worker.state() is WorkerState.FAILED
    assert not worker.heartbeat().healthy
    assert worker.heartbeat().iteration == 1
    assert worker.last_error == type(error).__name__
    assert worker.last_cycle_status == "FAILED"
    cycle.assert_called_once_with()
    cycle.side_effect = None
    worker.start()
    join_worker(worker)


def test_stop_waits_for_inflight_cycle_without_holding_lifecycle_lock(runtime, monkeypatch):
    runtime.running = True
    entered, release = Event(), Event()
    worker = SentinelCapabilityWorker(runtime, interval=0.001)

    def cycle():
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(runtime, "run_once", cycle)
    worker.start()
    errors = []

    def stop():
        try:
            worker.stop()
        except BaseException as error:
            errors.append(error)

    stopper = Thread(target=stop)
    try:
        assert entered.wait(2)
        stopper.start()
        assert worker._stop_event.wait(2)
        assert worker.heartbeat().state is WorkerState.STOPPING
        with pytest.raises(WorkerTransitionError):
            worker.start()
    finally:
        release.set()
        stopper.join(2)
        join_worker(worker)
    assert not errors
    assert not stopper.is_alive()
    assert worker.state() is WorkerState.STOPPED
    assert worker.heartbeat().iteration == 1


def test_shutdown_timeout_is_explicit_and_cannot_start_overlapping_thread(runtime, monkeypatch):
    runtime.running = True
    entered, release = Event(), Event()
    worker = SentinelCapabilityWorker(runtime, interval=0.001, shutdown_timeout=0.001)

    def cycle():
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(runtime, "run_once", cycle)
    worker.start()
    try:
        assert entered.wait(2)
        with pytest.raises(RuntimeError, match="timed out"):
            worker.stop()
        assert worker.state() is WorkerState.FAILED
        with pytest.raises(WorkerTransitionError, match="still active"):
            worker.start()
    finally:
        release.set()
        worker._thread.join(2)
    assert not worker._thread.is_alive()


@pytest.mark.parametrize("unavailable", [
    FileNotFoundError(), subprocess.CalledProcessError(1, "tmux"),
    subprocess.TimeoutExpired("tmux", 10),
])
def test_python_m_sentinel_reaches_real_headless_cycle(runtime, monkeypatch, unavailable):
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
                 "XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "GNOME_DESKTOP_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    sensor_calls = []

    def sensor(command, **kwargs):
        assert command[0] == "tmux"
        assert command[1] == "list-panes"
        assert kwargs["timeout"] == 10
        sensor_calls.append(command)
        raise unavailable

    monkeypatch.setattr(subprocess, "run", sensor)
    constructor = Mock(return_value=runtime)
    monkeypatch.setattr(entrypoint, "SentinelRuntime", constructor)
    config = replace(entrypoint.build_production_config(), daemon_cycle_interval=0.01)
    monkeypatch.setattr(entrypoint, "build_production_config", lambda: config)
    real_compose = entrypoint.build_runtime_supervision
    assert real_compose is build_production_supervision
    bundles = []
    completed = Event()
    run_once = runtime.run_once

    def cycle():
        result = run_once()
        assert result == []
        completed.set()
        return result

    monkeypatch.setattr(runtime, "run_once", cycle)

    def compose(supplied, supplied_config):
        bundle = real_compose(supplied, supplied_config)
        bundles.append(bundle)

        def wait(interval):
            assert completed.wait(2)
            assert bundle.runtime_worker.health()
            assert bundle.capability_worker.health()
            bundle.daemon.request_stop()
            return True

        monkeypatch.setattr(bundle.daemon._stop_event, "wait", wait)
        return bundle

    monkeypatch.setattr(entrypoint, "build_runtime_supervision", compose)
    monkeypatch.delitem(sys.modules, "sentinel.__main__", raising=False)
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("sentinel.__main__", run_name="__main__")
    assert caught.value.code == 0
    constructor.assert_called_once_with()
    assert sensor_calls
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.daemon.state is DaemonState.STOPPED
    assert bundle.capability_worker.state() is WorkerState.STOPPED
    assert bundle.runtime_worker.state() is WorkerState.STOPPED
    assert not bundle.capability_worker._thread.is_alive()
    assert not runtime.running


def test_canonical_observation_reaches_single_incident_and_investigation(runtime, monkeypatch):
    runtime.running = True
    # Isolate diagnostics scheduling; use the actual canonical submit boundary.
    monkeypatch.setattr(runtime.sensor_adapter.parser, "inspect_panes", lambda: [{
        "source": "TMUX", "captured_at": "2026-09-06T00:00:00+00:00",
        "pane_id": "%capability-test", "pane_dead": True, "capture_ok": False,
        "current_command": "bash", "window_name": "test", "first_observation": True,
    }])
    for owner, name in ((runtime.policy, "evaluate"),
                        (runtime.incident_manager, "resolve"),
                        (runtime.diagnostic.commander_semantic_policy, "assess")):
        monkeypatch.setattr(owner, name, Mock(side_effect=AssertionError("driver bypassed boundary")))
    worker = SentinelCapabilityWorker(runtime, interval=0.01)
    waits = iter([False, True])
    monkeypatch.setattr(worker._stop_event, "wait", lambda interval: next(waits))
    worker.start()
    worker._thread.join(2)
    try:
        assert worker.last_cycle_status == "OK"
        incident = runtime.incident_manager.get_active_incident("%capability-test")
        assert incident is not None
        assert incident.final_outcome is None
        assert len(runtime.diagnostic._investigation_by_incident) == 1
        assert incident.incident_id in runtime.diagnostic._investigation_by_incident
        assert worker.heartbeat().iteration == 1
    finally:
        join_worker(worker)


def test_structural_authority_and_host_operation_audit():
    source = inspect.getsource(module)
    tree = ast.parse(source)
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == "Thread" for node in ast.walk(tree)) == 1
    attrs = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
    assert attrs.count("run_once") == 1
    assert "sleep" not in attrs
    for target in (module, composition, entrypoint):
        source = inspect.getsource(target)
        for forbidden in ("IncidentManager(", "CommanderOrchestrator(",
                          "RuntimeDiagnosticCoordinator(", "evaluate_anomaly(",
                          ".resolve(", ".remediate(", "systemctl", "subprocess",
                          "DISPLAY", "wmctrl", "xdotool"):
            assert forbidden not in source
