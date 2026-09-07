"""D8.14 synthetic trusted inputs and isolated filesystem only."""
from dataclasses import replace, FrozenInstanceError
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer as Issuer,
    TrustedSystemdProductionCommanderApproval as Approval,
)
from sentinel.systemd_production_activation import SystemdProductionActivationGrant
from sentinel.systemd_production_preparation import PreparedSystemdProductionRemediation
from test_systemd_incident_dispatch_v1 import context
from test_systemd_dispatch_evidence_binding_v1 import prepare, bind
from test_systemd_evidence_plan_handoff_v1 import handoff


@pytest.fixture
def inputs(context):
    binding = bind(*prepare(context))
    plan = handoff(binding)
    prepared = PreparedSystemdProductionRemediation(binding, plan, 115)
    return Approval('approval-14', plan.permit_binding, 110, 120), prepared


def issue(issuer, inputs, **changes):
    approval, prepared = inputs
    return issuer.issue(**dict(dict(approval=approval, prepared=prepared,
                                   activation_id='activation-14', now=115), **changes))


def test_exact_durable_grant_and_permissions(tmp_path, inputs):
    issuer = Issuer(tmp_path / 'issuance')
    grant = issue(issuer, inputs)
    assert type(grant) is SystemdProductionActivationGrant
    approval, prepared = inputs
    assert grant.matches_effect(incident_id=prepared.plan.effect.incident_id,
        component_id=prepared.plan.effect.component_id, execution_id=prepared.plan.effect.execution_id,
        effect_fingerprint=prepared.plan.effect.fingerprint)
    record, = issuer.records()
    assert record == dict(schema_version=1, approval_id=approval.approval_id,
        activation_id=grant.activation_id, issued_at=110.0, expires_at=120.0,
        effect=approval.effect.canonical_dict)
    path, = issuer.root.iterdir()
    assert json.loads(path.read_text()) == record
    assert path.stat().st_mode & 0o777 == 0o600
    assert issuer.root.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_uid == os.getuid()
    with pytest.raises(FrozenInstanceError):
        approval.approval_id = 'other'


@pytest.mark.parametrize('field,value', [
    ('execution_id', 'other'), ('incident_id', 'other'), ('component_id', 'systemd:other.service'),
    ('target_fingerprint', 'a'*64), ('action', 'other'), ('effect_fingerprint', 'a'*64),
])
@pytest.mark.parametrize('replay', [False, True])
def test_exact_substitution_rejected(tmp_path, inputs, field, value, replay):
    issuer = Issuer(tmp_path / 'issuance')
    if replay:
        issue(issuer, inputs)
    approval, prepared = inputs
    changed = replace(approval, effect=replace(approval.effect, **{field: value}))
    with pytest.raises(ValueError):
        issue(Issuer(issuer.root), (changed, prepared))
    assert len(issuer.records()) == int(replay)


@pytest.mark.parametrize('activation_id', ['activation-14', 'another'])
def test_replay_new_instance(tmp_path, inputs, activation_id):
    issue(Issuer(tmp_path), inputs)
    with pytest.raises(ValueError, match='already_issued'):
        issue(Issuer(tmp_path), inputs, activation_id=activation_id)


@pytest.mark.parametrize('now', [109, 120, 121, -1, float('nan'), float('inf'), True, '115', None])
def test_invalid_or_expired_now(tmp_path, inputs, now):
    with pytest.raises((TypeError, ValueError)):
        issue(Issuer(tmp_path), inputs, now=now)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('field,value', [('issued_at', -1), ('issued_at', float('nan')),
    ('expires_at', 110), ('expires_at', 100), ('expires_at', float('inf')),
    ('approval_id', '../bad'), ('approval_id', ''), ('approval_id', True)])
