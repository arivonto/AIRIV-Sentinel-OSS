"""Explicit synchronous worker supervision; retry timing belongs to callers."""

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from math import ldexp
from threading import RLock

from .health import HealthMonitor, WorkerHealthStatus
from .models import WorkerHeartbeat, WorkerId
from .registry import WorkerRegistry
from .state import WorkerState


class RuntimeSupervisorError(Exception):
    """Base operational supervision error."""


class RuntimeStateError(RuntimeSupervisorError):
    """Invalid lifecycle transition or overlapping operation."""


class WorkerStartupError(RuntimeSupervisorError):
    """A worker could not become running."""


class WorkerShutdownError(RuntimeSupervisorError):
    """One or more workers could not stop."""


class WorkerSupervisionError(RuntimeSupervisorError):
    """A worker observation failed validation or raised."""


class RuntimeState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


def _validate_transition(current: RuntimeState, target: RuntimeState) -> None:
    allowed = {
        RuntimeState.STOPPED: {RuntimeState.STARTING},
        RuntimeState.STARTING: {RuntimeState.RUNNING, RuntimeState.FAILED, RuntimeState.STOPPING},
        RuntimeState.RUNNING: {RuntimeState.STOPPING, RuntimeState.FAILED},
        RuntimeState.FAILED: {RuntimeState.STARTING, RuntimeState.STOPPING},
        RuntimeState.STOPPING: {RuntimeState.STOPPED, RuntimeState.FAILED},
    }
    if target not in allowed[current]:
        raise RuntimeStateError(f"Invalid runtime transition: {current} -> {target}")


@dataclass(frozen=True)
class RestartPolicy:
    max_retries: int = 0
    initial_backoff: float = 0.0
    max_backoff: float = 0.0

    def __post_init__(self) -> None:
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        for value in (self.initial_backoff, self.max_backoff):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < float("inf"):
                raise ValueError("backoff must be finite and non-negative")
        if self.max_backoff < self.initial_backoff:
            raise ValueError("max_backoff must be at least initial_backoff")

    def delay(self, retry_number: int) -> float:
        if type(retry_number) is not int or retry_number < 1:
            raise ValueError("retry_number must be a positive integer")
        if self.initial_backoff == 0:
            return 0.0
        try:
            return min(ldexp(self.initial_backoff, retry_number - 1), self.max_backoff)
        except OverflowError:
            return self.max_backoff


@dataclass(frozen=True)
class WorkerRestartRecord:
    worker_id: WorkerId
    attempt: int
    backoff: float
    succeeded: bool
    error: str | None


@dataclass(frozen=True)
class WorkerSupervisionSnapshot:
    worker_id: WorkerId
    state: WorkerState
    health_status: WorkerHealthStatus
    restart_count: int
    last_exception: str | None
    last_heartbeat: WorkerHeartbeat | None


@dataclass(frozen=True)
class RuntimeSupervisorSnapshot:
    state: RuntimeState
    workers: tuple[WorkerSupervisionSnapshot, ...]


