from dataclasses import FrozenInstanceError
import inspect
from itertools import product
from threading import Event, Thread

import pytest

import sentinel.worker as api
from sentinel.worker import daemon as module
from sentinel.worker import (
    DaemonConfig, DaemonState, DaemonStateError, DaemonStartupError,
    DaemonCycleError, DaemonShutdownError, OperationalDaemon,
    RuntimeSupervisor, RuntimeSupervisorSnapshot, RuntimeState,
    WorkerSupervisionSnapshot, WorkerState, WorkerHealthStatus, WorkerId,
    WorkerRegistry, HealthMonitor, RestartPolicy,
)


class FakeSupervisor(RuntimeSupervisor):
    def __init__(self):
        self.current = RuntimeState.STOPPED
        self.calls = []
        self.observation = RuntimeSupervisorSnapshot(RuntimeState.RUNNING, ())
        self.errors = {}
        self.callback = lambda operation: None

    @property
    def state(self):
        return self.current

    def invoke(self, operation):
        self.calls.append(operation)
        self.callback(operation)
        if operation in self.errors:
            raise self.errors[operation]

    def start(self):
        self.invoke('start')
        self.current = RuntimeState.RUNNING

    def stop(self):
        self.invoke('stop')
        self.current = RuntimeState.STOPPED

    def supervise_once(self):
        self.invoke('cycle')
        return self.observation

    def recover(self, worker_id):
        self.invoke(('recover', worker_id))
        return False


@pytest.fixture
def setup():
    supervisor = FakeSupervisor()
    return supervisor, OperationalDaemon(supervisor, DaemonConfig(0.01))


def worker(name='w', state=WorkerState.RUNNING, health=WorkerHealthStatus.HEALTHY):
    return WorkerSupervisionSnapshot(WorkerId(name), state, health, 999, None, None)


def test_exact_states_and_initial_snapshot(setup):
    _, daemon = setup
    names = {'STOPPED', 'STARTING', 'RUNNING', 'STOPPING', 'FAILED'}
    assert set(DaemonState.__members__) == names
    assert {s.value for s in DaemonState} == names
    assert all(isinstance(s, str) for s in DaemonState)
    assert daemon.state is DaemonState.STOPPED
    assert daemon.snapshot() == api.DaemonSnapshot(DaemonState.STOPPED, 0, None)


@pytest.mark.parametrize('current,target', list(product(DaemonState, repeat=2)))
def test_transitions(current, target):
    allowed = {'STOPPED': {'STARTING'}, 'STARTING': {'RUNNING', 'FAILED', 'STOPPING'},
               'RUNNING': {'STOPPING', 'FAILED'}, 'FAILED': {'STARTING', 'STOPPING'},
               'STOPPING': {'STOPPED', 'FAILED'}}
    if target.value in allowed[current.value]:
        module._validate_transition(current, target)
    else:
        with pytest.raises(DaemonStateError):
            module._validate_transition(current, target)


@pytest.mark.parametrize('interval', [0, -1, True, None, '1', float('nan'), float('inf')])
def test_invalid_config(interval):
    with pytest.raises(ValueError):
        DaemonConfig(interval)


def test_config_and_snapshot_frozen(setup):
    config = DaemonConfig(1.5)
    assert config.cycle_interval == 1.5
    with pytest.raises(FrozenInstanceError):
        config.cycle_interval = 2
    for field in ('state', 'cycles', 'last_supervision'):
        with pytest.raises(FrozenInstanceError):
            setattr(setup[1].snapshot(), field, None)


@pytest.mark.parametrize('index', [0, 1])
def test_dependency_validation(setup, index):
    args = [setup[0], DaemonConfig(1)]
    args[index] = object()
    with pytest.raises(TypeError):
        OperationalDaemon(*args)


def test_cycle_requires_operational_supervisor(setup):
    s, d = setup
    with pytest.raises(DaemonStateError):
        d.run_once()
    assert s.calls == [] and d.snapshot().cycles == 0


@pytest.mark.parametrize('state,health', list(product(WorkerState, WorkerHealthStatus)))
def test_recovery_eligibility_and_no_mutation(setup, state, health):
    s, d = setup
    s.current = RuntimeState.RUNNING
    entry = worker(state=state, health=health)
    s.observation = RuntimeSupervisorSnapshot(RuntimeState.RUNNING, (entry, entry))
    old = d.snapshot()
    assert d.run_once() is s.observation
    expected = state is WorkerState.FAILED or health in (WorkerHealthStatus.UNHEALTHY, WorkerHealthStatus.STALE)
    assert s.calls == ['cycle'] + ([('recover', entry.worker_id)] if expected else [])
    assert entry.state is state and entry.restart_count == 999
    assert d.snapshot().cycles == 1 and old.cycles == 0
    assert d.snapshot().last_supervision is s.observation


