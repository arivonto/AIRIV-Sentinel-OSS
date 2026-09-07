"""Real worker infrastructure with a runtime stub that cannot launch diagnostics."""

from dataclasses import fields
from datetime import timezone
from threading import Event, Thread
from unittest.mock import Mock

import pytest

import sentinel.worker as api
from sentinel.runtime import SentinelRuntime
from sentinel.worker import runtime_worker as module
from sentinel.worker import (
    DaemonConfig, HealthMonitor, OperationalDaemon, RuntimeSupervisor,
    SentinelRuntimeWorker, WorkerHeartbeat, WorkerHealthStatus, WorkerId,
    WorkerInfo, WorkerProtocol, WorkerRegistry, WorkerState, WorkerTransitionError,
)


@pytest.fixture
def setup():
    # Production start recovers persisted investigations and launches a thread.
    # A spec-bound stub keeps those effects out of unit tests.
    runtime = Mock(spec=SentinelRuntime)
    worker = SentinelRuntimeWorker(runtime, WorkerId("sentinel.runtime"))
    return runtime, worker


def test_protocol_identity_initial_state_and_exports(setup):
    runtime, worker = setup
    assert isinstance(worker, WorkerProtocol)
    assert worker.state() is WorkerState.REGISTERED
    assert worker.runtime is runtime
    assert worker.last_error is None
    assert not worker.health()
    assert worker.worker_id() is worker.worker_id()
    assert worker.worker_id() == WorkerId("sentinel.runtime")
    assert api.SentinelRuntimeWorker is module.SentinelRuntimeWorker
    assert "SentinelRuntimeWorker" in api.__all__
    runtime.assert_not_called()
    assert runtime.mock_calls == []


@pytest.mark.parametrize("identity", [None, "sentinel.runtime", 1])
def test_requires_explicit_worker_id(identity):
    with pytest.raises(TypeError, match="WorkerId"):
        SentinelRuntimeWorker(Mock(spec=SentinelRuntime), identity)


def test_start_stop_restart_and_invalid_operations(setup):
    runtime, worker = setup
    with pytest.raises(WorkerTransitionError):
        worker.stop()
    for _ in range(2):
        worker.start()
        assert worker.state() is WorkerState.RUNNING
        assert worker.health()
        with pytest.raises(WorkerTransitionError):
            worker.start()
        assert worker.state() is WorkerState.RUNNING
        assert worker.last_error is None
        worker.stop()
        assert worker.state() is WorkerState.STOPPED
        assert not worker.health()
        with pytest.raises(WorkerTransitionError):
            worker.stop()
    assert runtime.start.call_count == runtime.stop.call_count == 2


@pytest.mark.parametrize("operation", ["start", "stop"])
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_lifecycle_failure_and_restart(setup, operation, error_type):
    runtime, worker = setup
    if operation == "stop":
        worker.start()
    error = error_type("runtime lifecycle failed")
    getattr(runtime, operation).side_effect = error
    with pytest.raises(error_type) as caught:
        getattr(worker, operation)()
    assert caught.value is error
    assert worker.state() is WorkerState.FAILED
    assert worker.last_error == f"{error_type.__name__}: runtime lifecycle failed"
    assert not worker.health()
    assert not worker.heartbeat().healthy
    with pytest.raises(AttributeError):
        worker.last_error = "changed"
    with pytest.raises(WorkerTransitionError):
        worker.stop()
    getattr(runtime, operation).side_effect = None
    worker.start()
    assert worker.state() is WorkerState.RUNNING
    assert worker.last_error is None
    assert worker.health()


