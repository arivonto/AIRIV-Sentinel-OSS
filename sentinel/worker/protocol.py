"""Structural contract implemented by operational workers."""

from typing import Protocol, runtime_checkable

from .models import WorkerHeartbeat, WorkerId
from .state import WorkerState


@runtime_checkable
class WorkerProtocol(Protocol):
    def worker_id(self) -> WorkerId: ...

    def state(self) -> WorkerState: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def heartbeat(self) -> WorkerHeartbeat: ...

    def health(self) -> bool: ...