class RuntimeSupervisor:
    """Serialize explicit operations without holding locks across external calls.

    Membership and health queries have the registry/monitor's snapshot semantics,
    not transactional isolation against concurrent registration changes. Retry
    budgets are lifetime budgets per identity, including across runtime starts.
    Observation errors are collected, then raised; snapshot() exposes their text.
    """

    def __init__(self, registry: WorkerRegistry, health_monitor: HealthMonitor,
                 restart_policy: RestartPolicy | None = None) -> None:
        if not isinstance(registry, WorkerRegistry):
            raise TypeError("registry must be WorkerRegistry")
        if not isinstance(health_monitor, HealthMonitor):
            raise TypeError("health_monitor must be HealthMonitor")
        if restart_policy is not None and not isinstance(restart_policy, RestartPolicy):
            raise TypeError("restart_policy must be RestartPolicy")
        self._registry = registry
        self._health_monitor = health_monitor
        self._restart_policy = restart_policy if restart_policy is not None else RestartPolicy()
        self._lock = RLock()
        self._state = RuntimeState.STOPPED
        self._busy = False
        self._counts: dict[WorkerId, int] = {}
        self._errors: dict[WorkerId, str] = {}
        self._history: dict[WorkerId, list[WorkerRestartRecord]] = {}

    @property
    def state(self) -> RuntimeState:
        with self._lock:
            return self._state

    def _transition(self, target: RuntimeState) -> None:
        with self._lock:
            _validate_transition(self._state, target)
            self._state = target

    @contextmanager
    def _operation(self):
        with self._lock:
            if self._busy:
                raise RuntimeStateError("Another supervisor operation is in progress")
            self._busy = True
        try:
            yield
        finally:
            with self._lock:
                self._busy = False

    def _error(self, worker_id: WorkerId, error: Exception) -> str:
        message = f"{type(error).__name__}: {error}"
        with self._lock:
            self._errors[worker_id] = message
        return message

    @staticmethod
    def _worker_state(worker) -> WorkerState:
        state = worker.state()
        if not isinstance(state, WorkerState):
            raise WorkerSupervisionError(f"Invalid worker state: {state!r}")
        return state

    def start(self) -> None:
        with self._operation():
            self._transition(RuntimeState.STARTING)
            try:
                for worker_id in self._registry.worker_ids():
                    try:
                        worker = self._registry.get(worker_id)
                        state = self._worker_state(worker)
                        if state in (WorkerState.REGISTERED, WorkerState.STOPPED, WorkerState.FAILED):
                            worker.start()
                            state = self._worker_state(worker)
                        if state is not WorkerState.RUNNING:
                            raise WorkerStartupError(f"Worker is {state.value}, expected RUNNING")
                    except Exception as error:
                        message = self._error(worker_id, error)
                        raise WorkerStartupError(f"{worker_id}: {message}") from error
            except Exception:
                self._transition(RuntimeState.FAILED)
                raise
            self._transition(RuntimeState.RUNNING)

    def stop(self) -> None:
        with self._operation():
            if self.state is RuntimeState.STOPPED:
                return
            self._transition(RuntimeState.STOPPING)
            failures = []
            for worker_id in reversed(self._registry.worker_ids()):
                try:
                    worker = self._registry.get(worker_id)
                    state = self._worker_state(worker)
                    if state is WorkerState.RUNNING:
                        worker.stop()
                        state = self._worker_state(worker)
                        if state is not WorkerState.STOPPED:
                            raise WorkerShutdownError(f"Worker remained {state.value}")
                    elif state not in (WorkerState.REGISTERED, WorkerState.STOPPED):
                        # The locked contract provides no stop transition here.
                        raise WorkerShutdownError(f"Cannot stop worker in {state.value}")
                except Exception as error:
                    failures.append(f"{worker_id}: {self._error(worker_id, error)}")
            self._transition(RuntimeState.FAILED if failures else RuntimeState.STOPPED)
            if failures:
                raise WorkerShutdownError("; ".join(failures))

    def _observe(self, worker_id, worker) -> None:
        heartbeat = worker.heartbeat()
        if not isinstance(heartbeat, WorkerHeartbeat):
            raise WorkerSupervisionError("heartbeat must be WorkerHeartbeat")
        if heartbeat.worker_id != worker.worker_id() or heartbeat.worker_id != worker_id:
            raise WorkerSupervisionError("Heartbeat worker identity mismatch")
        self._health_monitor.record(heartbeat)

    def supervise_once(self) -> RuntimeSupervisorSnapshot:
        with self._operation():
            if self.state is not RuntimeState.RUNNING:
                raise RuntimeStateError("Supervision requires RUNNING runtime")
            failures = []
            for worker_id in self._registry.worker_ids():
                try:
                    worker = self._registry.get(worker_id)
                    self._worker_state(worker)
                    self._observe(worker_id, worker)
                    self._health_monitor.snapshot(worker_id)
                except Exception as error:
                    failures.append(f"{worker_id}: {self._error(worker_id, error)}")
            if failures:
                raise WorkerSupervisionError("; ".join(failures))
            return self.snapshot()

    def snapshot(self) -> RuntimeSupervisorSnapshot:
        workers = []
        for worker_id in self._registry.worker_ids():
            worker = self._registry.get(worker_id)
            state = self._worker_state(worker)
            health = self._health_monitor.snapshot(worker_id)
            with self._lock:
                count = self._counts.get(worker_id, 0)
                error = self._errors.get(worker_id)
            workers.append(WorkerSupervisionSnapshot(
                worker_id, state, health.status, count, error, health.heartbeat,
            ))
        return RuntimeSupervisorSnapshot(self.state, tuple(workers))

    def recover(self, worker_id: WorkerId) -> bool:
        """Attempt once, without waiting. FAILED workers restart directly.

        Recovery requires an active or failed runtime. A successful restart
        means RUNNING plus a recorded heartbeat, not a guarantee of health.
        The runtime lifecycle is unchanged; start() can reconcile FAILED.
        """
        with self._operation():
            worker = self._registry.get(worker_id)
            if self.state not in (RuntimeState.RUNNING, RuntimeState.FAILED):
                raise RuntimeStateError("Recovery requires RUNNING or FAILED runtime")
            try:
                state = self._worker_state(worker)
                health = self._health_monitor.snapshot(worker_id)
                if state is not WorkerState.FAILED and health.status not in (
                    WorkerHealthStatus.UNHEALTHY, WorkerHealthStatus.STALE,
                ):
                    return False
                if state not in (WorkerState.RUNNING, WorkerState.FAILED, WorkerState.STOPPED):
                    return False
            except Exception as error:
                self._error(worker_id, error)
                return False
            with self._lock:
                attempt = self._counts.get(worker_id, 0) + 1
                if attempt > self._restart_policy.max_retries:
                    return False
                self._counts[worker_id] = attempt
            backoff = self._restart_policy.delay(attempt)
            error_text = None
            try:
                if state is WorkerState.RUNNING:
                    worker.stop()
                    if self._worker_state(worker) is not WorkerState.STOPPED:
                        raise WorkerShutdownError("Worker did not stop for recovery")
                worker.start()
                if self._worker_state(worker) is not WorkerState.RUNNING:
                    raise WorkerStartupError("Worker did not become RUNNING")
                self._observe(worker_id, worker)
            except Exception as error:
                error_text = self._error(worker_id, error)
            record = WorkerRestartRecord(worker_id, attempt, backoff, error_text is None, error_text)
            with self._lock:
                self._history.setdefault(worker_id, []).append(record)
            return record.succeeded

    def restart_history(self, worker_id: WorkerId) -> tuple[WorkerRestartRecord, ...]:
        self._registry.get(worker_id)
        with self._lock:
            return tuple(self._history.get(worker_id, ()))
