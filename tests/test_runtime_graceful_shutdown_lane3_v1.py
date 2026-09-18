"""Lane 3 proofs for deterministic graceful shutdown and passive liveness."""

from types import SimpleNamespace
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from sentinel.runtime import SentinelRuntime
from sentinel.runtime_reliability import RuntimeShutdownInProgressError
from sentinel.worker import (
    RestartPolicy,
    RuntimeState,
    RuntimeSupervisionConfig,
    SentinelRuntimeWorker,
    WorkerId,
    WorkerShutdownError,
    WorkerState,
)
from sentinel.worker.composition import build_production_supervision


def test_passive_health_read_does_not_block_stop_or_leak_stale_healthy():
    runtime = Mock(spec=SentinelRuntime)
    worker = SentinelRuntimeWorker(runtime, WorkerId("sentinel.runtime"))
    worker.start()

    entered = Event()
    release = Event()
    health_results = []
    observer_errors = []
    stop_errors = []

    def blocked_health_snapshot():
        entered.set()
        assert release.wait(2)
        # Deliberately stale: the read began while the worker was RUNNING.
        return SimpleNamespace(running=True)

    runtime.get_runtime_health.side_effect = blocked_health_snapshot

    def observe_health():
        try:
            health_results.append(worker.health())
        except BaseException as error:
            observer_errors.append(error)

    def stop_worker():
        try:
            worker.stop()
        except BaseException as error:
            stop_errors.append(error)

    observer = Thread(target=observe_health)
    stopper = Thread(target=stop_worker)
    observer.start()
    assert entered.wait(2)

    # health() must not retain the worker lock while the passive runtime read is
    # blocked. Shutdown therefore completes before that stale read is released.
    stopper.start()
    stopper.join(1)
    assert not stopper.is_alive()
    assert observer.is_alive()
    assert worker.state() is WorkerState.STOPPED
    assert not stop_errors
    runtime.stop.assert_called_once_with()

    release.set()
    observer.join(2)
    assert not observer.is_alive()
    assert not observer_errors
    # The post-read state reconciliation must reject the stale RUNNING snapshot.
    assert health_results == [False]
    assert not worker.health()


