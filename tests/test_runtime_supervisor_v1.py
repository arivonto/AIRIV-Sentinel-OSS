import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import inspect
from itertools import product

import pytest

import sentinel.worker as api
from sentinel.worker import (
    HealthMonitor, RestartPolicy, RuntimeState, RuntimeStateError,
    RuntimeSupervisor, WorkerHeartbeat, WorkerHealthStatus, WorkerId,
    WorkerInfo, WorkerNotFoundError, WorkerRegistry, WorkerShutdownError,
    WorkerStartupError, WorkerState, WorkerSupervisionError, validate_transition,
)
from sentinel.worker import health as health_module
from sentinel.worker import supervisor as module

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeWorker:
    def __init__(self, name, events):
        self.identity = WorkerId(name)
        self._state = WorkerState.REGISTERED
        self.events = events
        self.start_error = self.stop_error = self.heartbeat_error = None
        self.start_result = WorkerState.RUNNING
        self.stop_result = WorkerState.STOPPED
        self.healthy = True
        self.timestamp = NOW
        self.heartbeat_id = self.identity
        self.callback = lambda: None

    def worker_id(self):
        return self.identity

    def state(self):
        return self._state

    def transition(self, target):
        validate_transition(self._state, target)
        self._state = target

    def start(self):
        self.callback()
        self.events.append(('start', self.identity.value))
        self.transition(WorkerState.STARTING)
        if self.start_error:
            self.transition(WorkerState.FAILED)
            raise self.start_error
        self.transition(self.start_result)

    def stop(self):
        self.callback()
        self.events.append(('stop', self.identity.value))
        self.transition(WorkerState.STOPPING)
        if self.stop_error:
            self.transition(WorkerState.FAILED)
            raise self.stop_error
        self.transition(self.stop_result)

    def heartbeat(self):
        self.callback()
        self.events.append(('heartbeat', self.identity.value))
        if self.heartbeat_error:
            raise self.heartbeat_error
        return WorkerHeartbeat(self.heartbeat_id, self._state, self.timestamp, 0, 0, self.healthy)

    def health(self):
        raise AssertionError('redundant health call')


