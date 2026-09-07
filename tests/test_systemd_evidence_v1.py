"""D8.7A: synthetic snapshots, isolated durable evidence, no host effects."""
import ast
from dataclasses import FrozenInstanceError, replace
import inspect
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from sentinel import systemd_evidence as module
from sentinel.systemd_evidence import TrustedSystemdEvidenceRecord as Record, TrustedSystemdEvidenceStore as Store
from sentinel.systemd_incident_dispatch import assess_systemd_incident_dispatch
from test_systemd_incident_dispatch_v1 import context
from test_systemd_remediation_safety_boundary_v1 import snapshot


def record(**kwargs):
    return Record(**dict(dict(incident_id='incident-exact', component_id='systemd:example.service',
                             investigation_id='investigation-exact', observation_id='observation-exact',
                             observed_at=1234.5, snapshot=snapshot(active='failed')), **kwargs))


def test_roundtrip_immutable_and_inert(tmp_path):
    store = Store()
    assert not store.root.exists()
    assert store.records() == ()
    assert not store.root.exists()
    original = record()
    key = store.append(original)
    loaded = Store().get(key)
    assert loaded == original
    assert loaded.incident_id == 'incident-exact'
    assert loaded.component_id == 'systemd:example.service'
    assert loaded.snapshot.identity == original.snapshot.identity
    assert loaded.snapshot.identity.fingerprint == original.snapshot.identity.fingerprint
    assert loaded.snapshot.invocation_id == original.snapshot.invocation_id
    assert loaded.to_dict() == original.to_dict()
    with pytest.raises(FrozenInstanceError):
        loaded.incident_id = 'other'
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert (store.root / (key + '.json')).stat().st_mode & 0o777 == 0o600
    for env in ('AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR', 'AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR'):
        assert not Path(os.environ[env]).exists()


def test_duplicate_no_overwrite():
    store = Store()
    key = store.append(record())
    path = store.root / (key + '.json')
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        store.append(record())
    assert path.read_bytes() == before
    assert len(store.records()) == 1


@pytest.mark.parametrize('field,value', [
    ('incident_id', ''), ('incident_id', ' padded '), ('component_id', 'systemd:other.service'),
    ('observed_at', float('nan')), ('observed_at', float('inf')), ('observed_at', -1),
    ('observed_at', True), ('observed_at', '123'), ('schema_version', True),
    ('schema_version', 2), ('source', 'TMUX'), ('evidence_type', 'unknown'),
    ('observation_id', ''), ('investigation_id', ''),
])
def test_invalid_record(field, value):
    with pytest.raises((TypeError, ValueError)):
        record(**{field: value})


@pytest.mark.parametrize('unit', ['*.service', 'a?.service', 'a[1].service', 'a@.service',
                                 'a@instance.service', 'a.socket', 'a.service '])
def test_invalid_unit(unit):
    with pytest.raises((TypeError, ValueError)):
        record(snapshot=replace(snapshot(), identity=replace(snapshot().identity, unit_name=unit)))


@pytest.mark.parametrize('field,value', [('main_pid', True), ('main_pid', 1.5),
    ('exec_main_start_timestamp_monotonic', 1.5), ('invocation_id', None), ('active_state', ' failed ')])
def test_strict_snapshot(field, value):
    with pytest.raises((TypeError, ValueError)):
        record(snapshot=replace(snapshot(), **{field: value}))


@pytest.mark.parametrize('mutation', ['json', 'fingerprint', 'target_fingerprint', 'manager_fingerprint',
                                      'filename', 'unknown', 'snapshot', 'version'])
def test_corrupt_durable_fails_closed(mutation):
    store = Store()
    key = store.append(record())
    path = store.root / (key + '.json')
    data = json.loads(path.read_text())
    if mutation == 'filename':
        path.rename(store.root / ('0' * 64 + '.json'))
    elif mutation == 'json':
        path.write_text('{')
    else:
        if mutation == 'unknown':
            data['extra'] = 1
        elif mutation == 'snapshot':
            data['snapshot']['main_pid'] = 3
        elif mutation == 'version':
            data['schema_version'] = 2
        else:
            data[mutation] = '0' * 64
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        store.records()
    with pytest.raises(ValueError):
        store.append(record(observed_at=2000))


