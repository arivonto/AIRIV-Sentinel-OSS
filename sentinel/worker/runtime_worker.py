"""Composition boundary between the existing runtime and worker supervision."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
import time
from typing import TYPE_CHECKING

from .models import WorkerHeartbeat, WorkerId
from .state import WorkerState, WorkerTransitionError, validate_transition

if TYPE_CHECKING:
    from sentinel.runtime import SentinelRuntime


class SentinelRuntimeWorker:
    """Wrap one supplied runtime using its public start/stop operations.

    The runtime retains ownership of its diagnostic background worker. This
    adapter creates no threads and does not schedule runtime cycles. Health
    reports adapter availability only: the runtime has no operational health
    API, so diagnostic-thread failures cannot be inferred here.

    Uptime measures adapter lifetime from construction, including stopped time;
    both uptime and heartbeat iteration persist across restarts. Transitional
    states reject overlapping lifecycle calls without locking external calls.
    """

    def __init__(self, runtime: SentinelRuntime, worker_id: WorkerId) -> None:
        if not isinstance(worker_id, WorkerId):
            raise TypeError("worker_id must be WorkerId")
        self._runtime = runtime
        self._worker_id = worker_id
        self._state = WorkerState.REGISTERED
        self._last_error: str | None = None
        self._created_at = time.monotonic()
        self._iteration = 0
        self._lock = RLock()

    @property
    def runtime(self) -> SentinelRuntime:
        return self._runtime

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def worker_id(self) -> WorkerId:
        return self._worker_id

    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    def _transition(self, target: WorkerState) -> None:
        """Validate and update state while the caller holds the lock."""
        validate_transition(self._state, target)
        self._state = target

    def start(self) -> None:
        with self._lock:
            self._transition(WorkerState.STARTING)
        try:
            self._runtime.start()
        except BaseException as error:
            with self._lock:
                self._last_error = f"{type(error).__name__}: {error}"
                self._transition(WorkerState.FAILED)
            raise
        with self._lock:
            self._last_error = None
            self._transition(WorkerState.RUNNING)

    def stop(self) -> None:
        with self._lock:
            self._transition(WorkerState.STOPPING)
        try:
            self._runtime.stop()
        except BaseException as error:
            with self._lock:
                self._last_error = f"{type(error).__name__}: {error}"
                self._transition(WorkerState.FAILED)
            raise
        with self._lock:
            self._transition(WorkerState.STOPPED)

    def health(self) -> bool:
        with self._lock:
            return self._state is WorkerState.RUNNING and self._last_error is None

    def report_failure(self, message: str) -> None:
        """Record a known operational failure supplied by the runtime owner.

        This only marks adapter state; it neither polls runtime internals nor
        shuts down or recovers the runtime. Recovery belongs to supervision.
        """
        if not isinstance(message, str) or not message.strip():
            raise ValueError("failure message must be non-empty text")
        with self._lock:
            # Only an operational worker can report an operational failure.
            if self._state is not WorkerState.RUNNING:
                raise WorkerTransitionError("Operational failure requires RUNNING worker")
            self._transition(WorkerState.FAILED)
            self._last_error = message

    def heartbeat(self) -> WorkerHeartbeat:
        with self._lock:
            self._iteration += 1
            return WorkerHeartbeat(
                worker_id=self._worker_id,
                state=self._state,
                timestamp=datetime.now(timezone.utc),
                uptime=time.monotonic() - self._created_at,
                iteration=self._iteration,
                healthy=self.health(),
            )
