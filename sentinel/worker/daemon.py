"""Synchronous operational loop over the worker supervision contract."""

from dataclasses import dataclass
from enum import Enum
from threading import Event, RLock, get_ident

from .health import WorkerHealthStatus
from .state import WorkerState
from .supervisor import RuntimeState, RuntimeSupervisor, RuntimeSupervisorSnapshot


class OperationalDaemonError(Exception):
    """Base daemon operational error."""


class DaemonStateError(OperationalDaemonError):
    """Invalid transition, cycle state, or overlapping execution."""


class DaemonStartupError(OperationalDaemonError):
    """Supervisor startup failed."""


class DaemonCycleError(OperationalDaemonError):
    """Supervision or recovery request failed unexpectedly."""


class DaemonShutdownError(OperationalDaemonError):
    """Supervisor shutdown failed."""


class DaemonState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


def _validate_transition(current: DaemonState, target: DaemonState) -> None:
    allowed = {
        DaemonState.STOPPED: {DaemonState.STARTING},
        DaemonState.STARTING: {DaemonState.RUNNING, DaemonState.FAILED, DaemonState.STOPPING},
        DaemonState.RUNNING: {DaemonState.STOPPING, DaemonState.FAILED},
        DaemonState.FAILED: {DaemonState.STARTING, DaemonState.STOPPING},
        DaemonState.STOPPING: {DaemonState.STOPPED, DaemonState.FAILED},
    }
    if target not in allowed[current]:
        raise DaemonStateError(f"Invalid daemon transition: {current} -> {target}")


@dataclass(frozen=True)
class DaemonConfig:
    cycle_interval: float

    def __post_init__(self) -> None:
        if (isinstance(self.cycle_interval, bool)
                or not isinstance(self.cycle_interval, (int, float))
                or not 0 < self.cycle_interval < float("inf")):
            raise ValueError("cycle_interval must be a finite positive number")


@dataclass(frozen=True)
class DaemonSnapshot:
    state: DaemonState
    cycles: int
    last_supervision: RuntimeSupervisorSnapshot | None


class OperationalDaemon:
    """Drive supervision in the caller's thread.

    Standalone cycles are allowed while STOPPED with an externally started
    supervisor. During run_forever only its owning thread may drive cycles.
    Cycle counts and observations persist across runs, including observations
    completed before an unexpected recovery exception.
    """

    def __init__(self, supervisor: RuntimeSupervisor, config: DaemonConfig) -> None:
        if not isinstance(supervisor, RuntimeSupervisor):
            raise TypeError("supervisor must be RuntimeSupervisor")
        if not isinstance(config, DaemonConfig):
            raise TypeError("config must be DaemonConfig")
        self._supervisor = supervisor
        self._config = config
        self._lock = RLock()
        self._stop_event = Event()
        self._state = DaemonState.STOPPED
        self._cycles = 0
        self._last_supervision = None
        self._runner = None
        self._cycle_busy = False

    @property
    def state(self) -> DaemonState:
        with self._lock:
            return self._state

    def _transition(self, target: DaemonState) -> None:
        with self._lock:
            _validate_transition(self._state, target)
            self._state = target

    def snapshot(self) -> DaemonSnapshot:
        with self._lock:
            return DaemonSnapshot(self._state, self._cycles, self._last_supervision)

    def request_stop(self) -> None:
        self._stop_event.set()

    def _cycle_failure(self, error: Exception) -> None:
        # Standalone cycles begin with an externally running supervisor.
        if self.state is DaemonState.STOPPED:
            self._transition(DaemonState.STARTING)
        self._transition(DaemonState.FAILED)
        failure = DaemonCycleError("Daemon cycle failed")
        try:
            self._supervisor.stop()
        except BaseException as cleanup_error:
            failure.add_note(f"Supervisor cleanup failed: {cleanup_error!r}")
        raise failure from error

    def run_once(self) -> RuntimeSupervisorSnapshot:
        with self._lock:
            if (self._cycle_busy
                    or self._runner not in (None, get_ident())
                    or self._state not in (DaemonState.STOPPED, DaemonState.RUNNING)):
                raise DaemonStateError("Daemon is not available for a cycle")
            self._cycle_busy = True
        try:
            if self._supervisor.state is not RuntimeState.RUNNING:
                raise DaemonStateError("A cycle requires a RUNNING supervisor")
            try:
                observation = self._supervisor.supervise_once()
                with self._lock:
                    self._cycles += 1
                    self._last_supervision = observation
                requested = set()
                for worker in observation.workers:
                    if worker.worker_id not in requested and (
                        worker.state is WorkerState.FAILED
                        or worker.health_status in (WorkerHealthStatus.UNHEALTHY,
                                                    WorkerHealthStatus.STALE)
                    ):
                        requested.add(worker.worker_id)
                        self._supervisor.recover(worker.worker_id)
                return observation
            except Exception as error:
                self._cycle_failure(error)
            except KeyboardInterrupt:
                self.request_stop()
                if self._runner is None:
                    self._transition(DaemonState.STARTING)
                    self._shutdown()
                raise
        finally:
            with self._lock:
                self._cycle_busy = False

    def _shutdown(self) -> None:
        self._transition(DaemonState.STOPPING)
        try:
            self._supervisor.stop()
        except BaseException as error:
            self._transition(DaemonState.FAILED)
            raise DaemonShutdownError("Supervisor shutdown failed") from error
        self._transition(DaemonState.STOPPED)

    def run_forever(self) -> None:
        with self._lock:
            if (self._runner is not None or self._cycle_busy
                    or self._state not in (DaemonState.STOPPED, DaemonState.FAILED)):
                raise DaemonStateError("Daemon is already executing")
            self._transition(DaemonState.STARTING)
            self._stop_event.clear()
            self._runner = get_ident()
        try:
            try:
                try:
                    self._supervisor.start()
                except Exception as error:
                    self._transition(DaemonState.FAILED)
                    raise DaemonStartupError("Supervisor startup failed") from error
                self._transition(DaemonState.RUNNING)
                try:
                    while not self._stop_event.is_set():
                        self.run_once()
                        if self._stop_event.wait(self._config.cycle_interval):
                            break
                except Exception as error:
                    if self.state is DaemonState.FAILED:
                        raise
                    self._cycle_failure(error)
            except KeyboardInterrupt:
                self.request_stop()
            self._shutdown()
        finally:
            with self._lock:
                self._runner = None
