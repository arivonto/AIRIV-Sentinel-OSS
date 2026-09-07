"""Foreground lifecycle tests; signals and production startup are isolated."""

import ast
from dataclasses import FrozenInstanceError, fields
import importlib
import inspect
import os
import runpy
import signal
import sys
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from sentinel.runtime import SentinelRuntime
from sentinel.worker import (
    DaemonState, RestartPolicy, RuntimeScheduler, RuntimeState,
    RuntimeSupervisionConfig, WorkerId, WorkerState, build_runtime_supervision,
)
from sentinel.worker import entrypoint as ep


@pytest.fixture
def signals(monkeypatch):
    previous = {signal.SIGINT: object(), signal.SIGTERM: object()}
    current = previous.copy()
    changes = []

    def install(signum, handler):
        changes.append((signum, handler))
        old = current[signum]
        current[signum] = handler
        return old

    monkeypatch.setattr(signal, "getsignal", current.__getitem__)
    monkeypatch.setattr(signal, "signal", install)
    return SimpleNamespace(previous=previous, current=current, changes=changes)


@pytest.fixture
def wiring(monkeypatch, signals):
    runtime = Mock(spec=SentinelRuntime)
    constructor = Mock(return_value=runtime)
    bundle = SimpleNamespace(daemon=object())
    compose = Mock(return_value=bundle)
    scheduler = Mock(spec=RuntimeScheduler)
    schedule = Mock(return_value=scheduler)
    monkeypatch.setattr(ep, "SentinelRuntime", constructor)
    monkeypatch.setattr(ep, "build_runtime_supervision", compose)
    monkeypatch.setattr(ep, "RuntimeScheduler", schedule)
    return SimpleNamespace(runtime=runtime, constructor=constructor, bundle=bundle,
                           compose=compose, scheduler=scheduler, schedule=schedule)


def test_main_callable_and_canonical_runtime():
    assert callable(ep.main)
    runtime = ep.build_production_runtime()
    assert type(runtime) is SentinelRuntime
    assert not runtime.running


def test_explicit_existing_immutable_config():
    config = ep.build_production_config()
    assert type(config) is RuntimeSupervisionConfig
    assert config == RuntimeSupervisionConfig(
        WorkerId("sentinel.runtime"), "Sentinel runtime", "1", "Canonical runtime",
        1.0, 30.0, RestartPolicy(0, 0.0, 0.0),
    )
    assert ep.build_production_config() == config
    assert ep.build_production_config() is not config
    for field in fields(config):
        with pytest.raises(FrozenInstanceError):
            setattr(config, field.name, None)
    with pytest.raises(FrozenInstanceError):
        config.restart_policy.max_retries = 1
    with pytest.raises(FrozenInstanceError):
        config.worker_id.value = "other"
    assert {field.name for field in fields(config)} == {
        "worker_id", "worker_name", "worker_version", "worker_description",
        "daemon_cycle_interval", "health_stale_after", "restart_policy",
    }


def test_main_constructs_one_graph_and_runs_once(wiring, signals):
    assert ep.main([]) == 0
    wiring.constructor.assert_called_once_with()
    wiring.compose.assert_called_once_with(wiring.runtime, ep.build_production_config())
    assert wiring.compose.call_args.args[0] is wiring.runtime
    wiring.schedule.assert_called_once_with(wiring.bundle.daemon)
    assert wiring.scheduler.mock_calls == [call.run_forever()]
    assert wiring.runtime.mock_calls == []
    assert signals.current == signals.previous


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_only_requests_stop_and_restores(wiring, signals, signum):
    def run():
        assert set(signals.current) == {signal.SIGINT, signal.SIGTERM}
        assert all(callable(handler) for handler in signals.current.values())
        wiring.scheduler.reset_mock()
        signals.current[signum](signum, None)
        assert wiring.scheduler.mock_calls == [call.request_stop()]
        assert wiring.runtime.mock_calls == []

    wiring.scheduler.run_forever.side_effect = run
    assert ep.main() == 0
    assert [s for s, _ in signals.changes] == [
        signal.SIGINT, signal.SIGTERM, signal.SIGTERM, signal.SIGINT,
    ]
    assert signals.current == signals.previous


@pytest.mark.parametrize("stage", ["constructor", "compose", "schedule"])
def test_startup_failure_returns_one(wiring, signals, stage):
    getattr(wiring, stage).side_effect = RuntimeError(stage)
    assert ep.main() == 1
    wiring.scheduler.run_forever.assert_not_called()
    assert signals.changes == []


def test_scheduler_failure_restores_handlers(wiring, signals):
    wiring.scheduler.run_forever.side_effect = RuntimeError("scheduler failed")
    assert ep.main() == 1
    assert wiring.scheduler.mock_calls == [call.run_forever()]
    assert signals.current == signals.previous


def test_escaping_interrupt_requests_stop_without_claiming_clean_shutdown(wiring, signals):
    wiring.scheduler.run_forever.side_effect = KeyboardInterrupt()
    assert ep.main() == 1
    assert wiring.scheduler.mock_calls == [call.run_forever(), call.request_stop()]
    assert signals.current == signals.previous


def test_construction_interrupt_returns_one(wiring, signals):
    wiring.constructor.side_effect = KeyboardInterrupt()
    assert ep.main() == 1
    assert signals.changes == []


