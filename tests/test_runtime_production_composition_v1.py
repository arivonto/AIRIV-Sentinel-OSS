"""Production wiring with real Phase 2 infrastructure and isolated lifecycle."""

import ast
from dataclasses import FrozenInstanceError, fields, replace
import inspect
from threading import Thread
from unittest.mock import Mock, call

import pytest

from sentinel.runtime import SentinelRuntime
import sentinel.worker as api
from sentinel.worker import composition, scheduler as scheduler_module
from sentinel.worker import (
    DaemonState, HealthMonitor, OperationalDaemon, RestartPolicy,
    RuntimeScheduler, RuntimeState, RuntimeSupervisionBundle,
    RuntimeSupervisionConfig, RuntimeSupervisor, SentinelRuntimeWorker,
    WorkerHealthStatus, WorkerId, WorkerProtocol, WorkerRegistry, WorkerState,
    build_runtime_supervision,
)


@pytest.fixture
def config():
    return RuntimeSupervisionConfig(
        worker_id=WorkerId("sentinel.runtime"), worker_name="Sentinel runtime",
        worker_version="1", worker_description="Canonical runtime",
        daemon_cycle_interval=0.25, health_stale_after=30,
        restart_policy=RestartPolicy(2, 1, 4),
    )


@pytest.fixture
def runtime():
    # Construction only assembles objects. Never start the actual diagnostic
    # coordinator here: startup recovers persistent data and launches a thread.
    return SentinelRuntime()


def forbidden(*args, **kwargs):
    pytest.fail("unexpected startup, authority construction, or thread creation")


def test_valid_config(config):
    assert config.worker_id == WorkerId("sentinel.runtime")
    assert config.worker_name == "Sentinel runtime"
    assert config.worker_version == "1"
    assert config.worker_description == "Canonical runtime"
    assert config.daemon_cycle_interval == 0.25
    assert config.health_stale_after == 30
    assert config.restart_policy == RestartPolicy(2, 1, 4)
    assert replace(config, worker_description="").worker_description == ""


@pytest.mark.parametrize("field", ["daemon_cycle_interval", "health_stale_after"])
@pytest.mark.parametrize("value", [0, -1, True, None, "1", float("nan"),
                                   float("inf"), -float("inf")])
def test_invalid_timing(config, field, value):
    with pytest.raises(ValueError, match=field):
        replace(config, **{field: value})


@pytest.mark.parametrize("field", ["worker_name", "worker_version"])
@pytest.mark.parametrize("value", ["", " ", "\t\n", None, 1])
def test_invalid_metadata(config, field, value):
    with pytest.raises(ValueError, match=field):
        replace(config, **{field: value})


@pytest.mark.parametrize("field,value", [
    ("worker_id", "runtime"), ("restart_policy", None),
    ("worker_description", None),
])
def test_invalid_config_types(config, field, value):
    with pytest.raises(TypeError, match=field):
        replace(config, **{field: value})


def test_config_immutable(config):
    for field in fields(config):
        with pytest.raises(FrozenInstanceError):
            setattr(config, field.name, None)


def test_bundle_immutable(runtime, config):
    bundle = build_runtime_supervision(runtime, config)
    for field in fields(bundle):
        with pytest.raises(FrozenInstanceError):
            setattr(bundle, field.name, None)


@pytest.mark.parametrize("bad_runtime", [None, object(), "runtime"])
def test_factory_rejects_invalid_runtime_before_composition(config, monkeypatch, bad_runtime):
    monkeypatch.setattr(SentinelRuntimeWorker, "__init__", forbidden)
    with pytest.raises(TypeError, match="runtime must be SentinelRuntime"):
        build_runtime_supervision(bad_runtime, config)


def test_factory_rejects_invalid_config_before_composition(runtime, monkeypatch):
    monkeypatch.setattr(SentinelRuntimeWorker, "__init__", forbidden)
    with pytest.raises(TypeError, match="config must be RuntimeSupervisionConfig"):
        build_runtime_supervision(runtime, object())


def test_canonical_identities_and_no_composition_side_effects(runtime, config, monkeypatch):
    original = vars(runtime).copy()
    diagnostic_original = vars(runtime.diagnostic).copy()
    # Preserve every supplied authority, and forbid constructing another one.
    authority_types = {type(value) for value in original.values()
                       if type(value).__module__.startswith("sentinel.")}
    authority_types.update(type(value) for value in diagnostic_original.values()
                           if type(value).__module__.startswith("sentinel."))
    for authority_type in authority_types | {SentinelRuntime}:
        monkeypatch.setattr(authority_type, "__init__", forbidden)
    for cls, method in ((SentinelRuntime, "start"),
                        (SentinelRuntimeWorker, "start"),
                        (RuntimeSupervisor, "start"),
                        (OperationalDaemon, "run_forever"),
                        (Thread, "__init__"), (Thread, "start")):
        monkeypatch.setattr(cls, method, forbidden)
    registrations = []
    register = WorkerRegistry.register

    def record_registration(registry, worker, info):
        registrations.append((registry, worker, info))
        return register(registry, worker, info)

    monkeypatch.setattr(WorkerRegistry, "register", record_registration)
    bundle = build_runtime_supervision(runtime, config)
    scheduler = RuntimeScheduler(bundle.daemon)
    assert bundle.runtime is runtime
    assert bundle.runtime_worker.runtime is runtime
    assert bundle.runtime_worker.worker_id() is config.worker_id
    assert bundle.runtime_worker.worker_id() is bundle.runtime_worker.worker_id()
    assert bundle.worker_info.worker_id is bundle.runtime_worker.worker_id()
    assert bundle.worker_info.name == config.worker_name
    assert bundle.worker_info.version == config.worker_version
    assert bundle.worker_info.description == config.worker_description
    assert len(bundle.registry) == 1
    assert bundle.registry.workers() == (bundle.runtime_worker,)
    assert bundle.registry.get(config.worker_id) is bundle.runtime_worker
    assert bundle.registry.get_info(config.worker_id) is bundle.worker_info
    assert registrations == [(bundle.registry, bundle.runtime_worker, bundle.worker_info)]
    assert bundle.health_monitor._registry is bundle.registry
    assert bundle.health_monitor._stale_after == config.health_stale_after
    assert bundle.supervisor._registry is bundle.registry
    assert bundle.supervisor._health_monitor is bundle.health_monitor
    assert bundle.supervisor._restart_policy is config.restart_policy
    assert bundle.daemon._supervisor is bundle.supervisor
    assert bundle.daemon._config.cycle_interval == config.daemon_cycle_interval
    assert scheduler._daemon is bundle.daemon
    assert bundle.runtime_worker.state() is WorkerState.REGISTERED
    assert bundle.supervisor.state is RuntimeState.STOPPED
    assert scheduler.snapshot().state is DaemonState.STOPPED
    assert scheduler.snapshot().cycles == 0
    assert bundle.health_monitor.last_heartbeat(config.worker_id) is None
    assert isinstance(bundle.runtime_worker, WorkerProtocol)
    assert not runtime.running
    for name, value in original.items():
        assert getattr(runtime, name) is value
    for name, value in diagnostic_original.items():
        assert getattr(runtime.diagnostic, name) is value


