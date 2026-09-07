"""D8.7B pure handoff, synthetic evidence and isolated state only."""
import ast
from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from sentinel import systemd_evidence_plan_handoff as module
from sentinel.resource_bound_remediation import BoundSystemdRemediationPlan, ResourceBoundPermitBinding
from sentinel.systemd_dispatch_evidence_binding import TrustedSystemdDispatchEvidenceBinding as Binding
from sentinel.systemd_remediation_safety import SystemdPrivilegeBoundary, SystemdOperation
from test_systemd_dispatch_evidence_binding_v1 import prepare, bind
from test_systemd_incident_dispatch_v1 import context


def handoff(binding, **kwargs):
    return module.build_bound_systemd_plan_from_trusted_binding(**dict(
        dict(binding=binding, now=115, privilege=SystemdPrivilegeBoundary('/usr/bin/systemctl'),
             run_id='run-handoff', execution_id='execution-handoff', permit_id='permit-handoff'),
        **kwargs))


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def test_exact_canonical_continuity(context):
    assessment, evidence = prepare(context)
    binding = bind(assessment, evidence)
    plan = handoff(binding)
    assert type(plan) is BoundSystemdRemediationPlan
    assert plan.before is evidence.snapshot
    assert plan.scope.target is plan.effect.target is evidence.snapshot.identity
    assert plan.effect.incident_id == assessment.incident_id == evidence.incident_id
    assert plan.effect.component_id == assessment.component_id == evidence.component_id
    assert plan.scope.target.unit_name == assessment.unit
    assert plan.effect.target_fingerprint == binding.identity.target_fingerprint
    assert plan.before.invocation_id == binding.identity.invocation_id
    assert plan.before.identity.manager.fingerprint == evidence.snapshot.identity.manager.fingerprint
    assert plan.before.identity.canonical_dict == evidence.snapshot.identity.canonical_dict
    assert (plan.before.load_state, plan.before.active_state, plan.before.sub_state) == ('loaded', 'failed', evidence.snapshot.sub_state)
    assert plan.scope.expected_pre_active_state == 'failed'
    assert plan.scope.expected_post_active_state == 'active'
    assert plan.scope.require_new_invocation is True
    assert plan.scope.fingerprint == digest(plan.scope.canonical_dict)
    assert plan.effect.fingerprint == digest(plan.effect.canonical_dict)
    assert plan.effect.scope_fingerprint == plan.scope.fingerprint
    assert plan.permit_binding == ResourceBoundPermitBinding.from_effect(plan.effect)
    for field in ('run_id', 'incident_id', 'component_id', 'execution_id', 'permit_id',
                  'target_fingerprint', 'scope_fingerprint', 'action', 'resource_kind'):
        assert getattr(plan.permit_binding, field) == getattr(plan.effect, field)
    assert plan.permit_binding.effect_fingerprint == plan.effect.fingerprint
    assert assessment.action == 'RESTART'
    assert plan.effect.action == 'systemd_restart'
    assert plan.scope.operation is SystemdOperation.RESTART
    assert plan.effect.argv == ('/usr/bin/systemctl', '--no-ask-password', 'restart', assessment.unit)


@pytest.mark.parametrize('now', [100, 109, 110, 120])
def test_freshness_inclusive_and_binding_semantics(context, now):
    binding = bind(*prepare(context))
    assert binding.is_fresh(now)
    assert handoff(binding, now=now)


@pytest.mark.parametrize('now', [99, 120.001, -1, float('nan'), float('inf'),
                                -float('inf'), True, '115', None, 10**1000])
def test_invalid_or_expired_handoff(context, monkeypatch, now):
    binding = bind(*prepare(context))
    assert not binding.is_fresh(now)
    builder = Mock(side_effect=AssertionError('must not construct'))
    monkeypatch.setattr(module, 'build_bound_systemd_remediation_plan', builder)
    with pytest.raises(ValueError, match='fresh'):
        handoff(binding, now=now)
    builder.assert_not_called()


