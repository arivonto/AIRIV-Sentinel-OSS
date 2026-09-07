"""Repository-only D8.4 tests; all effects use the existing fake executor."""
import importlib.util
import multiprocessing
import os
from pathlib import Path

import pytest

from sentinel.systemd_production_runtime_guard import (
    SystemdProductionAttemptLedger as Ledger,
    SystemdProductionAttemptRecord as Record,
    SystemdProductionEffectLease as Lease,
)
from sentinel.remediation_policy import RemediationPolicy

spec = importlib.util.spec_from_file_location(
    '_d84_helpers', 'tests/test_systemd_production_commander_integration_v1.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def record(timestamp=1000):
    return Record.from_plan(helpers.d82.make_plan(), timestamp)


def test_empty_and_durable():
    ledger = Ledger()
    assert ledger.root.is_absolute()
    assert ledger.records() == ()
    ledger.append(record())
    assert Ledger().records() == (record(),)
    assert Ledger().attempts() == (record().to_fact(),)
    assert ledger.root.stat().st_mode & 0o777 == 0o700
    assert (ledger.root / record().filename).stat().st_mode & 0o777 == 0o600


def test_duplicate_never_overwrites():
    ledger = Ledger()
    ledger.append(record())
    with pytest.raises(FileExistsError):
        ledger.append(record(2000))
    assert ledger.records() == (record(),)


@pytest.mark.parametrize('payload', ['{', '{}', '{"timestamp":NaN}'])
def test_malformed_fails_closed(payload):
    ledger = Ledger()
    ledger.append(record())
    (ledger.root / record().filename).write_text(payload)
    with pytest.raises(ValueError, match='malformed'):
        Ledger().records()
    with pytest.raises(ValueError):
        ledger.append(record(2000))


@pytest.mark.parametrize('kind', ['root_link', 'ancestor_link', 'writable', 'file_link', 'lock_link'])
def test_unsafe_state(tmp_path, kind):
    root = tmp_path / 'state'
    if kind in ('root_link', 'ancestor_link'):
        target = tmp_path / 'target'
        target.mkdir(mode=0o700)
        root.symlink_to(target, target_is_directory=True)
        if kind == 'ancestor_link':
            root = root / 'nested'
    else:
        root.mkdir(mode=0o700)
        if kind == 'writable':
            root.chmod(0o777)
        else:
            target = tmp_path / 'target'
            target.write_text('x')
            (root / ('effect.lock' if kind == 'lock_link' else 'x.json')).symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        if kind == 'lock_link':
            Lease(root).acquire()
        else:
            Ledger(root).records()


def test_independent_leases_and_existing_lock_file():
    first, second = Lease(), Lease()
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.close()
    assert second.acquire()
    second.close()
    second.close()


def child_lease(root, pipe):
    lease = Lease(root)
    pipe.send(lease.acquire())
    pipe.recv()
    os._exit(0)  # No Python cleanup: kernel must release the lease.


def test_process_exclusion_and_exit_release(tmp_path):
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=child_lease, args=(str(tmp_path / 'state'), child))
    process.start()
    try:
        assert parent.poll(10)
        assert parent.recv()
        contender = Lease(tmp_path / 'state')
        assert not contender.acquire()
        parent.send('exit')
        process.join(10)
        assert process.exitcode == 0
        assert contender.acquire()
        contender.close()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(10)
        parent.close()
        child.close()


@pytest.fixture
def case(tmp_path, monkeypatch):
    return helpers.setup_case(tmp_path, monkeypatch)


def run(case, now=1000):
    return helpers.execute(case[3], case[4], case[5], production_now=now)


def allow(case, **kwargs):
    helpers.configure_target(case[0], case[4], **kwargs)


def assert_released():
    lease = Lease()
    assert lease.acquire()
    lease.close()


def test_default_empty_no_attempt_or_effect(case):
    assert RemediationPolicy().list_systemd_production_targets() == ()
    assert not run(case).authorization.authorized
    assert Ledger().records() == ()
    assert case[2].calls == []
    assert_released()


def test_attempt_before_executor_and_lease_through_verification(case, monkeypatch):
    allow(case)
    original = case[2].execute_argv
    calls = []

    def checked(*args, **kwargs):
        assert Ledger().records() == (record(),)
        assert not Lease().acquire()
        calls.append('execute')
        return original(*args, **kwargs)

    monkeypatch.setattr(case[2], 'execute_argv', checked)
    original_verify = case[3].verifier.verify

    def verify(**kwargs):
        assert not Lease().acquire()
        calls.append('verify')
        return original_verify(**kwargs)

    monkeypatch.setattr(case[3].verifier, 'verify', verify)
    assert run(case).recovered
    assert calls == ['execute', 'verify']
    assert_released()


