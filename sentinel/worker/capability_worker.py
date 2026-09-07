"""Periodic infrastructure driver for the supplied runtime's public cycle API."""

from datetime import datetime, timezone
from threading import Event, RLock, Thread
import time
from typing import TYPE_CHECKING

from .models import WorkerHeartbeat, WorkerId
from .observability import LiveEvidenceObservability
from .state import WorkerState, WorkerTransitionError, validate_transition

if TYPE_CHECKING:
    from sentinel.runtime import SentinelRuntime


class SentinelCapabilityWorker:
    """Drive one runtime without owning its lifecycle or interpreting results.

    The first cycle follows one interval, allowing supervision startup to finish.
    Stop interrupts the interval immediately and waits finitely for an in-flight
    public cycle. A timeout fails explicitly; Python cannot cancel that call.
    Restart refuses to overlap a surviving thread. Error text excludes exception
    payloads, which could contain sensor data.
    """

    ID = WorkerId("sentinel.capability")

    def __init__(self, runtime: "SentinelRuntime", *, interval: float = 1.0,
                 shutdown_timeout: float = 15.0,
                 observability: LiveEvidenceObservability | None = None) -> None:
        for name, value in (("interval", interval), ("shutdown_timeout", shutdown_timeout)):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0 < value < float("inf")):
                raise ValueError(f"{name} must be finite and positive")
        self._runtime = runtime
        self._observability = observability
        self._interval = interval
        self._shutdown_timeout = shutdown_timeout
        self._lock = RLock()
        self._stop_event = Event()
        self._ready = Event()
        self._thread: Thread | None = None
        self._state = WorkerState.REGISTERED
        self._created_at = time.monotonic()
        self._iteration = 0
        self._last_cycle_at: datetime | None = None
        self._last_cycle_status: str | None = None
        self._last_error: str | None = None
        self._publish_status()

    def _publish_status(self) -> None:
        if self._observability is not None:
            self._observability.status(
                worker_id=self.ID.value, state=self._state.value,
                iteration=self._iteration, last_cycle_at=self._last_cycle_at,
                last_cycle_status=self._last_cycle_status,
                last_error_type=("TimeoutError" if self._last_error ==
                                 "Capability shutdown timed out" else self._last_error),
            )

    @property
    def runtime(self) -> "SentinelRuntime":
        return self._runtime

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def last_cycle_at(self) -> datetime | None:
        with self._lock:
            return self._last_cycle_at

    @property
    def last_cycle_status(self) -> str | None:
        with self._lock:
            return self._last_cycle_status

    def worker_id(self) -> WorkerId:
        return self.ID

    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    def _transition(self, target: WorkerState) -> None:
        validate_transition(self._state, target)
        self._state = target
        self._publish_status()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise WorkerTransitionError("Capability thread is still active")
            self._transition(WorkerState.STARTING)
            self._stop_event.clear()
            self._ready.clear()
        try:
            if not self._runtime.running:
                raise RuntimeError("Runtime must be started before capability")
            thread = Thread(target=self._run, name="airiv-capability-worker", daemon=False)
            with self._lock:
                self._thread = thread
            thread.start()
        except BaseException as error:
            with self._lock:
                self._last_error = type(error).__name__
                self._transition(WorkerState.FAILED)
            raise
        with self._lock:
            self._last_error = None
            self._transition(WorkerState.RUNNING)
        self._ready.set()

    def _run(self) -> None:
        self._ready.wait()
        try:
            while not self._stop_event.wait(self._interval):
                with self._lock:
                    self._iteration += 1
                    self._last_cycle_status = "RUNNING"
                    self._publish_status()
                if not self._runtime.running:
                    raise RuntimeError("Runtime is not running")
                results = self._runtime.run_once()
                if self._observability is not None:
                    self._observability.observations(
                        self._runtime, results, worker_id=self.ID.value,
                        iteration=self._iteration,
                    )
                with self._lock:
                    self._last_cycle_at = datetime.now(timezone.utc)
                    self._last_cycle_status = "OK"
                    self._publish_status()
        except BaseException as error:
            with self._lock:
                self._last_cycle_at = datetime.now(timezone.utc)
                self._last_cycle_status = "FAILED"
                self._last_error = type(error).__name__
                if self._state in (WorkerState.RUNNING, WorkerState.STOPPING):
                    self._transition(WorkerState.FAILED)

    def stop(self) -> None:
        with self._lock:
            self._transition(WorkerState.STOPPING)
            thread = self._thread
        self._stop_event.set()
        if thread is not None:
            thread.join(self._shutdown_timeout)
        with self._lock:
            if thread is not None and thread.is_alive():
                self._last_error = "Capability shutdown timed out"
                if self._state is WorkerState.STOPPING:
                    self._transition(WorkerState.FAILED)
                raise RuntimeError("Capability shutdown timed out")
            if self._state is WorkerState.FAILED:
                raise RuntimeError("Capability failed during shutdown")
            self._transition(WorkerState.STOPPED)

    def health(self) -> bool:
        with self._lock:
            return self._state is WorkerState.RUNNING and self._last_error is None

    def heartbeat(self) -> WorkerHeartbeat:
        with self._lock:
            return WorkerHeartbeat(
                worker_id=self.ID, state=self._state,
                timestamp=datetime.now(timezone.utc),
                uptime=time.monotonic() - self._created_at,
                iteration=self._iteration, healthy=self.health(),
            )