def test_reuses_freshness_then_canonical_builder(context, monkeypatch):
    binding = bind(*prepare(context))
    calls = []
    fresh = Binding.is_fresh
    builder = module.build_bound_systemd_remediation_plan
    def check(self, now):
        calls.append(('fresh', self, now))
        return fresh(self, now)
    def build(**kwargs):
        calls.append(('build', kwargs))
        return builder(**kwargs)
    monkeypatch.setattr(Binding, 'is_fresh', check)
    monkeypatch.setattr(module, 'build_bound_systemd_remediation_plan', build)
    handoff(binding)
    assert [c[0] for c in calls] == ['fresh', 'build']
    assert calls[0][1:] == (binding, 115)
    assert calls[1][1]['before'] is binding.evidence.snapshot


@pytest.mark.parametrize('field', ['run_id', 'execution_id', 'permit_id'])
@pytest.mark.parametrize('value', ['', ' ', None, 4])
def test_canonical_id_validation(context, field, value):
    with pytest.raises((TypeError, ValueError)):
        handoff(bind(*prepare(context)), **{field: value})


def test_ids_not_derived_from_evidence(context):
    binding = bind(*prepare(context))
    first = handoff(binding)
    second = handoff(binding, execution_id='another-execution', permit_id='another-permit')
    assert first.effect.fingerprint != second.effect.fingerprint
    assert second.effect.execution_id == 'another-execution'
    assert second.effect.policy_run_id == 'run-handoff'


@pytest.mark.parametrize('field', ['evidence', 'assessment', 'incident_id', 'component_id', 'unit', 'scope', 'action'])
def test_no_loose_substitution_api(context, field):
    binding = bind(*prepare(context))
    with pytest.raises(TypeError):
        handoff(binding, **{field: binding.evidence})


def test_binding_a_cannot_use_evidence_b(context):
    assessment, evidence = prepare(context)
    other_context = deepcopy(context)
    observation = other_context['observations'][0]
    observation.value = replace(observation.value, invocation_id='b' * 32,
        identity=replace(observation.value.identity, fragment_sha256='b' * 64))
    other_assessment, other = prepare(other_context)
    with pytest.raises(ValueError):
        bind(assessment, other)
    assert handoff(bind(assessment, evidence)).before is evidence.snapshot
    assert handoff(bind(other_assessment, other)).before is other.snapshot


def test_unbound_and_non_candidate_rejected(context):
    assessment, evidence = prepare(context)
    for value in (None, evidence, assessment, (assessment, evidence), Mock()):
        with pytest.raises(TypeError):
            handoff(value)
    with pytest.raises(ValueError):
        handoff(bind(replace(assessment, candidate=False), evidence))


@pytest.mark.parametrize('unit', ['airiv-sentinel.service', 'airiv-sentinel-remediation-canary.service',
                                 '*.service', 'a@.service', 'a@instance.service'])
def test_excluded_targets(context, unit):
    observation = context['observations'][0]
    component = 'systemd:' + unit
    context['incident'].component_id = context['investigation'].component_id = component
    observation.component_id = component
    with pytest.raises((ValueError, TypeError)):
        observation.value = replace(observation.value, identity=replace(observation.value.identity, unit_name=unit))
        handoff(bind(*prepare(context)))


@pytest.mark.parametrize('unit', ['airiv-sentinel.service', 'airiv-sentinel-remediation-canary.service'])
def test_structural_protection_even_for_direct_assessment(context, unit):
    from sentinel.systemd_incident_dispatch import SystemdDispatchEvidenceIdentity
    assessment, evidence = prepare(context)
    evidence = replace(evidence, component_id='systemd:' + unit,
        snapshot=replace(evidence.snapshot, identity=replace(evidence.snapshot.identity, unit_name=unit)))
    assessment = replace(assessment, component_id=evidence.component_id, unit=unit,
                         trusted_evidence_identities=(SystemdDispatchEvidenceIdentity.from_record(evidence),))
    with pytest.raises(ValueError, match='protected_target'):
        handoff(bind(assessment, evidence))