def test_production_supervisor_quiesces_inflight_cycle_before_runtime_stop(
    tmp_path,
    monkeypatch,
):
    from sentinel.worker import observability

    monkeypatch.setattr(observability, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("AIRIV_SENTINEL_DIAGNOSTIC_DIR", str(tmp_path / "diagnostic"))

    runtime = SentinelRuntime()
    config = RuntimeSupervisionConfig(
        worker_id=WorkerId("sentinel.runtime"),
        worker_name="Sentinel runtime",
        worker_version="1",
        worker_description="Lane 3 shutdown proof",
        daemon_cycle_interval=0.001,
        health_stale_after=30,
        restart_policy=RestartPolicy(0, 0, 0),
    )
    bundle = build_production_supervision(runtime, config)

    entered = Event()
    release = Event()
    cycle_finished = Event()
    runtime_stop_called = Event()
    order = []
    shutdown_errors = []

    def runtime_start():
        order.append("runtime-start")
        runtime.running = True

    def runtime_cycle():
        entered.set()
        assert release.wait(2)
        order.append("cycle-finished")
        cycle_finished.set()
        return []

    def runtime_stop():
        # Production composition must stop the capability worker first. Its
        # bounded join must not permit runtime teardown while run_once is active.
        assert cycle_finished.is_set()
        order.append("runtime-stop")
        runtime.running = False
        runtime_stop_called.set()

    monkeypatch.setattr(runtime, "start", runtime_start)
    monkeypatch.setattr(runtime, "run_once", runtime_cycle)
    monkeypatch.setattr(runtime, "stop", runtime_stop)

    bundle.supervisor.start()
    stopper = None
    try:
        assert entered.wait(2)
        assert bundle.capability_worker is not None

        def shutdown():
            try:
                bundle.supervisor.stop()
            except BaseException as error:
                shutdown_errors.append(error)

        stopper = Thread(target=shutdown)
        stopper.start()

        # This event is set by SentinelCapabilityWorker.stop() before it joins
        # the in-flight cycle. At that point runtime shutdown must still wait.
        assert bundle.capability_worker._stop_event.wait(2)
        assert stopper.is_alive()
        assert not runtime_stop_called.is_set()
        assert runtime.running
        assert bundle.runtime_worker.state() is WorkerState.RUNNING
        assert bundle.supervisor.state is RuntimeState.STOPPING
    finally:
        release.set()
        if stopper is not None:
            stopper.join(2)
        elif bundle.supervisor.state is RuntimeState.RUNNING:
            bundle.supervisor.stop()

    assert stopper is not None and not stopper.is_alive()
    assert not shutdown_errors
    assert order == ["runtime-start", "cycle-finished", "runtime-stop"]
    assert runtime_stop_called.is_set()
    assert not runtime.running
    assert bundle.capability_worker.state() is WorkerState.STOPPED
    assert bundle.runtime_worker.state() is WorkerState.STOPPED
    assert bundle.supervisor.state is RuntimeState.STOPPED
    assert not bundle.runtime_worker.health()


def _isolate_runtime_cycle(runtime, monkeypatch, *, entered, release):
    """Make one canonical cycle block without touching host or production I/O."""

    def blocked_canary():
        entered.set()
        assert release.wait(2)
        return None

    monkeypatch.setattr(runtime.canary_live_execution, "cycle", blocked_canary)
    monkeypatch.setattr(runtime.production_probe_live_execution, "cycle", lambda: None)
    monkeypatch.setattr(runtime.gate3_live_validation, "cycle", lambda: None)
    monkeypatch.setattr(runtime.gate4_autonomous_remediation, "cycle", lambda: None)
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", lambda: [])
    monkeypatch.setattr(runtime.diagnostic, "submit", Mock())
    monkeypatch.setattr(runtime, "_sync_incident_reports_if_due", lambda: None)


def test_runtime_stop_rejects_active_cycle_without_teardown(monkeypatch):
    runtime = SentinelRuntime()
    diagnostic_start = Mock()
    diagnostic_stop = Mock()
    monkeypatch.setattr(runtime.diagnostic, "start", diagnostic_start)
    monkeypatch.setattr(runtime.diagnostic, "stop", diagnostic_stop)

    entered = Event()
    release = Event()
    runner_errors = []
    _isolate_runtime_cycle(runtime, monkeypatch, entered=entered, release=release)

    runtime.start()

    def run_cycle():
        try:
            runtime.run_once()
        except BaseException as error:
            runner_errors.append(error)

    runner = Thread(target=run_cycle)
    runner.start()
    try:
        assert entered.wait(2)
        health = runtime.get_runtime_health()
        assert health.running
        assert health.cycle_in_progress

        with pytest.raises(RuntimeShutdownInProgressError, match="quiescent"):
            runtime.stop()

        # Rejected shutdown is fail-closed: no lifecycle mutation and no
        # diagnostic teardown occurs underneath an active canonical cycle.
        health = runtime.get_runtime_health()
        assert health.running
        assert health.cycle_in_progress
        diagnostic_stop.assert_not_called()
    finally:
        release.set()
        runner.join(2)

    assert not runner.is_alive()
    assert not runner_errors
    health = runtime.get_runtime_health()
    assert health.running
    assert not health.cycle_in_progress
    assert health.cycles_started == health.cycles_completed == 1

    runtime.stop()
    assert not runtime.running
    diagnostic_start.assert_called_once_with()
    diagnostic_stop.assert_called_once_with()


def test_capability_shutdown_timeout_cannot_teardown_active_runtime(
    tmp_path,
    monkeypatch,
):
    from sentinel.worker import observability

    monkeypatch.setattr(observability, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("AIRIV_SENTINEL_DIAGNOSTIC_DIR", str(tmp_path / "diagnostic"))

    runtime = SentinelRuntime()
    diagnostic_start = Mock()
    diagnostic_stop = Mock()
    monkeypatch.setattr(runtime.diagnostic, "start", diagnostic_start)
    monkeypatch.setattr(runtime.diagnostic, "stop", diagnostic_stop)

    entered = Event()
    release = Event()
    _isolate_runtime_cycle(runtime, monkeypatch, entered=entered, release=release)

    config = RuntimeSupervisionConfig(
        worker_id=WorkerId("sentinel.runtime"),
        worker_name="Sentinel runtime",
        worker_version="1",
        worker_description="Lane 3 timeout containment proof",
        daemon_cycle_interval=0.001,
        health_stale_after=30,
        restart_policy=RestartPolicy(0, 0, 0),
    )
    bundle = build_production_supervision(runtime, config)
    assert bundle.capability_worker is not None
    # Test-only fault injection: force a bounded timeout while run_once blocks.
    bundle.capability_worker._shutdown_timeout = 0.01

    bundle.supervisor.start()
    try:
        assert entered.wait(2)
        assert runtime.get_runtime_health().cycle_in_progress

        with pytest.raises(WorkerShutdownError) as caught:
            bundle.supervisor.stop()

        message = str(caught.value)
        assert "Capability shutdown timed out" in message
        assert "RuntimeShutdownInProgressError" in message

        # Supervisor still attempts the next worker after the capability timeout,
        # but the canonical Lane 3 boundary refuses unsafe teardown atomically.
        assert bundle.supervisor.state is RuntimeState.FAILED
        assert bundle.capability_worker.state() is WorkerState.FAILED
        assert bundle.runtime_worker.state() is WorkerState.FAILED
        assert bundle.capability_worker._thread is not None
        assert bundle.capability_worker._thread.is_alive()
        health = runtime.get_runtime_health()
        assert health.running
        assert health.cycle_in_progress
        diagnostic_stop.assert_not_called()
    finally:
        release.set()
        if bundle.capability_worker._thread is not None:
            bundle.capability_worker._thread.join(2)

    assert bundle.capability_worker._thread is not None
    assert not bundle.capability_worker._thread.is_alive()
    health = runtime.get_runtime_health()
    assert health.running
    assert not health.cycle_in_progress
    assert health.cycles_started == health.cycles_completed == 1

    # Once quiescent, direct canonical cleanup is deterministic and safe. The
    # FAILED worker/supervisor retry semantics remain Lane 4 ownership.
    runtime.stop()
    assert not runtime.running
    diagnostic_start.assert_called_once_with()
    diagnostic_stop.assert_called_once_with()