@pytest.mark.parametrize("method", ["run_forever", "request_stop", "snapshot"])
def test_scheduler_delegates_once_without_supervising(runtime, config, monkeypatch, method):
    bundle = build_runtime_supervision(runtime, config)
    scheduler = RuntimeScheduler(bundle.daemon)
    snapshot = bundle.daemon.snapshot()
    delegate = Mock(return_value=snapshot if method == "snapshot" else None)
    monkeypatch.setattr(bundle.daemon, method, delegate)
    monkeypatch.setattr(bundle.supervisor, "supervise_once", forbidden)
    monkeypatch.setattr(bundle.supervisor, "recover", forbidden)
    result = getattr(scheduler, method)()
    delegate.assert_called_once_with()
    assert result is (snapshot if method == "snapshot" else None)


def test_scheduler_rejects_invalid_daemon():
    with pytest.raises(TypeError, match="daemon"):
        RuntimeScheduler(object())


def test_real_phase2_chain_lifecycle_and_heartbeat(config, monkeypatch):
    # Only the Phase 1 lifecycle boundary is doubled; no persisted recovery,
    # diagnostic worker, sensor polling, or production commands can run.
    runtime = Mock(spec=SentinelRuntime)
    bundle = build_runtime_supervision(runtime, config)
    scheduler = RuntimeScheduler(bundle.daemon)
    monkeypatch.setattr(Thread, "__init__", forbidden)
    monkeypatch.setattr(Thread, "start", forbidden)
    observations = []

    def wait(interval):
        assert interval == config.daemon_cycle_interval
        assert bundle.runtime_worker.state() is WorkerState.RUNNING
        assert bundle.supervisor.state is RuntimeState.RUNNING
        assert bundle.daemon.state is DaemonState.RUNNING
        runtime.start.assert_called_once_with()
        heartbeat = bundle.health_monitor.last_heartbeat(config.worker_id)
        observation = scheduler.snapshot().last_supervision
        assert heartbeat is observation.workers[0].last_heartbeat
        assert heartbeat.worker_id is config.worker_id
        assert heartbeat.healthy
        assert heartbeat.iteration == len(observations) + 1
        health = bundle.health_monitor.snapshot(config.worker_id, now=heartbeat.timestamp)
        assert health.status is WorkerHealthStatus.HEALTHY
        assert health.heartbeat is heartbeat
        observations.append(observation)
        if len(observations) == 2:
            scheduler.request_stop()
        return bundle.daemon._stop_event.is_set()

    monkeypatch.setattr(bundle.daemon._stop_event, "wait", wait)
    scheduler.run_forever()
    assert len(observations) == scheduler.snapshot().cycles == 2
    assert runtime.mock_calls == [call.start(), call.stop()]
    assert bundle.runtime_worker.state() is WorkerState.STOPPED
    assert bundle.supervisor.state is RuntimeState.STOPPED
    assert scheduler.snapshot().state is DaemonState.STOPPED
    assert isinstance(bundle.runtime_worker, WorkerProtocol)


def test_public_exports_and_architectural_boundaries():
    for name, value in {
        "RuntimeSupervisionConfig": RuntimeSupervisionConfig,
        "RuntimeSupervisionBundle": RuntimeSupervisionBundle,
        "build_runtime_supervision": build_runtime_supervision,
        "RuntimeScheduler": RuntimeScheduler,
    }.items():
        assert name in api.__all__
        assert getattr(api, name) is value
    for module in (composition, scheduler_module):
        source = inspect.getsource(module)
        for name in ("IncidentManager", "Investigation", "DiagnosisEvaluator",
                     "Commander", "CommanderIntent", "CommanderSemanticPolicy",
                     "RemediationPolicy", "FinalOutcomeMapper", "ExecutionBoundary",
                     "Verification", "environ", "getenv", "Thread"):
            assert name not in source
    source = inspect.getsource(scheduler_module)
    for name in ("supervise_once", "recover", "heartbeat", "WorkerRegistry",
                 "HealthMonitor", "RestartPolicy", "retry", "backoff", "sleep"):
        assert name not in source
    assert not any(isinstance(node, (ast.For, ast.While, ast.AsyncFor))
                   for node in ast.walk(ast.parse(source)))
