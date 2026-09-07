"""Thread-safe registration and lookup of workers and their metadata."""

from dataclasses import dataclass
from threading import RLock

from .models import WorkerId, WorkerInfo
from .protocol import WorkerProtocol


class WorkerRegistryError(Exception):
    """Base exception for registry failures."""


class DuplicateWorkerError(WorkerRegistryError, ValueError):
    """A worker with this identity is already registered."""


class WorkerNotFoundError(WorkerRegistryError, LookupError):
    """The requested worker is not registered."""


class WorkerIdentityMismatchError(WorkerRegistryError, ValueError):
    """Worker identity and metadata identity disagree."""


class InvalidWorkerError(WorkerRegistryError, ValueError):
    """The supplied registration does not satisfy the worker contract."""


@dataclass(frozen=True)
class _WorkerRegistration:
    worker: WorkerProtocol
    info: WorkerInfo


class WorkerRegistry:
    """Store registrations in insertion order without managing workers."""

    def __init__(self) -> None:
        self._registrations: dict[WorkerId, _WorkerRegistration] = {}
        self._lock = RLock()

    def register(self, worker: WorkerProtocol, info: WorkerInfo) -> None:
        if not isinstance(worker, WorkerProtocol):
            raise InvalidWorkerError("worker must satisfy WorkerProtocol")
        if not isinstance(info, WorkerInfo):
            raise InvalidWorkerError("info must be WorkerInfo")
        worker_id = worker.worker_id()
        if not isinstance(worker_id, WorkerId) or not isinstance(info.worker_id, WorkerId):
            raise InvalidWorkerError("worker and metadata identities must be WorkerId")
        if worker_id != info.worker_id:
            raise WorkerIdentityMismatchError(
                f"Worker identity {worker_id!r} differs from metadata {info.worker_id!r}"
            )
        with self._lock:
            if worker_id in self._registrations:
                raise DuplicateWorkerError(f"Worker already registered: {worker_id}")
            self._registrations[worker_id] = _WorkerRegistration(worker, info)

    def get(self, worker_id: WorkerId) -> WorkerProtocol:
        with self._lock:
            return self._get_registration(worker_id).worker

    def get_info(self, worker_id: WorkerId) -> WorkerInfo:
        with self._lock:
            return self._get_registration(worker_id).info

    def _get_registration(self, worker_id: WorkerId) -> _WorkerRegistration:
        """Look up a registration while the caller holds the lock."""
        try:
            return self._registrations[worker_id]
        except KeyError:
            raise WorkerNotFoundError(f"Worker not registered: {worker_id}") from None

    def worker_ids(self) -> tuple[WorkerId, ...]:
        with self._lock:
            return tuple(self._registrations)

    def workers(self) -> tuple[WorkerProtocol, ...]:
        with self._lock:
            return tuple(entry.worker for entry in self._registrations.values())

    def worker_infos(self) -> tuple[WorkerInfo, ...]:
        with self._lock:
            return tuple(entry.info for entry in self._registrations.values())

    def contains(self, worker_id: WorkerId) -> bool:
        with self._lock:
            return worker_id in self._registrations

    def __len__(self) -> int:
        with self._lock:
            return len(self._registrations)

    def unregister(self, worker_id: WorkerId) -> WorkerProtocol:
        with self._lock:
            try:
                return self._registrations.pop(worker_id).worker
            except KeyError:
                raise WorkerNotFoundError(f"Worker not registered: {worker_id}") from None