def test_order_and_one_retry_opportunity_per_cycle(setup):
    s, d = setup
    s.current = RuntimeState.RUNNING
    entries = tuple(worker(name, health=WorkerHealthStatus.STALE) for name in ('z', 'a', 'm'))
    s.observation = RuntimeSupervisorSnapshot(RuntimeState.RUNNING, entries)
    for count in range(1, 4):
        d.run_once()
        assert d.snapshot().cycles == count
    assert s.calls == (['cycle'] + [('recover', w.worker_id) for w in entries]) * 3


def test_forever_lifecycle_no_background_thread_or_sleep(setup, monkeypatch):
    import time
    s, d = setup
    def forbidden(*args, **kwargs):
        pytest.fail('internal thread or sleep')
    monkeypatch.setattr(Thread, 'start', forbidden)
    monkeypatch.setattr(time, 'sleep', forbidden)
    def callback(op):
        assert not d._lock._is_owned()
        assert d.state is {'start': DaemonState.STARTING, 'cycle': DaemonState.RUNNING,
                           'stop': DaemonState.STOPPING}[op]
        if op == 'cycle':
            d.request_stop()
            d.request_stop()
            assert s.calls == ['start', 'cycle']
    s.callback = callback
    d.run_forever()
    assert s.calls == ['start', 'cycle', 'stop']
    assert d.state is DaemonState.STOPPED


def test_event_wait_controls_cycles(setup, monkeypatch):
    s, d = setup
    waits = []
    def wait(interval):
        waits.append(interval)
        assert s.calls.count('cycle') == len(waits)
        if len(waits) == 3:
            d.request_stop()
        return d._stop_event.is_set()
    monkeypatch.setattr(d._stop_event, 'wait', wait)
    d.run_forever()
    assert waits == [0.01] * 3
    assert d.snapshot().cycles == 3
    assert s.calls.count('start') == s.calls.count('stop') == 1


def test_real_event_interruptible_and_concurrent_runner_rejected(setup, monkeypatch):
    s, d = setup
    waiting = Event()
    original_wait = d._stop_event.wait
    errors = []
    def wait(interval):
        waiting.set()
        return original_wait(30)
    monkeypatch.setattr(d._stop_event, 'wait', wait)
    def run():
        try:
            d.run_forever()
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=run)
    thread.start()
    try:
        assert waiting.wait(5)
        for operation in (d.run_forever, d.run_once):
            with pytest.raises(DaemonStateError):
                operation()
    finally:
        d.request_stop()
        thread.join(5)
    assert not thread.is_alive() and not errors
    assert s.calls == ['start', 'cycle', 'stop']
    assert d.state is DaemonState.STOPPED


@pytest.mark.parametrize('operation', ['start', 'cycle', 'stop'])
def test_failures(setup, operation):
    s, d = setup
    primary = RuntimeError(operation)
    s.errors[operation] = primary
    s.callback = lambda op: d.request_stop() if op == 'cycle' else None
    expected = {'start': DaemonStartupError, 'cycle': DaemonCycleError, 'stop': DaemonShutdownError}[operation]
    with pytest.raises(expected) as caught:
        d.run_forever()
    assert caught.value.__cause__ is primary
    assert d.state is DaemonState.FAILED
    assert s.calls == (['start'] if operation == 'start' else ['start', 'cycle', 'stop'])
    assert d.snapshot().cycles == int(operation == 'stop')


@pytest.mark.parametrize('standalone', [False, True])
def test_primary_failure_preserved_when_cleanup_fails(setup, standalone):
    s, d = setup
    primary = RuntimeError('primary')
    s.errors = {'cycle': primary, 'stop': RuntimeError('cleanup')}
    if standalone:
        s.current = RuntimeState.RUNNING
    with pytest.raises(DaemonCycleError) as caught:
        (d.run_once if standalone else d.run_forever)()
    assert caught.value.__cause__ is primary
    assert 'cleanup' in caught.value.__notes__[0]
    assert s.calls.count('stop') == 1
    assert d.state is DaemonState.FAILED


def test_recovery_exception_keeps_completed_observation(setup):
    s, d = setup
    entry = worker(state=WorkerState.FAILED)
    s.observation = RuntimeSupervisorSnapshot(RuntimeState.RUNNING, (entry,))
    s.errors[('recover', entry.worker_id)] = RuntimeError('recovery infrastructure')
    with pytest.raises(DaemonCycleError):
        d.run_forever()
    assert s.calls.count('stop') == 1
    assert d.snapshot().cycles == 1
    assert d.snapshot().last_supervision is s.observation


@pytest.mark.parametrize('where', ['start', 'cycle', 'wait', 'recover'])
def test_keyboard_interrupt_shutdown(setup, monkeypatch, where):
    s, d = setup
    if where == 'wait':
        def interrupt(interval):
            raise KeyboardInterrupt()
        monkeypatch.setattr(d._stop_event, 'wait', interrupt)
    elif where == 'recover':
        entry = worker(state=WorkerState.FAILED)
        s.observation = RuntimeSupervisorSnapshot(RuntimeState.RUNNING, (entry,))
        s.errors[('recover', entry.worker_id)] = KeyboardInterrupt()
    else:
        s.errors[where] = KeyboardInterrupt()
    d.run_forever()
    assert s.calls.count('stop') == 1
    assert d.state is DaemonState.STOPPED