def test_invalid_approval(inputs, field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(inputs[0], **{field: value})


@pytest.mark.parametrize('field,value', [('plan', None), ('binding', None),
    ('prepared_at', 116), ('prepared_at', float('nan'))])
def test_malformed_prepared(tmp_path, inputs, field, value):
    with pytest.raises((TypeError, ValueError)):
        issue(Issuer(tmp_path), inputs, prepared=replace(inputs[1], **{field: value}))


@pytest.mark.parametrize('raw', ['', '{}', '{bad', '{"schema_version":99}'])
def test_corrupt_state(tmp_path, inputs, raw):
    record = tmp_path / 'corrupt.json'
    record.write_text(raw)
    record.chmod(0o600)
    with pytest.raises(ValueError, match='malformed'):
        issue(Issuer(tmp_path), inputs)


@pytest.mark.parametrize('kind', ['root_link', 'ancestor_link', 'unsafe_root', 'unsafe_ancestor', 'record_link'])
def test_unsafe_storage(tmp_path, inputs, kind):
    root = tmp_path / 'ledger'
    if kind == 'root_link':
        root.symlink_to(tmp_path, target_is_directory=True)
    elif kind == 'ancestor_link':
        root.symlink_to(tmp_path, target_is_directory=True)
        root = root / 'child'
    elif kind == 'unsafe_root':
        root.mkdir(mode=0o755)
    elif kind == 'unsafe_ancestor':
        root.mkdir(mode=0o700)
        root.chmod(0o777)
        root = root / 'child'
    else:
        root.mkdir(mode=0o700)
        (root / 'record').symlink_to(tmp_path / 'missing')
    with pytest.raises((OSError, ValueError)):
        issue(Issuer(root), inputs)


def test_concurrent_single_winner(tmp_path, inputs):
    def attempt(index):
        try:
            return issue(Issuer(tmp_path), inputs, activation_id=f'activation-{index}')
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(result is not None for result in results) == 1
    assert len(Issuer(tmp_path).records()) == 1


def test_default_root_inert():
    assert Issuer().root == Path.home() / '.local/state/airiv-sentinel-secure/systemd_production_approval_issuance'


def test_staging_files_are_not_committed_state(tmp_path, inputs):
    staging = tmp_path / '.pending-unpublished'
    staging.write_text('{partial')
    staging.chmod(0o600)
    issuer = Issuer(tmp_path)
    assert issuer.records() == ()
    issue(issuer, inputs)
    assert len(issuer.records()) == 1
    assert staging.read_text() == '{partial'


def test_disappearing_staging_snapshot_is_ignored(tmp_path, inputs, monkeypatch):
    issuer = Issuer(tmp_path)
    issue(issuer, inputs)
    listdir = os.listdir
    monkeypatch.setattr(os, 'listdir', lambda directory:
                        listdir(directory) + ['.pending-renamed-before-open'])
    assert len(issuer.records()) == 1
    with pytest.raises(ValueError, match='already_issued'):
        issue(issuer, inputs)


def test_disappearing_committed_snapshot_fails_closed(tmp_path, inputs, monkeypatch):
    issuer = Issuer(tmp_path)
    monkeypatch.setattr(os, 'listdir', lambda directory: ['a' * 64 + '.json'])
    with pytest.raises(FileNotFoundError):
        issuer.records()
    with pytest.raises(FileNotFoundError):
        issue(issuer, inputs)


@pytest.mark.parametrize('raw', ['', '{}', '{bad', '{"schema_version":99}'])
def test_malformed_canonical_record_fails_closed(tmp_path, inputs, raw):
    record = tmp_path / ('a' * 64 + '.json')
    record.write_text(raw)
    record.chmod(0o600)
    with pytest.raises(ValueError, match='malformed'):
        issue(Issuer(tmp_path), inputs)


def test_canonical_record_symlink_fails_closed(tmp_path, inputs):
    (tmp_path / ('a' * 64 + '.json')).symlink_to(tmp_path / 'missing')
    with pytest.raises(OSError):
        issue(Issuer(tmp_path), inputs)


def test_replay_with_entirely_rebound_execution(tmp_path, inputs):
    issue(Issuer(tmp_path), inputs)
    approval, prepared = inputs
    plan = handoff(prepared.binding, execution_id='new-execution')
    changed = replace(approval, effect=plan.permit_binding)
    with pytest.raises(ValueError, match='already_issued'):
        issue(Issuer(tmp_path), (changed, replace(prepared, plan=plan)), activation_id='new-activation')


def test_publication_failure_burns_approval(tmp_path, inputs, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('simulated publication failure')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail)
        with pytest.raises(OSError, match='simulated'):
            issue(Issuer(tmp_path), inputs)
    with pytest.raises(ValueError, match='malformed'):
        issue(Issuer(tmp_path), inputs)
