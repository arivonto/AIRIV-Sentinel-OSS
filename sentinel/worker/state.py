"""Canonical, side-effect-free worker lifecycle validation."""

from enum import Enum


class WorkerState(str, Enum):
    REGISTERED = "REGISTERED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class WorkerTransitionError(ValueError):
    """Raised when a worker lifecycle transition is invalid."""


_ALLOWED_TRANSITIONS = frozenset({
    (WorkerState.REGISTERED, WorkerState.STARTING),
    (WorkerState.STARTING, WorkerState.RUNNING),
    (WorkerState.STARTING, WorkerState.FAILED),
    (WorkerState.RUNNING, WorkerState.STOPPING),
    (WorkerState.RUNNING, WorkerState.FAILED),
    (WorkerState.STOPPING, WorkerState.STOPPED),
    (WorkerState.STOPPING, WorkerState.FAILED),
    (WorkerState.FAILED, WorkerState.STARTING),
    (WorkerState.STOPPED, WorkerState.STARTING),
})


def can_transition(current: WorkerState, target: WorkerState) -> bool:
    return (current, target) in _ALLOWED_TRANSITIONS


def validate_transition(current: WorkerState, target: WorkerState) -> None:
    if not can_transition(current, target):
        raise WorkerTransitionError(
            f"Invalid worker transition: {current!r} -> {target!r}"
        )