def test_constructor_has_no_signal_effects(signals):
    ep.SentinelProcess(Mock(spec=RuntimeScheduler))
    assert signals.changes == []


def test_partial_installation_restores_previous_handlers(monkeypatch, signals):
    install = signal.signal

    def fail_second(signum, handler):
        if signum == signal.SIGTERM and callable(handler):
            raise ValueError("installation failed")
        return install(signum, handler)

    monkeypatch.setattr(signal, "signal", fail_second)
    scheduler = Mock(spec=RuntimeScheduler)
    assert ep.SentinelProcess(scheduler).run() == 1
    scheduler.run_forever.assert_not_called()
    assert signals.current == signals.previous


def test_restoration_failure_still_attempts_other_handler(monkeypatch, signals):
    install = signal.signal

    def fail_restore(signum, handler):
        if signum == signal.SIGTERM and handler is signals.previous[signum]:
            raise ValueError("restoration failed")
        return install(signum, handler)

    monkeypatch.setattr(signal, "signal", fail_restore)
    assert ep.SentinelProcess(Mock(spec=RuntimeScheduler)).run() == 1
    assert signals.current[signal.SIGINT] is signals.previous[signal.SIGINT]


@pytest.mark.parametrize("ending", ["sigint", "sigterm", "interrupt", "failure", "shutdown_failure"])
def test_real_chain_identity_and_daemon_owned_shutdown(monkeypatch, signals, ending):
    runtime = ep.build_production_runtime()
    original = vars(runtime).copy()
    # Replace only lifecycle operations, preventing persistent recovery and the
    # existing Phase 1 diagnostic thread from starting in this test.
    lifecycle = Mock()
    monkeypatch.setattr(runtime, "start", lifecycle.start)
    monkeypatch.setattr(runtime, "stop", lifecycle.stop)
    monkeypatch.setattr(ep, "build_production_runtime", Mock(return_value=runtime))
    bundles = []

    def compose(supplied, config):
        bundle = build_runtime_supervision(supplied, config)
        bundles.append(bundle)
        assert bundle.runtime is runtime
        assert bundle.runtime_worker.runtime is runtime
        assert bundle.registry.get(config.worker_id) is bundle.runtime_worker
        assert bundle.worker_info.worker_id is bundle.runtime_worker.worker_id()
        assert bundle.health_monitor._registry is bundle.registry
        assert bundle.supervisor._registry is bundle.registry
        assert bundle.supervisor._health_monitor is bundle.health_monitor
        assert bundle.daemon._supervisor is bundle.supervisor
        for name, value in original.items():
            assert getattr(runtime, name) is value

        def wait(interval):
            assert bundle.runtime_worker.state() is WorkerState.RUNNING
            if ending == "interrupt":
                raise KeyboardInterrupt()
            if ending == "failure":
                raise RuntimeError("infrastructure failed")
            signum = signal.SIGINT if ending == "sigint" else signal.SIGTERM
            signals.current[signum](signum, None)
            return bundle.daemon._stop_event.is_set()

        monkeypatch.setattr(bundle.daemon._stop_event, "wait", wait)
        return bundle

    def forbidden(*args, **kwargs):
        pytest.fail("process created a thread/process or ran business operations")

    monkeypatch.setattr(Thread, "__init__", forbidden)
    monkeypatch.setattr(Thread, "start", forbidden)
    for name in ("fork", "forkpty", "setsid"):
        monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(runtime, "run_once", forbidden)
    monkeypatch.setattr(runtime, "remediate", forbidden)
    monkeypatch.setattr(ep, "build_runtime_supervision", compose)
    if ending == "shutdown_failure":
        lifecycle.stop.side_effect = RuntimeError("shutdown failed")
    assert ep.main() == (1 if ending in {"failure", "shutdown_failure"} else 0)
    assert len(bundles) == 1
    assert lifecycle.mock_calls == [call.start(), call.stop()]
    if ending not in {"failure", "shutdown_failure"}:
        assert bundles[0].daemon.state is DaemonState.STOPPED
        assert bundles[0].supervisor.state is RuntimeState.STOPPED
        assert bundles[0].runtime_worker.state() is WorkerState.STOPPED
    assert signals.current == signals.previous


def test_main_module_import_is_passive_and_execution_delegates(monkeypatch):
    main = Mock(return_value=0)
    monkeypatch.setattr(ep, "main", main)
    module = importlib.import_module("sentinel.__main__")
    importlib.reload(module)
    main.assert_not_called()
    monkeypatch.delitem(sys.modules, "sentinel.__main__")
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("sentinel.__main__", run_name="__main__")
    assert caught.value.code == 0
    main.assert_called_once_with()


def test_process_boundary_has_no_direct_business_or_worker_operations():
    source = inspect.getsource(ep)
    tree = ast.parse(source)
    for name in (
        "IncidentManager", "Investigation", "DiagnosisEvaluator", "Commander",
        "CommanderIntent", "CommanderSemanticPolicy", "RemediationPolicy",
        "FinalOutcomeMapper", "ExecutionBoundary", "Verification",
        "supervise_once", "recover", "heartbeat", "Thread", "multiprocessing",
        "fork", "setsid", "daemonize", "subprocess",
    ):
        assert name not in source
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"start", "stop", "run_once", "remediate"}
    assert not any(isinstance(node, (ast.While, ast.AsyncFor)) for node in ast.walk(tree))