def test_required_inputs(context):
    params = dict(binding=bind(*prepare(context)), now=115,
                  privilege=SystemdPrivilegeBoundary('/usr/bin/systemctl'),
                  run_id='run', execution_id='exec', permit_id='permit')
    for field in params:
        with pytest.raises(TypeError):
            module.build_bound_systemd_plan_from_trusted_binding(**{k: v for k, v in params.items() if k != field})
    with pytest.raises(TypeError):
        handoff(params['binding'], privilege=Mock())


@pytest.mark.parametrize('existing', [False, True])
def test_no_authorities_or_filesystem_mutation(context, monkeypatch, tmp_path, existing):
    import sentinel.systemd_production_runtime_guard as guard
    import sentinel.systemd_commander_integration as integration
    import sentinel.systemd_incident_dispatch as dispatch
    from sentinel.remediation_policy import RemediationPolicy
    from sentinel.incidents.manager import IncidentManager
    from sentinel.execution import ExecutionBoundary
    from sentinel.generic_execution_permit_adapter import GenericResourceExecutionPermitAdapter
    from sentinel.remediation_execution_identity import RemediationExecutionIdentityJournal as Journal
    from sentinel.systemd_remediation_safety import SystemdRestartVerifier
    from sentinel.systemd_evidence import TrustedSystemdEvidenceStore
    binding = bind(*prepare(context))
    before_incident = context['incident'].to_dict()
    roots = [Path(os.environ[env]) for env in ('AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR',
        'AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR', 'AIRIV_SENTINEL_SYSTEMD_EVIDENCE_DIR')]
    if existing:
        for root in roots:
            root.mkdir()
            (root / 'unchanged').write_bytes(b'existing state')
    def state():
        return [(str(p), p.read_bytes() if p.is_file() else None) for p in sorted(tmp_path.rglob('*'))]
    before = state()
    forbidden = Mock(side_effect=AssertionError('authority crossed'))
    for owner, name in [(RemediationPolicy, 'evaluate_bound'),
        (RemediationPolicy, 'evaluate_systemd_production_bound'), (guard, 'production_runtime_guard'),
        (integration, 'production_runtime_guard'), (dispatch, 'assess_systemd_incident_dispatch'),
        (GenericResourceExecutionPermitAdapter, 'execute'), (ExecutionBoundary, 'execute'),
        (ExecutionBoundary, 'execute_argv'), (Journal, 'claim'), (Journal, 'claim_live_run_permit'),
        (guard.SystemdProductionAttemptLedger, 'append'), (guard.SystemdProductionEffectLease, 'acquire'),
        (SystemdRestartVerifier, 'verify'), (IncidentManager, 'resolve'),
        (TrustedSystemdEvidenceStore, 'append')]:
        monkeypatch.setattr(owner, name, forbidden)
    assert handoff(binding)
    with pytest.raises(ValueError):
        handoff(binding, now=121)
    forbidden.assert_not_called()
    assert context['incident'].to_dict() == before_incident
    assert state() == before


def test_static_closed_call_surface():
    tree = ast.parse(inspect.getsource(module))
    calls = {n.func.id if isinstance(n.func, ast.Name) else n.func.attr
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert calls <= {'type', 'TypeError', 'ValueError', '__post_init__', 'protected_target',
                     'BoundSystemdActionScope', 'is_fresh', 'build_bound_systemd_remediation_plan'}
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports == {'sentinel.resource_bound_remediation', 'sentinel.systemd_dispatch_evidence_binding',
                       'sentinel.systemd_production_target_policy', 'sentinel.systemd_remediation_safety'}
    assert not any(isinstance(n, ast.Import) for n in ast.walk(tree))


def test_fresh_runtime_empty_allowlist():
    from sentinel.runtime import SentinelRuntime
    assert SentinelRuntime().policy.list_systemd_production_targets() == ()
