"""Immutable worker identity, metadata, and heartbeat values."""

from dataclasses import dataclass
from datetime import datetime

from .state import WorkerState


@dataclass(frozen=True)
class WorkerId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("value must be a non-empty string")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class WorkerInfo:
    worker_id: WorkerId
    name: str
    version: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: WorkerId
    state: WorkerState
    timestamp: datetime
    uptime: float
    iteration: int
    healthy: bool

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.uptime >= 0:
            raise ValueError("uptime must be non-negative")
        if not self.iteration >= 0:
            raise ValueError("iteration must be non-negative")
        if not isinstance(self.healthy, bool):
            raise ValueError("healthy must be a bool")
