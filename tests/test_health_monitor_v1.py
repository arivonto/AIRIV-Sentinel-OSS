import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo
import inspect

import pytest

import sentinel.worker as public_api
from sentinel.worker import (
    HealthMonitor, HealthMonitorError, InvalidHeartbeatError,
    InvalidHealthMonitorConfigurationError, WorkerHealthSnapshot,
    WorkerHealthStatus, WorkerHeartbeat, WorkerId, WorkerInfo,
    WorkerNotFoundError, WorkerRegistry, WorkerState,
)
from sentinel.worker import health as health_module


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class PassiveWorker:
    def __init__(self, identity):
        self.identity = identity
        self.current_state = WorkerState.REGISTERED

    def worker_id(self):
        return self.identity

    def state(self):
        raise AssertionError("must not query worker state")

    def start(self):
        raise AssertionError("must not start worker")

    def stop(self):
        raise AssertionError("must not stop worker")

    def health(self):
        raise AssertionError("must not poll health")

    def heartbeat(self):
        raise AssertionError("must not poll heartbeat")


def register(registry, name):
    worker = PassiveWorker(WorkerId(name))
    registry.register(worker, WorkerInfo(worker.identity, name, "1", ""))
    return worker


@pytest.fixture
def setup():
    registry = WorkerRegistry()
    worker = register(registry, "worker")
    heartbeat = WorkerHeartbeat(worker.identity, WorkerState.RUNNING, NOW, 1, 1, True)
    return registry, worker, HealthMonitor(registry, 10), heartbeat


@pytest.mark.parametrize("threshold", [0, -1, float("nan"), float("inf"), -float("inf"), True, None, "10"])
def test_invalid_threshold(threshold):
    with pytest.raises(InvalidHealthMonitorConfigurationError):
        HealthMonitor(WorkerRegistry(), threshold)


def test_invalid_registry():
    with pytest.raises(InvalidHealthMonitorConfigurationError):
        HealthMonitor(object(), 10)


def test_empty_registry():
    assert HealthMonitor(WorkerRegistry(), 0.1).snapshots(now=NOW) == ()


def test_unknown_health(setup):
    _, worker, monitor, _ = setup
    assert monitor.last_heartbeat(worker.identity) is None
    assert monitor.snapshot(worker.identity, now=NOW) == WorkerHealthSnapshot(
        worker.identity, WorkerHealthStatus.UNKNOWN, None, None,
    )


@pytest.mark.parametrize("healthy", [True, False])
@pytest.mark.parametrize("age", [0, 5, 10, 10.000001, 11, -5])
def test_health_and_time_boundaries(setup, healthy, age):
    _, worker, monitor, heartbeat = setup
    heartbeat = replace(heartbeat, healthy=healthy, timestamp=NOW - timedelta(seconds=age))
    assert monitor.record(heartbeat) is None
    snapshot = monitor.snapshot(worker.identity, now=NOW)
    expected = WorkerHealthStatus.HEALTHY if healthy else WorkerHealthStatus.UNHEALTHY
    if age > 10:
        expected = WorkerHealthStatus.STALE
    assert snapshot.status is expected
    assert snapshot.age_seconds == max(0, age)
    assert snapshot.heartbeat is heartbeat


@pytest.mark.parametrize("operation", ["snapshot", "snapshots"])
def test_naive_now_rejected(setup, operation):
    _, worker, monitor, _ = setup
    args = (worker.identity,) if operation == "snapshot" else ()
    with pytest.raises(ValueError, match="timezone-aware"):
        getattr(monitor, operation)(*args, now=NOW.replace(tzinfo=None))


def test_no_offset_now_rejected():
    class NoOffset(tzinfo):
        def utcoffset(self, dt):
            return None
    with pytest.raises(ValueError, match="timezone-aware"):
        HealthMonitor(WorkerRegistry(), 10).snapshots(now=NOW.replace(tzinfo=NoOffset()))


def test_default_clock_and_other_timezone(setup):
    _, worker, monitor, heartbeat = setup
    before = datetime.now(timezone.utc)
    monitor.record(replace(heartbeat, timestamp=before))
    result = monitor.snapshot(worker.identity)
    after = datetime.now(timezone.utc)
    assert 0 <= result.age_seconds <= (after - before).total_seconds()
    assert monitor.snapshots()[0].age_seconds >= result.age_seconds
    assert monitor.snapshot(worker.identity, now=before.astimezone(timezone(timedelta(hours=7)))).age_seconds == 0