def test_reentrant_cycle_rejected_and_external_calls_unlocked(setup):
    s, d = setup
    s.current = RuntimeState.RUNNING
    entry = worker(state=WorkerState.FAILED)
    s.observation = RuntimeSupervisorSnapshot(RuntimeState.RUNNING, (entry,))
    def callback(op):
        assert not d._lock._is_owned()
        for operation in (d.run_once, d.run_forever):
            with pytest.raises(DaemonStateError):
                operation()
    s.callback = callback
    d.run_once()
    assert s.calls == ['cycle', ('recover', entry.worker_id)]


def test_concurrent_standalone_cycle_rejected(setup):
    s, d = setup
    s.current = RuntimeState.RUNNING
    entered, release = Event(), Event()
    errors = []
    def callback(op):
        entered.set()
        assert release.wait(5)
    s.callback = callback
    def run():
        try:
            d.run_once()
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(DaemonStateError):
            d.run_once()
        with pytest.raises(DaemonStateError):
            d.run_forever()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors
    assert s.calls == ['cycle']


def test_restart_after_failure_and_stop_event_cleared(setup):
    s, d = setup
    s.errors['start'] = RuntimeError('start')
    with pytest.raises(DaemonStartupError):
        d.run_forever()
    s.errors.clear()
    s.callback = lambda op: d.request_stop() if op == 'cycle' else None
    d.request_stop()
    d.run_forever()
    d.run_forever()
    assert d.state is DaemonState.STOPPED and d.snapshot().cycles == 2


def test_actual_supervisor_retry_policy_is_authoritative(monkeypatch):
    from datetime import datetime, timezone
    class Worker:
        def __init__(self):
            self.current = WorkerState.REGISTERED
            self.starts = 0
        def worker_id(self):
            return WorkerId('w')
        def state(self):
            return self.current
        def start(self):
            self.starts += 1
            self.current = WorkerState.RUNNING
        def stop(self):
            self.current = WorkerState.STOPPED
        def heartbeat(self):
            return api.WorkerHeartbeat(self.worker_id(), self.current,
                                       datetime.now(timezone.utc), 0, 0, False)
        def health(self):
            pytest.fail('duplicate health polling')
    registry = WorkerRegistry()
    w = Worker()
    registry.register(w, api.WorkerInfo(w.worker_id(), 'w', '1', ''))
    s = RuntimeSupervisor(registry, HealthMonitor(registry, 10), RestartPolicy(2, 1, 2))
    d = OperationalDaemon(s, DaemonConfig(0.01))
    def wait(interval):
        if d.snapshot().cycles == 4:
            d.request_stop()
        return d._stop_event.is_set()
    monkeypatch.setattr(d._stop_event, 'wait', wait)
    d.run_forever()
    assert w.starts == 3
    assert [r.backoff for r in s.restart_history(w.worker_id())] == [1, 2]
    assert d.snapshot().cycles == 4


def test_exports_and_boundary():
    names = {'DaemonState', 'DaemonConfig', 'DaemonSnapshot', 'OperationalDaemon',
             'OperationalDaemonError', 'DaemonStateError', 'DaemonStartupError',
             'DaemonCycleError', 'DaemonShutdownError'}
    assert names <= set(api.__all__)
    for name in names:
        assert getattr(api, name) is getattr(module, name)
        if name.endswith('Error'):
            assert issubclass(getattr(api, name), api.OperationalDaemonError)
    source = inspect.getsource(module)
    for name in ('Incident', 'IncidentManager', 'Investigation', 'Diagnosis',
                 'DiagnosisEvaluator', 'Commander', 'CommanderIntent',
                 'CommanderSemanticPolicy', 'Remediation', 'RemediationPolicy',
                 'FinalOutcomeMapper', 'ExecutionBoundary', 'Verification',
                 'max_retries', 'restart_history', 'backoff', 'heartbeat('):
        assert name not in source


def test_standalone_interrupt_cleans_up(setup):
    s, d = setup
    s.current = RuntimeState.RUNNING
    s.errors['cycle'] = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        d.run_once()
    assert s.calls == ['cycle', 'stop']
    assert d.state is DaemonState.STOPPED


def test_wait_exception_cleans_up_once(setup, monkeypatch):
    s, d = setup
    primary = RuntimeError('wait failed')
    def wait(interval):
        raise primary
    monkeypatch.setattr(d._stop_event, 'wait', wait)
    with pytest.raises(DaemonCycleError) as caught:
        d.run_forever()
    assert caught.value.__cause__ is primary
    assert s.calls == ['start', 'cycle', 'stop']
    assert d.state is DaemonState.FAILED


def test_interrupt_shutdown_failure(setup):
    s, d = setup
    s.errors = {'cycle': KeyboardInterrupt(), 'stop': RuntimeError('stop')}
    with pytest.raises(DaemonShutdownError):
        d.run_forever()
    assert s.calls == ['start', 'cycle', 'stop']
    assert d.state is DaemonState.FAILED