@pytest.mark.parametrize('now,reason', [(1001, 'cooldown_active'), (1400, 'retry_budget_exhausted')])
def test_durable_attempt_limits_second_effect(case, now, reason):
    allow(case)
    assert run(case).recovered
    result = run(case, now)
    assert not result.authorization.authorized
    assert reason in result.authorization.reason
    assert len(case[2].calls) == 1
    assert len(Ledger().records()) == 1


def test_concurrent_canonical_deny_without_attempt(case, monkeypatch):
    allow(case)
    original = case[0].policy.evaluate_systemd_production_bound
    calls = []

    def counted(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(case[0].policy, 'evaluate_systemd_production_bound', counted)
    lease = Lease()
    assert lease.acquire()
    try:
        result = run(case)
        assert result.authorization.reason.endswith('production_effect_already_active')
        assert len(calls) == 1
        assert calls[0]['active_production_effects'] == 1
        assert Ledger().records() == ()
        assert case[2].calls == []
    finally:
        lease.close()


@pytest.mark.parametrize('failure', ['persistence', 'executor', 'observation'])
def test_failure_releases_lease(case, monkeypatch, failure):
    allow(case)

    def fail(*args, **kwargs):
        raise RuntimeError('injected failure')

    if failure == 'persistence':
        monkeypatch.setattr(Ledger, 'append', fail)
    elif failure == 'executor':
        monkeypatch.setattr(case[3].execution_adapter, 'execute', fail)
    else:
        case = (*case[:5], fail)
    with pytest.raises(RuntimeError, match='injected failure'):
        run(case)
    assert_released()
    if failure == 'persistence':
        assert case[2].calls == []
        assert Ledger().records() == ()
    else:
        assert len(Ledger().records()) == 1


def test_failed_executor_result_releases_lease(case):
    allow(case)
    case[2].success = False
    assert not run(case).execution_succeeded
    assert len(Ledger().records()) == 1
    assert_released()


def test_corrupt_state_prevents_permit(case):
    allow(case)
    ledger = Ledger()
    ledger.append(record())
    (ledger.root / record().filename).write_text('')
    with pytest.raises(ValueError):
        run(case)
    assert case[2].calls == []
    assert_released()


def test_legacy_does_not_open_production_state(case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('legacy accessed production state')
    monkeypatch.setattr(Lease, 'acquire', forbidden)
    assert helpers.execute(case[3], case[4], case[5]).recovered


def test_fsync_failure_prevents_adapter(case, monkeypatch):
    import sentinel.systemd_production_runtime_guard as module
    import stat
    allow(case)
    original = module.os.fsync

    def fail_file(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('durability failed')
        return original(fd)

    monkeypatch.setattr(module.os, 'fsync', fail_file)
    with pytest.raises(OSError, match='durability failed'):
        run(case)
    assert case[2].calls == []
    assert len(Ledger().records()) == 1
    assert_released()


def test_duplicate_after_window_still_prevents_adapter(case):
    allow(case)
    assert run(case).recovered
    with pytest.raises(FileExistsError):
        run(case, 3000)
    assert len(case[2].calls) == 1
    assert len(Ledger().records()) == 1
    assert_released()


def test_record_binding_tamper_rejected():
    import dataclasses
    import json
    ledger = Ledger()
    ledger.append(record())
    changed = dataclasses.replace(record(), execution_id='different')
    (ledger.root / record().filename).write_text(json.dumps(
        dataclasses.asdict(changed), sort_keys=True, separators=(',', ':')))
    with pytest.raises(ValueError, match='malformed'):
        ledger.records()



def test_default_root_uses_secure_private_namespace(monkeypatch):
    from pathlib import Path

    from sentinel.systemd_production_runtime_guard import (
        SystemdProductionAttemptLedger,
    )

    monkeypatch.delenv(
        "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR",
        raising=False,
    )

    ledger = SystemdProductionAttemptLedger()

    expected = (
        Path.home()
        / ".local"
        / "state"
        / "airiv-sentinel-secure"
        / "systemd_production_runtime"
    ).resolve()

    assert ledger.root == expected

    assert (
        "airiv-sentinel-secure"
        in ledger.root.parts
    )

    assert (
        ledger.root
        != (
            Path.cwd()
            / "var"
            / "systemd_production_runtime"
        ).resolve()
    )