@pytest.fixture
def setup(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return NOW
    monkeypatch.setattr(health_module, 'datetime', Clock)
    registry = WorkerRegistry()
    events = []
    workers = [FakeWorker(name, events) for name in ('z', 'a', 'm')]
    for worker in workers:
        registry.register(worker, WorkerInfo(worker.identity, str(worker.identity), '1', ''))
    monitor = HealthMonitor(registry, 10)
    supervisor = RuntimeSupervisor(registry, monitor, RestartPolicy(3, 2, 5))
    return supervisor, registry, monitor, workers, events


def test_initial_and_exact_states(setup):
    supervisor, *_ = setup
    assert supervisor.state is RuntimeState.STOPPED
    names = {'STOPPED', 'STARTING', 'RUNNING', 'STOPPING', 'FAILED'}
    assert set(RuntimeState.__members__) == names
    assert {s.value for s in RuntimeState} == names
    assert all(isinstance(s, str) for s in RuntimeState)


@pytest.mark.parametrize('current,target', list(product(RuntimeState, repeat=2)))
def test_transition_matrix(current, target):
    allowed = {'STOPPED': {'STARTING'}, 'STARTING': {'RUNNING', 'FAILED', 'STOPPING'},
               'RUNNING': {'STOPPING', 'FAILED'}, 'FAILED': {'STARTING', 'STOPPING'},
               'STOPPING': {'STOPPED', 'FAILED'}}
    if target.value in allowed[current.value]:
        module._validate_transition(current, target)
    else:
        with pytest.raises(RuntimeStateError):
            module._validate_transition(current, target)


@pytest.mark.parametrize('values', [(-1, 0, 0), (True, 0, 0), (1.0, 0, 0),
    (1, -1, 0), (1, 2, 1), (1, float('nan'), 1), (1, 0, float('inf')),
    (1, True, 1), (1, '1', 1)])
def test_invalid_policy(values):
    with pytest.raises(ValueError):
        RestartPolicy(*values)


def test_backoff():
    policy = RestartPolicy(10, 2, 5)
    assert [policy.delay(i) for i in range(1, 5)] == [2, 4, 5, 5]
    assert policy.delay(10**100) == 5
    assert RestartPolicy().delay(10**100) == 0
    with pytest.raises(FrozenInstanceError):
        policy.max_retries = 100


@pytest.mark.parametrize('value', [0, -1, True, 1.5])
def test_invalid_retry_number(value):
    with pytest.raises(ValueError):
        RestartPolicy().delay(value)


@pytest.mark.parametrize('index', [0, 1, 2])
def test_invalid_dependencies(index):
    registry = WorkerRegistry()
    args = [registry, HealthMonitor(registry, 10), RestartPolicy()]
    args[index] = object()
    with pytest.raises(TypeError):
        RuntimeSupervisor(*args)


def test_empty_start_stop():
    registry = WorkerRegistry()
    supervisor = RuntimeSupervisor(registry, HealthMonitor(registry, 10))
    supervisor.start()
    assert supervisor.state is RuntimeState.RUNNING
    assert supervisor.supervise_once().workers == ()
    supervisor.stop()
    assert supervisor.state is RuntimeState.STOPPED


def test_start_stop_order_and_repeated_calls(setup):
    s, _, _, workers, events = setup
    s.start()
    assert events == [('start', name) for name in ('z', 'a', 'm')]
    assert all(w.state() is WorkerState.RUNNING for w in workers)
    with pytest.raises(RuntimeStateError):
        s.start()
    s.stop()
    assert events[3:] == [('stop', name) for name in ('m', 'a', 'z')]
    assert s.state is RuntimeState.STOPPED
    before = list(events)
    s.stop()
    assert events == before
    s.start()
    assert s.state is RuntimeState.RUNNING


def test_running_start_and_stopped_stop_are_skipped(setup):
    s, _, _, workers, events = setup
    workers[0].start()
    events.clear()
    s.start()
    assert ('start', 'z') not in events
    workers[0].stop()
    events.clear()
    s.stop()
    assert ('stop', 'z') not in events


@pytest.mark.parametrize('failure', ['exception', 'failed', 'starting', 'stopping', 'invalid'])
def test_start_failure_captured(setup, failure):
    s, _, _, workers, _ = setup
    worker = workers[0]
    if failure == 'exception':
        worker.start_error = RuntimeError('startup broke')
    elif failure == 'failed':
        worker.start_result = WorkerState.FAILED
    elif failure == 'invalid':
        worker._state = 'RUNNING'
    else:
        worker._state = WorkerState[failure.upper()]
    with pytest.raises(WorkerStartupError):
        s.start()
    assert s.state is RuntimeState.FAILED
    if failure != 'invalid':
        assert s.snapshot().workers[0].last_exception
    if failure == 'exception':
        assert 'startup broke' in s.snapshot().workers[0].last_exception
        worker.start_error = None
        s.start()
        assert s.state is RuntimeState.RUNNING


@pytest.mark.parametrize('failure', ['exception', 'failed_result', 'starting', 'failed'])
def test_shutdown_continues_and_fails_closed(setup, failure):
    s, _, _, workers, events = setup
    s.start()
    if failure == 'exception':
        workers[1].stop_error = RuntimeError('stop broke')
    elif failure == 'failed_result':
        workers[1].stop_result = WorkerState.FAILED
    else:
        workers[1]._state = WorkerState[failure.upper()]
    events.clear()
    with pytest.raises(WorkerShutdownError):
        s.stop()
    assert s.state is RuntimeState.FAILED
    assert workers[0].state() is workers[2].state() is WorkerState.STOPPED
    assert events[0] == ('stop', 'm') and events[-1] == ('stop', 'z')
    assert s.snapshot().workers[1].last_exception


def test_stop_after_partial_start_skips_registered(setup):
    s, _, _, workers, _ = setup
    workers[0].start_error = RuntimeError('failure')
    with pytest.raises(WorkerStartupError):
        s.start()
    with pytest.raises(WorkerShutdownError):
        s.stop()
    assert workers[1].state() is WorkerState.REGISTERED


def test_supervision_requires_running(setup):
    with pytest.raises(RuntimeStateError):
        setup[0].supervise_once()


def test_supervision_records_ordered_immutable_snapshot(setup):
    s, registry, monitor, workers, events = setup
    s.start()
    events.clear()
    snapshot = s.supervise_once()
    assert events == [('heartbeat', name) for name in ('z', 'a', 'm')]
    assert isinstance(snapshot.workers, tuple)
    assert tuple(w.worker_id for w in snapshot.workers) == registry.worker_ids()
    for w in snapshot.workers:
        assert w.state is WorkerState.RUNNING
        assert w.health_status is WorkerHealthStatus.HEALTHY
        assert w.last_heartbeat is monitor.last_heartbeat(w.worker_id)
        with pytest.raises(FrozenInstanceError):
            w.restart_count = 99
    with pytest.raises(FrozenInstanceError):
        snapshot.state = RuntimeState.FAILED
    workers[0].timestamp += timedelta(seconds=1)
    workers[0].healthy = False
    s.supervise_once()
    assert snapshot.workers[0].last_heartbeat.healthy


@pytest.mark.parametrize('failure', ['identity', 'exception', 'invalid_heartbeat', 'state'])
def test_supervision_errors_continue_and_are_captured(setup, failure):
    s, _, monitor, workers, _ = setup
    s.start()
    if failure == 'identity':
        workers[0].heartbeat_id = workers[1].identity
    elif failure == 'exception':
        workers[0].heartbeat_error = RuntimeError('heartbeat broke')
    elif failure == 'invalid_heartbeat':
        workers[0].heartbeat = lambda: None
    else:
        workers[0].state = lambda: 'RUNNING'
    with pytest.raises(WorkerSupervisionError):
        s.supervise_once()
    assert monitor.last_heartbeat(workers[0].identity) is None
    assert monitor.last_heartbeat(workers[2].identity) is not None
    if failure != 'state':
        assert s.snapshot().workers[0].last_exception


@pytest.mark.parametrize('condition', ['healthy', 'unknown', 'failed', 'unhealthy', 'stale'])
def test_recovery_eligibility(setup, condition):
    s, _, monitor, workers, events = setup
    s.start()
    worker = workers[0]
    if condition == 'failed':
        worker.transition(WorkerState.FAILED)
    elif condition != 'unknown':
        worker.healthy = condition != 'unhealthy'
        heartbeat = worker.heartbeat()
        if condition == 'stale':
            heartbeat = replace(heartbeat, timestamp=NOW - timedelta(seconds=11))
        monitor.record(heartbeat)
    events.clear()
    eligible = condition in ('failed', 'unhealthy', 'stale')
    assert s.recover(worker.identity) is eligible
    assert s.snapshot().workers[0].restart_count == int(eligible)
    if eligible:
        assert worker.state() is WorkerState.RUNNING
        assert ('start', 'z') in events
        assert (('stop', 'z') in events) is (condition != 'failed')
        assert monitor.last_heartbeat(worker.identity) is not None
    else:
        assert events == []


def test_retries_history_and_error(setup):
    s, registry, _, workers, events = setup
    s.start()
    worker = workers[0]
    worker.transition(WorkerState.FAILED)
    worker.start_error = RuntimeError('restart broke')
    old = s.restart_history(worker.identity)
    for _ in range(4):
        assert not s.recover(worker.identity)
    history = s.restart_history(worker.identity)
    assert old == () and isinstance(history, tuple)
    assert [r.attempt for r in history] == [1, 2, 3]
    assert [r.backoff for r in history] == [2, 4, 5]
    assert all(not r.succeeded and 'restart broke' in r.error for r in history)
    assert s.snapshot().workers[0].restart_count == 3
    assert events.count(('start', 'z')) == 4
    with pytest.raises(FrozenInstanceError):
        history[0].error = None
    registry.unregister(worker.identity)
    assert worker.identity not in [w.worker_id for w in s.snapshot().workers]
    for operation in (s.recover, s.restart_history):
        with pytest.raises(WorkerNotFoundError):
            operation(worker.identity)


def test_default_policy_no_retries(setup):
    _, registry, monitor, workers, events = setup
    s = RuntimeSupervisor(registry, monitor)
    s.start()
    workers[0].transition(WorkerState.FAILED)
    events.clear()
    assert not s.recover(workers[0].identity)
    assert events == [] and s.restart_history(workers[0].identity) == ()


@pytest.mark.parametrize('failure', ['stop', 'start_result', 'heartbeat'])
def test_recovery_failure_recorded(setup, failure):
    s, _, _, workers, _ = setup
    s.start()
    worker = workers[0]
    worker.healthy = False
    s.supervise_once()
    if failure == 'stop':
        worker.stop_error = RuntimeError('stop failed')
    elif failure == 'start_result':
        worker.start_result = WorkerState.FAILED
    else:
        worker.heartbeat_error = RuntimeError('heartbeat failed')
    assert not s.recover(worker.identity)
    record = s.restart_history(worker.identity)[0]
    assert not record.succeeded and record.error
    assert s.snapshot().workers[0].restart_count == 1


def test_no_lock_held_during_external_calls_and_overlap_rejected(setup):
    s, _, _, workers, _ = setup
    def callback():
        assert not s._lock._is_owned()
        with pytest.raises(RuntimeStateError):
            s.stop()
    for worker in workers:
        worker.callback = callback
    s.start()
    s.supervise_once()
    workers[0].transition(WorkerState.FAILED)
    assert s.recover(workers[0].identity)
    s.stop()


def test_unknown_recovery_and_stopped_runtime(setup):
    s, _, _, workers, _ = setup
    with pytest.raises(WorkerNotFoundError):
        s.recover(WorkerId('missing'))
    with pytest.raises(RuntimeStateError):
        s.recover(workers[0].identity)


def test_no_background_execution_and_boundary(setup, monkeypatch):
    import threading
    import time
    def forbidden(*args, **kwargs):
        raise AssertionError('background execution or sleeping')
    monkeypatch.setattr(threading.Thread, 'start', forbidden)
    monkeypatch.setattr(time, 'sleep', forbidden)
    _, registry, monitor, workers, _ = setup
    s = RuntimeSupervisor(registry, monitor, RestartPolicy(1, 1, 1))
    s.start()
    s.supervise_once()
    workers[0].transition(WorkerState.FAILED)
    assert s.recover(workers[0].identity)
    s.stop()
    source = inspect.getsource(module)
    for name in ('Incident', 'IncidentManager', 'Investigation', 'Diagnosis',
                 'DiagnosisEvaluator', 'Commander', 'CommanderIntent',
                 'CommanderSemanticPolicy', 'Remediation', 'RemediationPolicy',
                 'FinalOutcomeMapper', 'ExecutionBoundary', 'Verification'):
        assert name not in source
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert isinstance(node, ast.ImportFrom)
            assert node.module in {'contextlib', 'dataclasses', 'enum', 'math',
                                   'threading', 'health', 'models', 'registry', 'state'}


def test_public_exports():
    names = {'RuntimeState', 'RestartPolicy', 'WorkerRestartRecord',
             'WorkerSupervisionSnapshot', 'RuntimeSupervisorSnapshot',
             'RuntimeSupervisor', 'RuntimeSupervisorError', 'RuntimeStateError',
             'WorkerStartupError', 'WorkerShutdownError', 'WorkerSupervisionError'}
    assert names <= set(api.__all__)
    for name in names:
        assert getattr(api, name) is getattr(module, name)
    for name in ('RuntimeStateError', 'WorkerStartupError', 'WorkerShutdownError', 'WorkerSupervisionError'):
        assert issubclass(getattr(api, name), api.RuntimeSupervisorError)
