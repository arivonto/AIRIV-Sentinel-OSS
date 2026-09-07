"""D8.7A.1: exact continuity, explicit freshness, no effects."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import inspect
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from sentinel import systemd_dispatch_evidence_binding as module
from sentinel.systemd_dispatch_evidence_binding import TrustedSystemdDispatchEvidenceBinding as Binding
from sentinel.systemd_evidence import TrustedSystemdEvidenceRecord as Record, TrustedSystemdEvidenceStore as Store
from sentinel.systemd_incident_dispatch import assess_systemd_incident_dispatch as assess
from test_systemd_incident_dispatch_v1 import context


def prepare(context, observed_at=100):
    observation = context['observations'][0]
    observation.observed_at = datetime.fromtimestamp(observed_at, timezone.utc)
    evidence = Record(incident_id=context['incident'].incident_id,
                      component_id=observation.component_id,
                      observation_id=observation.observation_id,
                      investigation_id=observation.investigation_id,
                      observed_at=observed_at, snapshot=observation.value)
    return assess(**context, trusted_evidence=(evidence,)), evidence


def bind(assessment, evidence, now=110, max_age_seconds=20):
    return Binding(assessment=assessment, evidence=evidence, now=now,
                   max_age_seconds=max_age_seconds)


def test_retention_and_legacy(context):
    legacy = assess(**context)
    assessment, evidence = prepare(context)
    identity, = assessment.trusted_evidence_identities
    assert identity.evidence_fingerprint == evidence.fingerprint
    assert identity.target_fingerprint == evidence.snapshot.identity.fingerprint
    assert identity.invocation_id == evidence.snapshot.invocation_id
    assert identity.observed_at == evidence.observed_at
    assert legacy.trusted_evidence_identities == ()
    for field in ('candidate', 'incident_id', 'component_id', 'unit', 'action', 'reasons',
                  'required_downstream_facts'):
        assert getattr(assessment, field) == getattr(legacy, field)
    with pytest.raises(ValueError):
        bind(legacy, evidence)
    with pytest.raises(FrozenInstanceError):
        identity.observed_at = 0


def test_matching_and_immutable(context):
    assessment, evidence = prepare(context)
    binding = bind(assessment, evidence)
    assert binding.evidence is evidence
    assert binding.assessment is assessment
    assert binding.validated_at == 110
    assert binding.max_age_seconds == 20
    assert binding.expires_at == 120
    assert binding.identity == assessment.trusted_evidence_identities[0]
    with pytest.raises(FrozenInstanceError):
        binding.expires_at = 1000
    # A durable roundtrip of exactly the same content is valid identity continuity.
    assert bind(assessment, Record.from_dict(evidence.to_dict())) == binding


@pytest.mark.parametrize('field,value', [
    ('evidence_fingerprint', '0' * 64), ('target_fingerprint', '0' * 64),
    ('invocation_id', 'b' * 32), ('observed_at', 99),
])
def test_each_retained_fact_checked_independently(context, field, value):
    assessment, evidence = prepare(context)
    identity = replace(assessment.trusted_evidence_identities[0], **{field: value})
    with pytest.raises(ValueError, match='continuity'):
        bind(replace(assessment, trusted_evidence_identities=(identity,)), evidence)


@pytest.mark.parametrize('change', ['observation', 'investigation', 'target', 'invocation', 'time', 'pid'])
def test_real_record_substitution(context, change):
    assessment, evidence = prepare(context)
    if change == 'observation':
        other = replace(evidence, observation_id='other')
    elif change == 'investigation':
        other = replace(evidence, investigation_id='other')
    elif change == 'target':
        other = replace(evidence, snapshot=replace(evidence.snapshot,
            identity=replace(evidence.snapshot.identity, fragment_sha256='b' * 64)))
    elif change == 'invocation':
        other = replace(evidence, snapshot=replace(evidence.snapshot, invocation_id='b' * 32))
    elif change == 'pid':
        other = replace(evidence, snapshot=replace(evidence.snapshot, main_pid=2000))
    else:
        other = replace(evidence, observed_at=99)
    assert other.fingerprint != evidence.fingerprint
    with pytest.raises(ValueError):
        bind(assessment, other)


@pytest.mark.parametrize('field,value', [('candidate', False), ('candidate', 1),
    ('incident_id', 'foreign'), ('component_id', 'foreign'), ('unit', 'other.service'),
    ('action', 'START'), ('action', None), ('trusted_evidence_identities', ()),
    ('trusted_evidence_identities', [])])
def test_assessment_facts(context, field, value):
    assessment, evidence = prepare(context)
    with pytest.raises(ValueError):
        bind(replace(assessment, **{field: value}), evidence)


def test_same_routing_cannot_substitute(context):
    assessment, evidence = prepare(context)
    other_context = deepcopy(context)
    observation = other_context['observations'][0]
    observation.value = replace(observation.value, invocation_id='b' * 32,
        identity=replace(observation.value.identity, fragment_sha256='b' * 64))
    other_assessment, other = prepare(other_context)
    assert assessment.candidate and other_assessment.candidate
    assert replace(assessment, trusted_evidence_identities=()) == replace(
        other_assessment, trusted_evidence_identities=())
    assert assessment != other_assessment
    with pytest.raises(ValueError):
        bind(assessment, other)
    assert bind(other_assessment, other)


def test_multiple_consumed_records_retained(context):
    _, first = prepare(context)
    second = deepcopy(context['observations'][0])
    second.observation_id = 'second'
    context['observations'] += (second,)
    context['diagnosis'].supporting_evidence_ids.append('second')
    context['investigation'].evidence_ids.append('second')
    context['investigation'].observation_ids.append('second')
    context['request'] = replace(context['request'], supporting_evidence_ids=(first.observation_id, 'second'))
    other = replace(first, observation_id='second')
    assessment = assess(**context, trusted_evidence=(other, first))
    assert assessment.candidate
    assert [i.evidence_fingerprint for i in assessment.trusted_evidence_identities] == [first.fingerprint, other.fingerprint]
    assert bind(assessment, first)
    assert bind(assessment, other)
    with pytest.raises(ValueError):
        bind(assessment, replace(other, observation_id='third'))


@pytest.mark.parametrize('now', [100, 110, 120])
def test_fresh_inclusive(context, now):
    assessment, evidence = prepare(context)
    assert bind(assessment, evidence, now=now).is_fresh(now)


@pytest.mark.parametrize('now', [99, 120.001, -1, float('nan'), float('inf'),
                                -float('inf'), True, '110', None, 10**1000])
def test_invalid_or_stale_time(context, now):
    assessment, evidence = prepare(context)
    with pytest.raises(ValueError):
        bind(assessment, evidence, now=now)
    assert not bind(assessment, evidence).is_fresh(now)


@pytest.mark.parametrize('limit', [0, -1, float('nan'), float('inf'), -float('inf'),
                                  True, '20', None, 10**1000])
def test_invalid_age_limit(context, limit):
    assessment, evidence = prepare(context)
    with pytest.raises(ValueError):
        bind(assessment, evidence, max_age_seconds=limit)


def test_explicit_inputs_required(context):
    assessment, evidence = prepare(context)
    for inputs in ({}, {'now': 110}, {'max_age_seconds': 20}):
        with pytest.raises(TypeError):
            Binding(assessment=assessment, evidence=evidence, **inputs)


def test_zero_persistence_separate_from_freshness(context):
    assessment, evidence = prepare(context, observed_at=0)
    store = Store()
    loaded = store.get(store.append(evidence))
    assert loaded == evidence and loaded.observed_at == 0
    assert bind(assessment, loaded, now=0).is_fresh(20)
    with pytest.raises(ValueError, match='stale'):
        bind(assessment, loaded, now=100)


def test_no_authority_calls(context, monkeypatch):
    from sentinel.remediation_policy import RemediationPolicy
    from sentinel.incidents.manager import IncidentManager
    from sentinel.systemd_production_runtime_guard import SystemdProductionAttemptLedger, SystemdProductionEffectLease
    from sentinel.execution import ExecutionBoundary
    from sentinel.systemd_remediation_safety import SystemdRestartVerifier
    import sentinel.resource_bound_remediation as plans
    assessment, evidence = prepare(context)
    before = context['incident'].to_dict()
    forbidden = Mock(side_effect=AssertionError('authority crossed'))
    for owner, name in [(RemediationPolicy, 'evaluate_bound'),
        (RemediationPolicy, 'evaluate_systemd_production_bound'),
        (plans, 'BoundSystemdRemediationPlan'), (plans, 'build_bound_systemd_remediation_plan'),
        (Store, '__init__'), (Store, 'append'), (SystemdProductionAttemptLedger, 'append'),
        (SystemdProductionEffectLease, 'acquire'), (ExecutionBoundary, 'execute'),
        (SystemdRestartVerifier, 'verify'), (IncidentManager, 'resolve')]:
        monkeypatch.setattr(owner, name, forbidden)
    assert bind(assessment, evidence).is_fresh(120)
    with pytest.raises(ValueError):
        bind(assessment, evidence, now=121)
    assert context['incident'].to_dict() == before
    forbidden.assert_not_called()
    for env in ('AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR',
                'AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR', 'AIRIV_SENTINEL_SYSTEMD_EVIDENCE_DIR'):
        assert not Path(os.environ[env]).exists()


def test_static_authority_surface():
    tree = ast.parse(inspect.getsource(module))
    forbidden = {'evaluate', 'evaluate_bound', 'evaluate_systemd_production_bound',
        'production_runtime_guard', 'execute', 'execute_argv', 'claim', 'verify', 'resolve',
        'subprocess', 'systemctl', 'busctl', 'pkcheck', 'sudo', 'pkexec',
        'BoundSystemdRemediationPlan', 'build_bound_systemd_remediation_plan',
        'ResourceBoundPermitBinding', 'ExecutionIdentityRecord', 'open', 'append'}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & forbidden
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {'dataclasses', 'sentinel.systemd_evidence',
                      'sentinel.systemd_incident_dispatch', 'sentinel.systemd_production_target_policy'}
    assert 'systemd-run' not in inspect.getsource(module)


def test_production_allowlist_empty():
    from sentinel.remediation_policy import RemediationPolicy
    assert RemediationPolicy().list_systemd_production_targets() == ()
