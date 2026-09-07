"""Projection tests use only fake execution and snapshots from the canary harness."""
import inspect
import json
import os

import pytest

from test_systemd_canary_live_execution_v1 import setup, deliver, empty, payload
import sentinel.systemd_canary_live_execution as live
import sentinel.systemd_canary_live_observability as projection


def read(surface):
    return json.loads(surface.state_path.read_text())


def test_daemon_idle_and_current_identity(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    runtime.canary_live_execution = surface
    runtime.running = True
    monkeypatch.setattr(runtime.sensor_adapter, 'process_tick', lambda: [])
    monkeypatch.setattr(runtime.diagnostic, 'submit', lambda _: None)
    assert runtime.run_once() == []
    record = read(surface)
    assert record['phase'] == 'IDLE'
    assert record['process'] == projection.process_identity()
    assert record['process']['pid'] == os.getpid()
    assert record['inbox_pending'] is False
    assert record['active_request_id'] is None
    assert record['activation_empty'] is True
    assert record['cleanup_uncertain'] is False
    assert projection.valid_idle_projection(record, expected_process=projection.process_identity(), now=1050)
    assert calls == fake.calls == []
    empty(runtime)


@pytest.mark.parametrize('value', [False, True, None, 0, 1, 'false', 'true', [], {}, 0.0])
def test_idle_validator_cleanup_uncertain(setup, value):
    surface = setup[3]
    surface.cycle()
    record = read(surface)
    expected_process = projection.process_identity()
    assert projection.valid_idle_projection(record, expected_process=expected_process, now=1050)
    record['cleanup_uncertain'] = value
    assert record['activation_empty'] is True
    assert projection.valid_idle_projection(record, expected_process=expected_process, now=1050) is (value is False)


@pytest.mark.parametrize('field', ['cleanup_uncertain', 'activation_empty'])
def test_idle_validator_missing_safety_evidence(setup, field):
    surface = setup[3]
    surface.cycle()
    record = read(surface)
    del record[field]
    assert not projection.valid_idle_projection(record, expected_process=projection.process_identity(), now=1050)


@pytest.mark.parametrize('field', [
    'activation_empty', 'policy_activation_empty', 'catalog_activation_empty', 'bound_activation_empty',
])
def test_idle_validator_nonempty_activation(setup, field):
    surface = setup[3]
    surface.cycle()
    record = read(surface)
    record[field] = False
    assert record['cleanup_uncertain'] is False
    assert not projection.valid_idle_projection(record, expected_process=projection.process_identity(), now=1050)


@pytest.mark.parametrize('surface_name', ['policy', 'catalog', 'bound', 'trigger', 'unknown'])
def test_activation_truth(setup, surface_name, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    if surface_name == 'policy':
        runtime.policy.allowed_actions.add('RESTART')
    elif surface_name == 'catalog':
        surface.catalog.register(live.RemediationActionEntry(action='RESTART', command='fake', rationale='test'))
    elif surface_name == 'bound':
        runtime.policy.allowed_actions.add(plan.effect.action)
        runtime.policy.configure_bound_effect(plan.effect)
        runtime.policy.allowed_actions.clear()
    elif surface_name == 'trigger':
        surface.catalog._trigger_map['test'] = 'RESTART'
    else:
        monkeypatch.setattr(runtime.policy, 'list_bound_runs', lambda: (_ for _ in ()).throw(ValueError()))
    surface.cycle()
    assert read(surface)['activation_empty'] is False
    assert fake.calls == []


@pytest.mark.parametrize('change', ['old_pid', 'old_start', 'old_boot', 'expired', 'future', 'malformed', 'bool_version', 'pending', 'active', 'activation', 'phase'])
def test_invalid_proof(setup, change):
    surface = setup[3]
    surface.cycle()
    record = read(surface)
    if change == 'old_pid': record['process']['pid'] += 1000000
    elif change == 'old_start': record['process']['start_ticks'] = '0'
    elif change == 'old_boot': record['process']['boot_id'] = 'old'
    elif change == 'expired': record['timestamp'] = 1000
    elif change == 'future': record['timestamp'] = 1100
    elif change == 'malformed': record = {}
    elif change == 'bool_version': record['schema_version'] = True
    elif change == 'pending': record['inbox_pending'] = True
    elif change == 'active': record['active_request_id'] = 'request'
    elif change == 'activation': record['bound_activation_empty'] = False
    else: record['phase'] = 'PROCESSING'
    assert not projection.valid_idle_projection(record, expected_process=projection.process_identity(), now=1050)


@pytest.mark.parametrize('outcome', ['success', 'verification_failure', 'execution_failure', 'denial', 'exception'])
def test_terminal_evidence_and_single_call(setup, monkeypatch, outcome):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    if outcome == 'verification_failure': snaps[1] = snaps[0]
    if outcome == 'execution_failure': fake.success = False
    if outcome == 'denial':
        original_policy = runtime.policy.evaluate_bound
        def deny(**kwargs):
            runtime.policy.allowed_actions.clear()
            return original_policy(**kwargs)
        monkeypatch.setattr(runtime.policy, 'evaluate_bound', deny)
    original = surface.integration.execute_verified
    returned = []
    invoked = []
    def execute(**kwargs):
        invoked.append(1)
        state = read(surface)
        assert state['phase'] == 'PROCESSING'
        assert state['active_request_id'] == 'request-1'
        assert state['active_approval_id'] == 'approval-1'
        assert state['activation_empty'] is False
        if outcome == 'exception': raise RuntimeError('sensitive exception text')
        result = original(**kwargs)
        returned.append(result)
        return result
    monkeypatch.setattr(surface.integration, 'execute_verified', execute)
    deliver(surface)
    result = surface.cycle()
    assert len(invoked) == 1
    assert len(fake.calls) <= 1
    if returned: assert result is returned[0] is surface.last_result
    evidence = json.loads(surface.evidence_path.read_text())
    assert evidence['pre_invocation_id'] == 'a' * 32
    assert evidence['pre_target_fingerprint'] == plan.before.identity.fingerprint
    assert evidence['permit_id'] == plan.effect.permit_id
    assert evidence['execution_id'] == plan.effect.execution_id
    assert evidence['argv'] == list(live.ARGV)
    assert evidence['cleanup_state']['activation_empty'] is True
    assert evidence['terminal_outcome'] == ('TERMINAL_SUCCESS' if outcome == 'success' else 'TERMINAL_FAILURE')
    if outcome in ('success', 'verification_failure'):
        assert evidence['post_invocation_id'] == snaps[1].invocation_id
        assert evidence['verification_success'] is (outcome == 'success')
        assert evidence['verification']['reason'] == result.verification.reason
    if outcome == 'execution_failure':
        assert evidence['execution_success'] is False
        assert evidence['execution_exit_code'] == 1
    if outcome == 'denial': assert evidence['policy_result']['decision'] == 'DENY'
    assert 'sensitive exception text' not in surface.evidence_path.read_text()
    assert read(surface)['activation_empty'] is True
    assert read(surface)['cleanup_uncertain'] is False
    assert surface._cleanup_uncertain is False
    empty(runtime)
    surface.cycle()
    assert read(surface)['phase'] == 'IDLE'
    assert read(surface)['last_terminal_request_id'] == 'request-1'
    assert len(invoked) == 1


def test_runtime_retains_exact_result(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    runtime.canary_live_execution = surface
    runtime.running = True
    monkeypatch.setattr(runtime.sensor_adapter, 'process_tick', lambda: [])
    monkeypatch.setattr(runtime.diagnostic, 'submit', lambda _: None)
    deliver(surface)
    runtime.run_once()
    assert runtime.last_canary_live_result is surface.last_result
    assert runtime.last_canary_live_result.recovered
    runtime.run_once()
    assert runtime.last_canary_live_result is surface.last_result
    assert len(fake.calls) == 1


def test_cleanup_uncertainty_latches(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    close = live.TemporaryLiveRemediationActivationLease.close
    def uncertain(self):
        close(self)
        raise RuntimeError('cleanup unproven')
    monkeypatch.setattr(live.TemporaryLiveRemediationActivationLease, 'close', uncertain)
    deliver(surface)
    surface.cycle()
    empty(runtime)
    assert read(surface)['activation_empty'] is False
    assert json.loads(surface.evidence_path.read_text())['cleanup_state']['activation_empty'] is False
    surface.cycle()
    assert read(surface)['activation_empty'] is False


@pytest.mark.parametrize('failure', ['raises', 'unproven'])
def test_latched_cleanup_survives_later_successful_requests(setup, monkeypatch, failure):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    empty(runtime)
    surface.cycle()
    assert read(surface)['activation_empty'] is True
    assert surface._cleanup_uncertain is False
    close = live.TemporaryLiveRemediationActivationLease.close
    closed = []
    invoked = []
    execute = surface.integration.execute_verified

    def counted_execute(**kwargs):
        invoked.append(kwargs['plan'].effect.execution_id)
        return execute(**kwargs)

    def cleanup(self):
        result = close(self)
        closed.append(result)
        if len(closed) == 1:
            if failure == 'raises':
                raise RuntimeError('cleanup unproven')
            return False
        return result

    monkeypatch.setattr(surface.integration, 'execute_verified', counted_execute)
    monkeypatch.setattr(live.TemporaryLiveRemediationActivationLease, 'close', cleanup)
    for number in range(1, 4):
        data = payload()
        data.update(request_id=f'request-{number}', approval_id=f'approval-{number}')
        request_plan = live.CanaryLiveRequest.parse(json.dumps(data), 1050).build_plan(snaps[0])
        fake.expected_command = orch.identity_boundary._bound_command(request_plan.effect)
        snapshots = iter(snaps)
        surface.snapshot_provider = lambda: next(snapshots)
        deliver(surface, data)
        result = surface.cycle()
        assert result.recovered
        assert len(invoked) == len(fake.calls) == len(closed) == number
        assert closed == [True] * number
        empty(runtime)
        assert surface._cleanup_uncertain is True
        state = read(surface)
        evidence = json.loads(surface.evidence_path.read_text())
        for facts in (state, evidence['cleanup_state']):
            assert facts['cleanup_uncertain'] is True
            assert facts['activation_empty'] is False
            assert all(facts[key] is True for key in (
                'policy_activation_empty', 'catalog_activation_empty', 'bound_activation_empty'))
        assert evidence['terminal_outcome'] == 'TERMINAL_FAILURE'

    assert len(set(invoked)) == 3
    assert surface.cycle() is None
    state = read(surface)
    assert state['phase'] == 'IDLE'
    assert state['cleanup_uncertain'] is True
    assert state['activation_empty'] is False
    assert surface._cleanup_uncertain is True
    assert not projection.valid_idle_projection(state, expected_process=projection.process_identity(), now=1050)
    assert len(invoked) == len(fake.calls) == len(closed) == 3


def test_old_files_are_never_inputs(setup):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    surface.root.mkdir(mode=0o700)
    surface.state_path.write_text('{malformed old state')
    surface.evidence_path.write_text('{"request_id":"old", "approval_id":"old"}')
    surface.cycle()
    assert fake.calls == calls == []
    assert read(surface)['phase'] == 'IDLE'
    assert surface.last_result is None


def test_replay_evidence(setup):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    deliver(surface)
    surface.cycle()
    surface.snapshot_provider = lambda: snaps[0]
    deliver(surface)
    result = surface.cycle()
    assert json.loads(surface.evidence_path.read_text())['replayed'] is result.replayed
    assert len(fake.calls) == 1


def test_atomic_replace_and_failure(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    projection.atomic_write(tmp_path, path.name, {'old': True})
    replace = os.replace
    def checked(src, dst, **kwargs):
        assert json.loads(path.read_text()) == {'old': True}
        assert json.loads((tmp_path / src).read_text()) == {'new': True}
        replace(src, dst, **kwargs)
    monkeypatch.setattr(os, 'replace', checked)
    projection.atomic_write(tmp_path, path.name, {'new': True})
    assert json.loads(path.read_text()) == {'new': True}
    assert path.stat().st_mode & 0o777 == 0o600
    def fail(*args, **kwargs): raise OSError('disk failure')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError): projection.atomic_write(tmp_path, path.name, {'partial': True})
    assert json.loads(path.read_text()) == {'new': True}
    assert list(tmp_path.iterdir()) == [path]


def test_authorities_unchanged():
    source = inspect.getsource(live)
    assert source.count('.execute_verified(') == 1
    for module in (live, projection):
        source = inspect.getsource(module)
        for forbidden in ('evaluate_bound(', '.execute(', 'shell=True', 'sudo', 'pkexec', 'systemd-run'):
            assert forbidden not in source


def test_post_observation_exception_preserves_durable_execution(setup):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    def provider():
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError('post observation unavailable')
        return snaps[0]
    surface.snapshot_provider = provider
    deliver(surface)
    assert surface.cycle() is None
    evidence = json.loads(surface.evidence_path.read_text())
    assert evidence['execution_success'] is True
    assert evidence['execution_exit_code'] == 0
    assert evidence['verification_success'] is None
    assert evidence['terminal_outcome'] == 'TERMINAL_FAILURE'
    assert len(fake.calls) == 1
    empty(runtime)


def test_evidence_write_failure_cannot_become_idle_proof(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    write = live.atomic_write
    def fail_evidence(root, name, record):
        if name == surface.evidence_path.name:
            raise OSError('disk error')
        write(root, name, record)
    monkeypatch.setattr(live, 'atomic_write', fail_evidence)
    deliver(surface)
    result = surface.cycle()
    assert result is surface.last_result
    assert read(surface)['phase'] == 'PROCESSING'
    surface.cycle()
    assert read(surface)['activation_empty'] is False
    assert len(fake.calls) == 1


def test_pending_inbox_fact(setup):
    surface = setup[3]
    deliver(surface)
    surface.publish_state('IDLE')
    record = read(surface)
    assert record['inbox_pending'] is True
    assert not projection.valid_idle_projection(record, expected_process=projection.process_identity(), now=1050)
    assert setup[2].calls == []


@pytest.mark.parametrize('unsafe', ['directory_symlink', 'writable_directory'])
def test_projection_rejects_unsafe_root(tmp_path, unsafe):
    root = tmp_path / 'root'
    if unsafe == 'directory_symlink':
        target = tmp_path / 'target'
        target.mkdir(mode=0o700)
        root.symlink_to(target, target_is_directory=True)
    else:
        root.mkdir()
        root.chmod(0o777)
    with pytest.raises((OSError, ValueError)):
        projection.atomic_write(root, 'state.json', {})
    assert not (root / 'state.json').exists()