def test_heartbeat_observation_and_monotonic_lifetime(monkeypatch):
    ticks = iter([10.0, 12.0, 15.0, 18.0, 20.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    runtime = Mock(spec=SentinelRuntime)
    worker = SentinelRuntimeWorker(runtime, WorkerId("runtime-1"))
    observations = [worker.heartbeat()]
    worker.start()
    observations.append(worker.heartbeat())
    worker.stop()
    observations.append(worker.heartbeat())
    worker.start()
    observations.append(worker.heartbeat())
    assert [h.uptime for h in observations] == [2.0, 5.0, 8.0, 10.0]
    assert [h.iteration for h in observations] == [1, 2, 3, 4]
    assert [h.state for h in observations] == [WorkerState.REGISTERED,
        WorkerState.RUNNING, WorkerState.STOPPED, WorkerState.RUNNING]
    assert [h.healthy for h in observations] == [False, True, False, True]
    for heartbeat in observations:
        assert isinstance(heartbeat, WorkerHeartbeat)
        assert heartbeat.worker_id is worker.worker_id()
        assert heartbeat.timestamp.tzinfo is timezone.utc
        assert heartbeat.uptime >= 0
    assert observations[-1].state is worker.state()
    # No sensor cycles, diagnostics, Commander or remediation were invoked.
    assert [call[0] for call in runtime.mock_calls] == ["start", "stop", "start"]
    assert {field.name for field in fields(observations[0])} == {
        "worker_id", "state", "timestamp", "uptime", "iteration", "healthy",
    }


def test_known_operational_failure_is_passive_and_restartable(setup):
    runtime, worker = setup
    with pytest.raises(WorkerTransitionError):
        worker.report_failure("unavailable")
    worker.start()
    worker.report_failure("runtime owner reported unavailable")
    assert worker.state() is WorkerState.FAILED
    assert not worker.health()
    assert not worker.heartbeat().healthy
    assert worker.last_error == "runtime owner reported unavailable"
    assert [call[0] for call in runtime.mock_calls] == ["start"]
    worker.start()
    assert worker.health()
    assert worker.last_error is None


@pytest.mark.parametrize("message", [None, ValueError("mutable"), "", " "])
def test_failure_report_requires_text(setup, message):
    _, worker = setup
    worker.start()
    with pytest.raises(ValueError):
        worker.report_failure(message)
    assert worker.health()


@pytest.mark.parametrize("operation", ["start", "stop"])
def test_concurrent_lifecycle_rejected_and_observation_unlocked(setup, operation):
    runtime, worker = setup
    if operation == "stop":
        worker.start()
    entered, release = Event(), Event()
    errors = []

    def block():
        entered.set()
        assert release.wait(5)

    def run():
        try:
            getattr(worker, operation)()
        except BaseException as error:
            errors.append(error)

    getattr(runtime, operation).side_effect = block
    thread = Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        expected = WorkerState.STARTING if operation == "start" else WorkerState.STOPPING
        assert worker.state() is expected
        assert worker.heartbeat().state is expected
        assert not worker.health()
        for overlapping in (worker.start, worker.stop):
            with pytest.raises(WorkerTransitionError):
                overlapping()
        with pytest.raises(WorkerTransitionError):
            worker.report_failure("overlapping failure")
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert getattr(runtime, operation).call_count == 1


def test_real_infrastructure_chain_without_internal_thread(setup, monkeypatch):
    runtime, worker = setup

    def forbidden(*args, **kwargs):
        pytest.fail("adapter must not create a background thread")

    monkeypatch.setattr(Thread, "start", forbidden)
    info = WorkerInfo(worker.worker_id(), "Sentinel runtime", "1", "Runtime adapter")
    registry = WorkerRegistry()
    registry.register(worker, info)
    assert registry.get(worker.worker_id()) is worker
    assert registry.get_info(worker.worker_id()) is info
    assert info.worker_id is worker.worker_id()
    monitor = HealthMonitor(registry, stale_after=30)
    supervisor = RuntimeSupervisor(registry, monitor)
    daemon = OperationalDaemon(supervisor, DaemonConfig(cycle_interval=1))
    supervisor.start()
    try:
        assert worker.state() is WorkerState.RUNNING
        observation = supervisor.supervise_once()
        heartbeat = monitor.last_heartbeat(worker.worker_id())
        assert heartbeat is observation.workers[0].last_heartbeat
        assert monitor.snapshot(worker.worker_id()).status is WorkerHealthStatus.HEALTHY
        cycle = daemon.run_once()
        assert cycle.workers[0].worker_id is worker.worker_id()
        assert cycle.workers[0].health_status is WorkerHealthStatus.HEALTHY
        assert cycle.workers[0].last_heartbeat.iteration > heartbeat.iteration
        assert daemon.snapshot().last_supervision is cycle
        assert daemon.snapshot().cycles == 1
        assert worker.runtime is runtime
    finally:
        supervisor.stop()
    assert worker.state() is WorkerState.STOPPED
    assert [call[0] for call in runtime.mock_calls] == ["start", "stop"]


def test_composition_preserves_supplied_phase1_graph(monkeypatch):
    # Exercise the actual runtime lifecycle methods with only its background
    # coordinator replaced. Bypass construction to avoid persistent resources.
    runtime = object.__new__(SentinelRuntime)
    runtime.running = False
    runtime.diagnostic = Mock()
    authorities = ("incident_manager", "commander", "execution", "policy",
                   "remediation_action_catalog", "sensor_adapter")
    for name in authorities:
        setattr(runtime, name, object())
    original = vars(runtime).copy()

    def forbidden(*args, **kwargs):
        pytest.fail("adapter must not construct another runtime")

    monkeypatch.setattr(SentinelRuntime, "__init__", forbidden)
    worker = SentinelRuntimeWorker(runtime, WorkerId("production-runtime"))
    worker.start()
    assert runtime.running
    worker.heartbeat()
    worker.health()
    worker.stop()
    assert not runtime.running
    assert worker.runtime is runtime
    assert vars(runtime) == original
    assert [call[0] for call in runtime.diagnostic.mock_calls] == ["start", "stop"]
