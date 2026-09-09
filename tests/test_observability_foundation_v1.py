from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from sentinel.worker import (
    HealthMonitor,
    WorkerHealthProjection,
    WorkerHealthStatus,
    WorkerHeartbeat,
    WorkerId,
    WorkerInfo,
    WorkerRegistry,
    WorkerState,
)


NOW = datetime(2026, 9, 9, 3, 55, tzinfo=timezone.utc)


class PassiveWorker:
    def __init__(self, name: str) -> None:
        self.identity = WorkerId(name)

    def worker_id(self):
        return self.identity

    def state(self):
        raise AssertionError("projection must not poll worker state")

    def start(self):
        raise AssertionError("projection must not start workers")

    def stop(self):
        raise AssertionError("projection must not stop workers")

    def health(self):
        raise AssertionError("projection must not poll worker health")

    def heartbeat(self):
        raise AssertionError("projection must not poll heartbeat")


def _register(registry: WorkerRegistry, name: str) -> PassiveWorker:
    worker = PassiveWorker(name)
    registry.register(worker, WorkerInfo(worker.identity, name, "1", ""))
    return worker


def _heartbeat(worker: PassiveWorker, *, age: float, healthy: bool = True) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        worker.identity,
        WorkerState.RUNNING,
        NOW - timedelta(seconds=age),
        100,
        1,
        healthy,
    )


def test_projection_preserves_all_health_states_and_counts():
    registry = WorkerRegistry()
    unknown = _register(registry, "unknown")
    healthy = _register(registry, "healthy")
    unhealthy = _register(registry, "unhealthy")
    stale = _register(registry, "stale")
    monitor = HealthMonitor(registry, stale_after=10)

    monitor.record(_heartbeat(healthy, age=2, healthy=True))
    monitor.record(_heartbeat(unhealthy, age=2, healthy=False))
    monitor.record(_heartbeat(stale, age=11, healthy=True))

    projection = monitor.projection(now=NOW)

    assert isinstance(projection, WorkerHealthProjection)
    assert projection.observed_at is NOW
    assert projection.total_workers == 4
    assert projection.unknown_count == 1
    assert projection.healthy_count == 1
    assert projection.unhealthy_count == 1
    assert projection.stale_count == 1
    assert tuple(worker.worker_id for worker in projection.workers) == registry.worker_ids()
    assert {worker.status for worker in projection.workers} == set(WorkerHealthStatus)
    assert projection.workers[0].worker_id == unknown.identity


def test_projection_is_immutable_and_snapshot_based():
    registry = WorkerRegistry()
    worker = _register(registry, "worker")
    monitor = HealthMonitor(registry, stale_after=10)
    heartbeat = _heartbeat(worker, age=1)
    monitor.record(heartbeat)

    projection = monitor.projection(now=NOW)
    with pytest.raises(FrozenInstanceError):
        projection.total_workers = 99

    monitor.record(replace(heartbeat, timestamp=NOW, healthy=False, iteration=2))
    assert projection.healthy_count == 1
    assert projection.unhealthy_count == 0
    assert projection.workers[0].heartbeat is heartbeat


def test_projection_empty_registry_and_explicit_freshness():
    projection = HealthMonitor(WorkerRegistry(), stale_after=10).projection(now=NOW)
    assert projection == WorkerHealthProjection(
        observed_at=NOW,
        workers=(),
        total_workers=0,
        unknown_count=0,
        healthy_count=0,
        unhealthy_count=0,
        stale_count=0,
    )


def test_projection_rejects_ambiguous_query_time():
    monitor = HealthMonitor(WorkerRegistry(), stale_after=10)
    with pytest.raises(ValueError, match="timezone-aware"):
        monitor.projection(now=NOW.replace(tzinfo=None))


def test_projection_has_no_recovery_or_authority_side_effects():
    registry = WorkerRegistry()
    healthy = _register(registry, "healthy")
    stale = _register(registry, "stale")
    monitor = HealthMonitor(registry, stale_after=10)
    monitor.record(_heartbeat(healthy, age=1))
    monitor.record(_heartbeat(stale, age=20))

    first = monitor.projection(now=NOW)
    second = monitor.projection(now=NOW)

    assert first == second
    assert first.stale_count == 1
    assert first.healthy_count == 1
