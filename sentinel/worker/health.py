"""Passive, thread-safe heartbeat storage and freshness reporting."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock

from .models import WorkerHeartbeat, WorkerId
from .registry import WorkerRegistry


class HealthMonitorError(Exception):
    """Base exception for health monitor failures."""


class InvalidHealthMonitorConfigurationError(HealthMonitorError, ValueError):
    """The registry or freshness threshold is invalid."""


class InvalidHeartbeatError(HealthMonitorError, ValueError):
    """The supplied observation is not a WorkerHeartbeat."""


class WorkerHealthStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    STALE = "STALE"


@dataclass(frozen=True)
class WorkerHealthSnapshot:
    worker_id: WorkerId
    status: WorkerHealthStatus
    heartbeat: WorkerHeartbeat | None
    age_seconds: float | None


@dataclass(frozen=True)
class WorkerHealthProjection:
    """Immutable read-only liveness/staleness projection at one query time."""

    observed_at: datetime
    workers: tuple[WorkerHealthSnapshot, ...]
    total_workers: int
    unknown_count: int
    healthy_count: int
    unhealthy_count: int
    stale_count: int


class HealthMonitor:
    """Report heartbeat facts for registered identities without polling workers.

    Missing identities use the registry's canonical not-found exception.
    Equal timestamps retain the first observation, including on identical
    retries; conflicting observations cannot overwrite it. Registration and
    heartbeat storage have independent locks, so queries do not constitute
    an atomic transaction with concurrent registry changes.
    """

    def __init__(self, registry: WorkerRegistry, stale_after: float) -> None:
        if not isinstance(registry, WorkerRegistry):
            raise InvalidHealthMonitorConfigurationError("registry must be WorkerRegistry")
        if (
            isinstance(stale_after, bool)
            or not isinstance(stale_after, (int, float))
            or not 0 < stale_after < float("inf")
        ):
            raise InvalidHealthMonitorConfigurationError(
                "stale_after must be a finite positive number"
            )
        self._registry = registry
        self._stale_after = stale_after
        self._heartbeats: dict[WorkerId, WorkerHeartbeat] = {}
        self._lock = RLock()

    def record(self, heartbeat: WorkerHeartbeat) -> None:
        if not isinstance(heartbeat, WorkerHeartbeat):
            raise InvalidHeartbeatError("heartbeat must be WorkerHeartbeat")
        self._registry.get(heartbeat.worker_id)
        with self._lock:
            previous = self._heartbeats.get(heartbeat.worker_id)
            if previous is None or heartbeat.timestamp > previous.timestamp:
                self._heartbeats[heartbeat.worker_id] = heartbeat

    def last_heartbeat(self, worker_id: WorkerId) -> WorkerHeartbeat | None:
        self._registry.get(worker_id)
        with self._lock:
            return self._heartbeats.get(worker_id)

    @staticmethod
    def _query_time(now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        return now

    def _snapshot(
        self, worker_id: WorkerId, heartbeat: WorkerHeartbeat | None, now: datetime,
    ) -> WorkerHealthSnapshot:
        if heartbeat is None:
            return WorkerHealthSnapshot(worker_id, WorkerHealthStatus.UNKNOWN, None, None)
        age = max(0.0, (now - heartbeat.timestamp).total_seconds())
        if age > self._stale_after:
            status = WorkerHealthStatus.STALE
        else:
            status = WorkerHealthStatus.HEALTHY if heartbeat.healthy else WorkerHealthStatus.UNHEALTHY
        return WorkerHealthSnapshot(worker_id, status, heartbeat, age)

    def snapshot(
        self, worker_id: WorkerId, *, now: datetime | None = None,
    ) -> WorkerHealthSnapshot:
        query_time = self._query_time(now)
        return self._snapshot(worker_id, self.last_heartbeat(worker_id), query_time)

    def snapshots(self, *, now: datetime | None = None) -> tuple[WorkerHealthSnapshot, ...]:
        query_time = self._query_time(now)
        worker_ids = self._registry.worker_ids()
        with self._lock:
            heartbeats = tuple(self._heartbeats.get(worker_id) for worker_id in worker_ids)
        return tuple(
            self._snapshot(worker_id, heartbeat, query_time)
            for worker_id, heartbeat in zip(worker_ids, heartbeats)
        )

    def projection(self, *, now: datetime | None = None) -> WorkerHealthProjection:
        """Project worker freshness without polling, recovery, or side effects."""
        query_time = self._query_time(now)
        workers = self.snapshots(now=query_time)
        counts = {status: 0 for status in WorkerHealthStatus}
        for worker in workers:
            counts[worker.status] += 1
        return WorkerHealthProjection(
            observed_at=query_time,
            workers=workers,
            total_workers=len(workers),
            unknown_count=counts[WorkerHealthStatus.UNKNOWN],
            healthy_count=counts[WorkerHealthStatus.HEALTHY],
            unhealthy_count=counts[WorkerHealthStatus.UNHEALTHY],
            stale_count=counts[WorkerHealthStatus.STALE],
        )