@pytest.mark.parametrize('kind', ['root_symlink', 'ancestor_symlink', 'file_symlink', 'root_mode', 'file_mode', 'hardlink'])
def test_unsafe_storage(tmp_path, kind):
    store = Store()
    key = store.append(record())
    path = store.root / (key + '.json')
    if kind == 'root_symlink':
        link = tmp_path / 'link'
        link.symlink_to(store.root, target_is_directory=True)
        store = Store(link)
    elif kind == 'ancestor_symlink':
        link = tmp_path / 'link'
        link.symlink_to(tmp_path, target_is_directory=True)
        store = Store(link / store.root.name)
    elif kind == 'file_symlink':
        path.rename(store.root / 'original')
        path.symlink_to(store.root / 'original')
    elif kind == 'root_mode':
        store.root.chmod(0o770)
    elif kind == 'file_mode':
        path.chmod(0o666)
    else:
        os.link(path, tmp_path / 'other-link')
    with pytest.raises((ValueError, OSError)):
        store.records()


def test_fsync_and_atomic_failure(monkeypatch):
    real = os.fsync
    calls = []
    def sync(fd):
        calls.append(os.fstat(fd).st_mode)
        real(fd)
    monkeypatch.setattr(os, 'fsync', sync)
    store = Store()
    store.append(record())
    import stat
    assert any(stat.S_ISREG(mode) for mode in calls)
    assert any(stat.S_ISDIR(mode) for mode in calls)
    monkeypatch.setattr(os, 'link', Mock(side_effect=OSError('publication failed')))
    with pytest.raises(OSError):
        store.append(record(observed_at=2000))
    assert store.records() == (record(),)


def test_dispatch_durable_binding(context):
    observation = context['observations'][0]
    evidence = record(incident_id=context['incident'].incident_id,
                      investigation_id=context['investigation'].investigation_id,
                      observation_id=observation.observation_id,
                      observed_at=observation.observed_at.timestamp(), snapshot=observation.value)
    store = Store()
    key = store.append(evidence)
    assert assess_systemd_incident_dispatch(**context, trusted_evidence=(Store().get(key),)).candidate
    assert not assess_systemd_incident_dispatch(**context, trusted_evidence=(replace(evidence, incident_id='foreign'),)).candidate
    assert not assess_systemd_incident_dispatch(**context, trusted_evidence=()).candidate


def test_no_effect_authorities(monkeypatch, context):
    from sentinel.remediation_policy import RemediationPolicy
    from sentinel.incidents.manager import IncidentManager
    from sentinel.systemd_production_runtime_guard import SystemdProductionEffectLease, SystemdProductionAttemptLedger
    import sentinel.resource_bound_remediation as plans
    import subprocess
    for cls, name in ((RemediationPolicy, 'evaluate_bound'),
                      (RemediationPolicy, 'evaluate_systemd_production_bound'),
                      (IncidentManager, 'resolve'), (SystemdProductionEffectLease, 'acquire'),
                      (SystemdProductionAttemptLedger, 'append'),
                      (plans, 'build_bound_systemd_remediation_plan'), (subprocess, 'run')):
        monkeypatch.setattr(cls, name, Mock(side_effect=AssertionError(name)))
    previous = context['incident'].lifecycle_state
    Store().append(record())
    assert context['incident'].lifecycle_state == previous


def test_source_has_only_evidence_authority():
    tree = ast.parse(inspect.getsource(module))
    forbidden = {'evaluate_bound', 'evaluate_systemd_production_bound', 'execute_argv',
                 'subprocess', 'systemctl', 'sudo', 'pkexec', 'resolve', 'FinalOutcomeMapper',
                 'build_bound_systemd_remediation_plan', 'BoundSystemdRemediationPlan'}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & forbidden


def test_fresh_runtime_empty(monkeypatch, tmp_path):
    from sentinel.runtime import SentinelRuntime
    monkeypatch.setenv('AIRIV_SENTINEL_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('AIRIV_SENTINEL_DIAGNOSTIC_DIR', str(tmp_path / 'diagnostic'))
    runtime = SentinelRuntime()
    assert runtime.policy.list_systemd_production_targets() == ()
    assert not Store().root.exists()
