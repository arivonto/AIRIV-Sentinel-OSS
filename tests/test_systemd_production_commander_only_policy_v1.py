"""D8.15 isolated durable facts; policy evaluation has no live effects."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from sentinel.remediation_policy import RemediationPolicy
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext as Context,
)
from sentinel.systemd_production_activation_binding import bind_consumed_activation_to_prepared_effect
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionStore as Store,
    SystemdProductionActivationConsumptionRecord as Record,
)
from sentinel.systemd_production_approval_issuance import SystemdProductionCommanderApprovalIssuer as Issuer
from sentinel.systemd_production_target_policy import (
    ProductionTargetMode as Mode, SystemdProductionTargetPolicy as Targets,
    SystemdProductionTargetRule as Rule, SystemdAttemptFact,
)
from test_systemd_production_approval_issuance_v1 import inputs, issue
from test_systemd_incident_dispatch_v1 import context


@pytest.fixture
def facts(tmp_path, inputs):
    issuer = Issuer(tmp_path / 'issuance')
    grant = issue(issuer, inputs)
    store = Store(tmp_path / 'consumption')
    record = store.consume(grant=grant, now=115, incident_id=grant.incident_id,
        component_id=grant.component_id, execution_id=grant.execution_id,
        effect_fingerprint=grant.effect_fingerprint)
    binding = bind_consumed_activation_to_prepared_effect(
        grant=grant, consumption=record, prepared=inputs[1], now=115)
    return binding, issuer, store


def make_context(facts):
    binding, issuer, store = facts
    return Context(binding=binding, issuer=issuer, consumption_store=store)


def policy_for(effect, mode=Mode.COMMANDER_ONLY):
    policy = RemediationPolicy({effect.action})
    policy.configure_bound_effect(effect)
    policy.configure_systemd_production_target_policy(Targets([
        Rule(effect.target.unit_name, mode)]))
    return policy


def evaluate(facts, auth=None, *, effect=None, policy=None, **kwargs):
    effect = facts[0].prepared.plan.effect if effect is None else effect
    policy = policy_for(effect) if policy is None else policy
    return policy.evaluate_systemd_production_bound(
        incident_state='INVESTIGATING', effect=effect,
        commander_authorization=auth, **dict(dict(now=115), **kwargs))[0]


@pytest.mark.parametrize('raw', [None, 'approval-14', 'activation-14',
    {'approval_id': 'approval-14'}, object()])
def test_missing_or_raw_context_denied(facts, raw):
    assert not evaluate(facts, raw).authorized


def test_exact_commander_context_preserves_allow(facts):
    assert evaluate(facts, make_context(facts)).authorized


@pytest.mark.parametrize('field,value', [
    ('incident_id', 'other'), ('execution_id', 'other'), ('action', 'other'),
    ('run_id', 'other'), ('permit_id', 'other'), ('scope_fingerprint', 'a'*64),
])
def test_requested_effect_substitution_denied(facts, field, value):
    auth = make_context(facts)
    effect = replace(facts[0].prepared.plan.effect, **{field: value})
    assert not evaluate(facts, auth, effect=effect).authorized


def test_exact_target_substitution_denied(facts):
    auth = make_context(facts)
    original = facts[0].prepared.plan.effect
    target = replace(original.target, unit_name='other.service')
    effect = replace(original, target=target, component_id=target.component_id)
    assert not evaluate(facts, auth, effect=effect).authorized


def test_non_live_identity_rejected_by_existing_bound_contract(facts):
    original = facts[0].prepared.plan.effect
    # Canonical identity validation rejects this before bound-effect construction.
    with pytest.raises(ValueError, match='^fragment_inode must be positive$'):
        target = replace(original.target, fragment_inode=0)
        replace(original, target=target)


@pytest.mark.parametrize('field,value', [('incident_id', 'other'),
    ('component_id', 'systemd:other.service'), ('action', 'other'),
    ('effect_fingerprint', 'a'*64), ('execution_id', 'other'),
    ('target_fingerprint', 'b'*64)])
def test_malformed_approved_binding_denied(facts, field, value):
    auth = make_context(facts)
    object.__setattr__(auth, 'approval', replace(auth.approval,
        effect=replace(auth.approval.effect, **{field: value})))
    assert not evaluate(facts, auth).authorized


@pytest.mark.parametrize('now', [114, 120, 121])
def test_authorization_time_denied(facts, now):
    assert not evaluate(facts, make_context(facts), now=now).authorized


def test_unconsumed_activation_cannot_construct_context(facts, tmp_path):
    with pytest.raises(ValueError, match='consumption_required'):
        Context(binding=facts[0], issuer=facts[1], consumption_store=Store(tmp_path / 'empty'))


def test_unissued_grant_cannot_construct_context(facts, tmp_path):
    with pytest.raises(ValueError, match='issuance_required'):
        Context(binding=facts[0], issuer=Issuer(tmp_path / 'empty'), consumption_store=facts[2])


def test_fabricated_consumption_value_insufficient(facts, tmp_path):
    binding = replace(facts[0], consumption=Record.from_grant(facts[0].grant, 115))
    with pytest.raises(ValueError, match='consumption_required'):
        Context(binding=binding, issuer=facts[1], consumption_store=Store(tmp_path / 'empty'))


def test_activation_binding_mismatch_denied(facts):
    auth = make_context(facts)
    object.__setattr__(auth.binding, 'grant', replace(auth.binding.grant, activation_id='other'))
    assert not evaluate(facts, auth).authorized


@pytest.mark.parametrize('field', ['binding', 'approval'])
def test_malformed_context_denied(facts, field):
    auth = make_context(facts)
    object.__setattr__(auth, field, None)
    assert not evaluate(facts, auth).authorized


def test_uninitialized_context_denied(facts):
    assert not evaluate(facts, object.__new__(Context)).authorized


def test_autonomous_unchanged(facts):
    policy = policy_for(facts[0].prepared.plan.effect, Mode.AUTONOMOUS)
    assert evaluate(facts, policy=policy).authorized
    assert evaluate(facts, object(), policy=policy).authorized


def test_canonical_deny_never_upgraded(facts):
    policy = policy_for(facts[0].prepared.plan.effect)
    policy.clear_bound_effects()
    assert not evaluate(facts, make_context(facts), policy=policy).authorized


def test_unknown_target_and_default_empty(facts):
    policy = policy_for(facts[0].prepared.plan.effect)
    policy.clear_systemd_production_target_policy()
    assert policy.list_systemd_production_targets() == ()
    assert RemediationPolicy().list_systemd_production_targets() == ()
    assert not evaluate(facts, make_context(facts), policy=policy).authorized


def test_protected_target_cannot_be_configured():
    with pytest.raises(ValueError, match='protected'):
        Targets([Rule('airiv-sentinel.service', Mode.COMMANDER_ONLY)])


@pytest.mark.parametrize('safety', ['cooldown', 'retry', 'lease'])
def test_commander_cannot_bypass_target_safety(facts, safety):
    effect = facts[0].prepared.plan.effect
    policy = policy_for(effect)
    kwargs = {}
    if safety == 'lease':
        kwargs['active_production_effects'] = 1
    else:
        policy.configure_systemd_production_target_policy(Targets([
            Rule(effect.target.unit_name, Mode.COMMANDER_ONLY,
                 cooldown_seconds=10 if safety == 'retry' else 300,
                 max_attempts_per_window=1 if safety == 'retry' else 10)]))
        kwargs['attempts'] = [SystemdAttemptFact(effect.target.unit_name, 'RESTART',
                                               100 if safety == 'retry' else 114)]
    assert not evaluate(facts, make_context(facts), policy=policy, **kwargs).authorized


def test_policy_has_no_durable_or_lifecycle_side_effects(facts, monkeypatch):
    auth = make_context(facts)
    from sentinel.incidents.manager import IncidentManager
    forbidden = Mock(side_effect=AssertionError('policy side effect'))
    for cls, names in [(Issuer, ('issue', 'records')), (Store, ('consume', 'records')),
                       (IncidentManager, ('resolve',))]:
        for name in names:
            monkeypatch.setattr(cls, name, forbidden)
    assert evaluate(facts, auth).authorized
    forbidden.assert_not_called()
