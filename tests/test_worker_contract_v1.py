from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo
from itertools import product

import pytest

from sentinel.worker import (
    WorkerHeartbeat,
    WorkerId,
    WorkerInfo,
    WorkerProtocol,
    WorkerState,
    WorkerTransitionError,
    can_transition,
    validate_transition,
)


def test_exact_states():
    names = {"REGISTERED", "STARTING", "RUNNING", "FAILED", "STOPPING", "STOPPED"}
    assert set(WorkerState.__members__) == names
    assert {state.value for state in WorkerState} == names
    assert all(isinstance(state, str) for state in WorkerState)


@pytest.mark.parametrize("current,target", list(product(WorkerState, repeat=2)))
def test_all_lifecycle_transitions(current, target):
    allowed = {
        "REGISTERED": {"STARTING"},
        "STARTING": {"RUNNING", "FAILED"},
        "RUNNING": {"STOPPING", "FAILED"},
        "STOPPING": {"STOPPED", "FAILED"},
        "FAILED": {"STARTING"},
        "STOPPED": {"STARTING"},
    }
    expected = target.value in allowed[current.value]
    assert can_transition(current, target) is expected
    if expected:
        assert validate_transition(current, target) is None
    else:
        with pytest.raises(WorkerTransitionError):
            validate_transition(current, target)
    assert issubclass(WorkerTransitionError, ValueError)


def test_worker_id_value_semantics():
    worker_id = WorkerId(" worker-1 ")
    assert str(worker_id) == " worker-1 "
    assert worker_id == WorkerId(" worker-1 ")
    assert worker_id != WorkerId("worker-2")
    assert len({worker_id, WorkerId(" worker-1 ")}) == 1
    with pytest.raises(FrozenInstanceError):
        worker_id.value = "changed"


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_worker_id_rejects_blank(value):
    with pytest.raises(ValueError):
        WorkerId(value)


def test_worker_info():
    info = WorkerInfo(WorkerId("worker-1"), "Worker", "1.0", "")
    assert info.description == ""
    for field in ("worker_id", "name", "version", "description"):
        with pytest.raises(FrozenInstanceError):
            setattr(info, field, getattr(info, field))


@pytest.mark.parametrize("field", ["name", "version"])
@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_worker_info_rejects_blank(field, value):
    fields = dict(worker_id=WorkerId("worker-1"), name="Worker", version="1", description="")
    fields[field] = value
    with pytest.raises(ValueError):
        WorkerInfo(**fields)


@pytest.fixture
def heartbeat():
    return WorkerHeartbeat(
        WorkerId("worker-1"), WorkerState.RUNNING,
        datetime(2026, 1, 1, tzinfo=timezone.utc), 0.0, 0, True,
    )


def test_heartbeat_valid_and_immutable(heartbeat):
    assert heartbeat.uptime == 0.0
    assert heartbeat.iteration == 0
    assert heartbeat.healthy is True
    for field in ("worker_id", "state", "timestamp", "uptime", "iteration", "healthy"):
        with pytest.raises(FrozenInstanceError):
            setattr(heartbeat, field, getattr(heartbeat, field))


@pytest.mark.parametrize("field,value", [
    ("uptime", -0.1), ("uptime", float("nan")), ("iteration", -1),
    ("timestamp", datetime(2026, 1, 1)),
    ("healthy", 0), ("healthy", 1), ("healthy", "true"), ("healthy", None),
])
def test_heartbeat_rejects_invalid_fields(heartbeat, field, value):
    with pytest.raises(ValueError):
        replace(heartbeat, **{field: value})


@pytest.mark.parametrize("offset", [0, 7, -5])
def test_heartbeat_accepts_aware_timestamp(heartbeat, offset):
    timestamp = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=offset)))
    assert replace(heartbeat, timestamp=timestamp, healthy=False).timestamp == timestamp


def test_heartbeat_rejects_tzinfo_without_offset(heartbeat):
    class NoOffset(tzinfo):
        def utcoffset(self, dt):
            return None

    with pytest.raises(ValueError):
        replace(heartbeat, timestamp=datetime(2026, 1, 1, tzinfo=NoOffset()))


def test_runtime_protocol(heartbeat):
    class CompliantWorker:
        def worker_id(self) -> WorkerId:
            return heartbeat.worker_id

        def state(self) -> WorkerState:
            return heartbeat.state

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def heartbeat(self) -> WorkerHeartbeat:
            return heartbeat

        def health(self) -> bool:
            return heartbeat.healthy

    class IncompleteWorker:
        def worker_id(self) -> WorkerId:
            return heartbeat.worker_id

    assert isinstance(CompliantWorker(), WorkerProtocol)
    assert not isinstance(IncompleteWorker(), WorkerProtocol)
    assert not isinstance(object(), WorkerProtocol)
    for method in ("worker_id", "state", "start", "stop", "heartbeat", "health"):
        assert callable(getattr(WorkerProtocol, method))