@pytest.mark.parametrize("value", [None, {}, "heartbeat", object()])
def test_invalid_heartbeat(setup, value):
    _, worker, monitor, _ = setup
    with pytest.raises(InvalidHeartbeatError):
        monitor.record(value)
    assert monitor.last_heartbeat(worker.identity) is None


@pytest.mark.parametrize("operation", ["record", "snapshot", "last_heartbeat"])
def test_missing_worker(setup, operation):
    _, _, monitor, heartbeat = setup
    identity = WorkerId("missing")
    argument = replace(heartbeat, worker_id=identity) if operation == "record" else identity
    with pytest.raises(WorkerNotFoundError):
        getattr(monitor, operation)(argument)


def test_timestamp_ordering_and_equal_timestamp_first_wins(setup):
    _, worker, monitor, heartbeat = setup
    monitor.record(heartbeat)
    newer = replace(heartbeat, timestamp=NOW + timedelta(seconds=1), iteration=0)
    monitor.record(newer)
    monitor.record(replace(heartbeat, iteration=999))
    monitor.record(replace(newer))
    monitor.record(replace(newer, healthy=False, iteration=999))
    assert monitor.last_heartbeat(worker.identity) is newer


def test_order_immutability_and_no_worker_calls(setup):
    registry, worker, monitor, heartbeat = setup
    others = [register(registry, name) for name in ("z", "a")]
    monitor.record(heartbeat)
    snapshots = monitor.snapshots(now=NOW)
    assert isinstance(snapshots, tuple)
    assert tuple(s.worker_id for s in snapshots) == registry.worker_ids()
    for field in ("worker_id", "status", "heartbeat", "age_seconds"):
        with pytest.raises(FrozenInstanceError):
            setattr(snapshots[0], field, None)
    with pytest.raises(FrozenInstanceError):
        snapshots[0].heartbeat.healthy = False
    monitor.record(replace(heartbeat, timestamp=NOW + timedelta(seconds=1), healthy=False))
    assert snapshots[0].heartbeat is heartbeat
    assert all(w.current_state is WorkerState.REGISTERED for w in [worker, *others])


def test_unregistered_cached_worker_is_not_visible(setup):
    registry, worker, monitor, heartbeat = setup
    monitor.record(heartbeat)
    registry.unregister(worker.identity)
    assert monitor.snapshots(now=NOW) == ()
    for operation in (monitor.snapshot, monitor.last_heartbeat):
        with pytest.raises(WorkerNotFoundError):
            operation(worker.identity)
    with pytest.raises(WorkerNotFoundError):
        monitor.record(replace(heartbeat, timestamp=NOW + timedelta(seconds=1)))
    assert monitor.snapshots() == ()


def test_concurrent_records_retain_newest(setup):
    _, worker, monitor, heartbeat = setup
    observations = [replace(heartbeat, timestamp=NOW + timedelta(seconds=i)) for i in range(100)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(monitor.record, reversed(observations)))
    assert monitor.last_heartbeat(worker.identity) is observations[-1]


def test_public_exports_and_exact_statuses():
    names = {"HealthMonitor", "HealthMonitorError", "InvalidHeartbeatError",
             "InvalidHealthMonitorConfigurationError", "WorkerHealthSnapshot", "WorkerHealthStatus"}
    assert names <= set(public_api.__all__)
    for name in names:
        assert getattr(public_api, name) is getattr(health_module, name)
    statuses = {"UNKNOWN", "HEALTHY", "UNHEALTHY", "STALE"}
    assert set(WorkerHealthStatus.__members__) == statuses
    assert {s.value for s in WorkerHealthStatus} == statuses
    assert all(isinstance(s, str) for s in WorkerHealthStatus)
    for error in (InvalidHeartbeatError, InvalidHealthMonitorConfigurationError):
        assert issubclass(error, HealthMonitorError)
        assert issubclass(error, ValueError)


def test_architectural_boundary():
    source = inspect.getsource(health_module)
    for forbidden in (
        "Incident", "IncidentManager", "Diagnosis", "DiagnosisEvaluator", "Commander",
        "CommanderIntent", "Remediation", "RemediationPolicy", "FinalOutcomeMapper",
        "RuntimeSupervisor", "ExecutionBoundary", "Verification",
    ):
        assert forbidden not in source
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert isinstance(node, ast.ImportFrom)
            assert (node.level, node.module) in {
                (0, "dataclasses"), (0, "datetime"), (0, "enum"), (0, "threading"),
                (1, "models"), (1, "registry"),
            }
