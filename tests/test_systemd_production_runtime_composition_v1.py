"""D8.5 composition: real authorities and guard, isolated fake effects only."""
import inspect
import os
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from sentinel.commander import CommanderOrchestrator
from sentinel.remediation_policy import RemediationPolicy
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_commander_integration import SystemdCommanderIntegration
from sentinel.systemd_production_runtime_guard import (
    SystemdProductionAttemptLedger as Ledger,
    SystemdProductionAttemptRecord as Record,
    SystemdProductionEffectLease as Lease,
)
from sentinel.worker import entrypoint, observability
from sentinel.worker.composition import build_production_supervision
from test_systemd_production_commander_integration_v1 import (
    configure_target, d82, execute, legacy,
)


@pytest.fixture(autouse=True)
def isolated_io(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setenv('AIRIV_SENTINEL_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('AIRIV_SENTINEL_DIAGNOSTIC_DIR', str(tmp_path / 'diagnostic'))
    monkeypatch.setattr(observability, 'REPOSITORY_ROOT', tmp_path)
    monkeypatch.setattr(subprocess, 'run', Mock(side_effect=AssertionError('host I/O forbidden')))


def assert_inert(runtime):
    assert runtime.policy.list_systemd_production_targets() == ()
    assert not hasattr(runtime.policy, '_systemd_production_target_policy')
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()
    assert not Path(os.environ['AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR']).exists()
    journal = runtime.commander.remediation_orchestrator.identity_boundary.journal
    assert list(journal.root.iterdir()) == []


def test_fresh_composition_shares_exact_authorities_once(monkeypatch):
    counts = []
    for cls in (CommanderOrchestrator, RemediationPolicy):
        original = cls.__init__
        def counted(self, *args, _original=original, _cls=cls, **kwargs):
            counts.append(_cls)
            _original(self, *args, **kwargs)
        monkeypatch.setattr(cls, '__init__', counted)
    runtime = SentinelRuntime()
    integration = runtime.systemd_production_integration
    orch = runtime.commander.remediation_orchestrator
    assert type(integration) is SystemdCommanderIntegration
    assert integration.commander is runtime.commander
    assert integration.policy is runtime.policy is orch.policy
    assert integration.execution_adapter.identity_boundary is orch.identity_boundary
    assert orch.identity_boundary.gate is orch.gate
    assert orch.gate.executor is runtime.execution
    assert counts.count(CommanderOrchestrator) == 1
    assert counts.count(RemediationPolicy) == 1
    assert_inert(runtime)


def test_composition_never_constructs_production_storage_or_enters_guard(monkeypatch):
    import sentinel.systemd_commander_integration as module
    forbidden = Mock(side_effect=AssertionError('composition opened production state'))
    monkeypatch.setattr(Ledger, '__init__', forbidden)
    monkeypatch.setattr(Lease, '__init__', forbidden)
    monkeypatch.setattr(module, 'production_runtime_guard', forbidden)
    runtime = entrypoint.build_production_runtime()
    assert_inert(runtime)
    forbidden.assert_not_called()


@pytest.fixture
def case():
    runtime = SentinelRuntime()
    orch = runtime.commander.remediation_orchestrator
    fake = legacy.FakeArgvExecutor()
    orch.gate.executor = fake
    plan = d82.make_plan(unit='d85-synthetic-worker.service')
    legacy.activate_exact_plan(runtime, plan)
    legacy.configure_fake(orch, fake, plan)
    provider = legacy.SnapshotProvider(legacy.successful_after(plan))
    return runtime, fake, plan, provider


def run(case, now=1000):
    runtime, _, plan, provider = case
    return execute(runtime.systemd_production_integration, plan, provider,
                   production_now=now)


def assert_released():
    lease = Lease()
    try:
        assert lease.acquire()
    finally:
        lease.close()


def test_empty_allowlist_denies_even_exact_bound_action(case):
    runtime, fake, plan, provider = case
    result = run(case)
    assert result.authorization.reason.endswith('target_not_allowlisted')
    assert not result.authorization.authorized
    assert result.execution is result.identity_record is result.verification is None
    assert fake.calls == [] and provider.calls == 0
    assert Ledger().records() == ()
    assert runtime.commander.remediation_orchestrator.identity_boundary.journal.get(plan.effect.execution_id) is None
    assert_released()


def test_guard_durable_before_effect_lease_through_verification_and_single_authorities(case, monkeypatch):
    runtime, fake, plan, provider = case
    configure_target(runtime, plan)
    integration = runtime.systemd_production_integration
    journal = integration.execution_adapter.identity_boundary.journal
    calls = []
    for owner, method in ((runtime.policy, 'evaluate_systemd_production_bound'),
                          (runtime.policy, 'evaluate_bound'), (runtime.policy, 'evaluate'),
                          (integration.execution_adapter, 'execute'),
                          (journal, 'claim_live_run_permit'),
                          (fake, 'execute_argv'), (integration.verifier, 'verify')):
        original = getattr(owner, method)
        def counted(*args, _original=original, _method=method, **kwargs):
            calls.append(_method)
            if _method in ('execute_argv', 'verify'):
                assert Ledger().records() == (Record.from_plan(plan, 1000),)
                contender = Lease()
                try:
                    assert not contender.acquire()
                finally:
                    contender.close()
            return _original(*args, **kwargs)
        monkeypatch.setattr(owner, method, counted)
    result = run(case)
    assert result.recovered
    assert calls == ['evaluate_systemd_production_bound', 'evaluate_bound', 'evaluate',
                     'execute', 'claim_live_run_permit', 'execute_argv', 'verify']
    assert journal.get(plan.effect.execution_id) == result.identity_record
    assert provider.calls == 1
    assert_released()


@pytest.mark.parametrize('now,reason', [(1001, 'cooldown_active'), (1400, 'retry_budget_exhausted')])
def test_fresh_runtime_observes_durable_attempt(case, now, reason):
    runtime, fake, plan, provider = case
    configure_target(runtime, plan)
    assert run(case).recovered
    fresh = SentinelRuntime()
    legacy.activate_exact_plan(fresh, plan)
    configure_target(fresh, plan)
    fresh.commander.remediation_orchestrator.gate.executor = fake
    result = run((fresh, fake, plan, provider), now)
    assert not result.authorization.authorized
    assert result.authorization.reason.endswith(reason)
    assert len(fake.calls) == provider.calls == 1
    assert Ledger().records() == (Record.from_plan(plan, 1000),)
    assert_released()


def test_held_lease_reaches_canonical_denial(case):
    runtime, fake, plan, provider = case
    configure_target(runtime, plan)
    lease = Lease()
    assert lease.acquire()
    try:
        result = run(case)
        assert result.authorization.reason.endswith('production_effect_already_active')
        assert not result.authorization.authorized
        assert Ledger().records() == ()
        assert fake.calls == [] and provider.calls == 0
    finally:
        lease.close()
    assert_released()


def test_legacy_integration_still_bypasses_production_storage(case):
    runtime, fake, plan, provider = case
    result = execute(SystemdCommanderIntegration(runtime.commander), plan, provider)
    assert result.recovered
    assert len(fake.calls) == provider.calls == 1
    assert not Path(os.environ['AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR']).exists()


def test_canary_retains_separate_integration_and_no_production_policy(monkeypatch):
    runtime = SentinelRuntime()
    canary = runtime.canary_live_execution
    assert canary.integration is not runtime.systemd_production_integration
    assert canary.integration.commander is runtime.commander
    assert canary.integration.policy is runtime.policy
    forbidden = Mock(side_effect=AssertionError('canary entered production path'))
    monkeypatch.setattr(runtime.policy, 'evaluate_systemd_production_bound', forbidden)
    monkeypatch.setattr(runtime.systemd_production_integration, 'execute_verified', forbidden)
    assert canary.poll_once() is None
    assert_inert(runtime)


def test_production_daemon_start_cycle_stop_is_inert(monkeypatch):
    runtime = entrypoint.build_production_runtime()
    completed = Event()
    def observe():
        completed.set()
        return []
    monkeypatch.setattr(runtime.sensor_adapter, 'process_tick', observe)
    forbidden = Mock(side_effect=AssertionError('automatic production remediation'))
    monkeypatch.setattr(runtime.systemd_production_integration, 'execute_verified', forbidden)
    from dataclasses import replace
    config = replace(entrypoint.build_production_config(), daemon_cycle_interval=0.01)
    bundle = build_production_supervision(runtime, config)
    def wait(interval):
        assert completed.wait(3)
        bundle.daemon.request_stop()
        return True
    monkeypatch.setattr(bundle.daemon._stop_event, 'wait', wait)
    bundle.daemon.run_forever()
    assert not runtime.running
    assert not bundle.capability_worker._thread.is_alive()
    forbidden.assert_not_called()
    assert_inert(runtime)


def test_runtime_composition_adds_no_privilege_or_dispatch_surface():
    source = inspect.getsource(SentinelRuntime)
    assert source.count('CommanderOrchestrator(') == 1
    assert source.count('RemediationPolicy(') == 1
    assert source.count('SystemdCommanderIntegration(') == 1
    assert 'systemd_production_integration' not in inspect.getsource(SentinelRuntime.run_once)
    for token in ('subprocess', 'sudo', 'pkexec', 'systemctl', 'systemd-run',
                  'evaluate_systemd_production_bound(', '.execute_verified('):
        assert token not in source
