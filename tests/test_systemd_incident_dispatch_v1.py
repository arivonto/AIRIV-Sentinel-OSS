"""D8.6 synthetic evidence only; no host probes or production activation."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import inspect
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_assessor import CommanderIntentAssessor
from sentinel.commander_intent_decider import CommanderIntentDecider
from sentinel.commander_semantic_policy import CommanderSemanticPolicy, CommanderSemanticRule
from sentinel.diagnostic.commander_handoff import RemediationActionRequest
from sentinel.diagnostic.evaluator import DiagnosisEvaluator
from sentinel.diagnostic.models import (
    DiagnosticBudget, DiagnosisStatus, Hypothesis, HypothesisStatus,
    Investigation, InvestigationState, Observation, utc_now,
)
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_action_catalog import RemediationActionCatalog, RemediationActionEntry
from sentinel.systemd_incident_dispatch import assess_systemd_incident_dispatch as assess
from test_systemd_remediation_safety_boundary_v1 import identity, snapshot


@pytest.fixture
def context():
    manager = IncidentManager()
    incident = manager.evaluate_anomaly(
        observation={'pane_id': 'systemd:example.service'},
        anomaly_type='SYNTHETIC_SYSTEMD_FAILURE', reason='Synthetic diagnostic fixture',
    )
    manager.investigate(incident.component_id)
    investigation = Investigation(
        'inv-d86', incident.incident_id, incident.component_id, incident.anomaly_type,
        InvestigationState.ACTIVE, DiagnosticBudget(60, 10, 3, 10, 1),
        evidence_ids=['evidence-d86'], observation_ids=['evidence-d86'],
    )
    observation = Observation(
        'evidence-d86', investigation.investigation_id, '', incident.component_id,
        utc_now(), 'SYSTEMD', 'unit_snapshot', snapshot(active='failed'),
    )
    diagnosis = DiagnosisEvaluator().evaluate(investigation, [Hypothesis(
        'hyp-d86', investigation.investigation_id, 'Observed failed systemd unit',
        HypothesisStatus.SUPPORTED, ['evidence-d86'],
    )])
    investigation.diagnosis_id = diagnosis.diagnosis_id
    investigation.state = InvestigationState.COMPLETED
    semantics = CommanderSemanticPolicy()
    semantics.register(CommanderSemanticRule(incident.anomaly_type, True, False, 'Synthetic rule'))
    catalog = RemediationActionCatalog()
    catalog.register(RemediationActionEntry('RESTART', 'synthetic-unused', 'Fixture only'),
                     trigger=incident.anomaly_type)
    entry = catalog.select_for_trigger(incident.anomaly_type)
    assessment = CommanderIntentAssessor(semantics).assess(
        incident=incident, diagnosis=diagnosis, remediation_action_available=entry is not None,
    )
    return dict(incident=incident, investigation=investigation, diagnosis=diagnosis,
                assessment=assessment, decision=CommanderIntentDecider().decide(assessment),
                request=RemediationActionRequest.from_diagnosis(
                    incident_id=incident.incident_id, diagnosis=diagnosis, action=entry.action),
                observations=(observation,))


def test_candidate_is_immutable_routing_only(context):
    result = assess(**context)
    assert result.candidate
    assert result.incident_id == context['incident'].incident_id
    assert (result.component_id, result.unit, result.action) == (
        'systemd:example.service', 'example.service', 'RESTART')
    assert 'explicit_autonomous_production_target_rule' in result.required_downstream_facts
    with pytest.raises(FrozenInstanceError):
        result.candidate = False
    assert not hasattr(result, 'authorized')


@pytest.mark.parametrize('component', [
    '%1', '', None, ' systemd:example.service', 'systemd:', 'systemd:example',
    'systemd:example.socket', 'systemd:example.service ', 'systemd:*.service',
    'systemd:a?.service', 'systemd:a[1].service', 'systemd:a@.service',
    'systemd:a@instance.service', 'systemd:../a.service', 'SYSTEMD:example.service',
])
def test_invalid_components(context, component):
    context['incident'].component_id = component
    assert not assess(**context).candidate


@pytest.mark.parametrize('unit', [
    'airiv-sentinel.service', 'airiv-sentinel-remediation-canary.service',
    'dbus.service', 'systemd-journald.service',
])
def test_protected_names_use_existing_d81_predicate(context, unit):
    component = 'systemd:' + unit
    context['incident'].component_id = context['investigation'].component_id = component
    observation = context['observations'][0]
    observation.component_id = component
    observation.value = replace(observation.value, identity=replace(identity(), unit_name=unit))
    assert assess(**context).reasons == ('protected_target',)


@pytest.mark.parametrize('action', ['restart', 'START', 'restart_service', '', None, ['RESTART']])
def test_unsupported_action(context, action):
    context['request'] = replace(context['request'], action=action)
    assert 'unsupported_action' in assess(**context).reasons


@pytest.mark.parametrize('field,value', [
    ('status', 'TERMINAL'), ('status', 'OPEN'), ('lifecycle_state', 'TERMINAL'),
    ('final_outcome', 'RECOVERED'), ('incident_id', ''),
])
def test_lifecycle_and_identity(context, field, value):
    setattr(context['incident'], field, value)
    assert not assess(**context).candidate


@pytest.mark.parametrize('field,value', [
    ('status', DiagnosisStatus.INSUFFICIENT_EVIDENCE), ('status', 'ESTABLISHED'),
    ('supporting_evidence_ids', []), ('supporting_evidence_ids', None),
    ('supporting_evidence_ids', ['foreign']), ('conclusion', ''),
    ('contradictory_evidence_ids', ['evidence-d86']), ('investigation_id', 'foreign'),
])
def test_insufficient_or_foreign_diagnosis(context, field, value):
    setattr(context['diagnosis'], field, value)
    assert not assess(**context).candidate


@pytest.mark.parametrize('field,value', [
    ('incident_id', 'foreign'), ('component_id', 'foreign'), ('trigger', 'foreign'),
    ('diagnosis_id', 'foreign'), ('state', InvestigationState.ACTIVE),
    ('evidence_ids', []), ('observation_ids', []),
])
def test_investigation_binding(context, field, value):
    setattr(context['investigation'], field, value)
    assert not assess(**context).candidate


@pytest.mark.parametrize('field,value', [
    ('incident_id', 'foreign'), ('investigation_id', 'foreign'),
    ('diagnosis_id', 'foreign'), ('supporting_evidence_ids', ('foreign',)),
])
def test_request_binding(context, field, value):
    context['request'] = replace(context['request'], **{field: value})
    assert not assess(**context).candidate


@pytest.mark.parametrize('field,value', [
    ('semantic_configured', None), ('semantic_configured', False),
    ('commander_action_required', True), ('remediation_required', False),
    ('remediation_action_available', False),
    ('diagnosis_status', DiagnosisStatus.INSUFFICIENT_EVIDENCE),
])
def test_semantic_facts_fail_closed_even_with_autonomous_decision(context, field, value):
    context['assessment'] = replace(context['assessment'], **{field: value})
    assert not assess(**context).candidate


@pytest.mark.parametrize('intent', [CommanderIntent.NO_ACTION, CommanderIntent.NEED_COMMANDER,
                                    CommanderIntent.INSUFFICIENT_EVIDENCE, 'AUTONOMOUS_REMEDIATE'])
def test_non_autonomous_intent(context, intent):
    context['decision'] = replace(context['decision'], intent=intent)
    assert not assess(**context).candidate


@pytest.mark.parametrize('key', ['incident', 'investigation', 'diagnosis', 'assessment', 'decision', 'request'])
def test_missing_canonical_context(context, key):
    context[key] = None
    assert not assess(**context).candidate


@pytest.mark.parametrize('observations', [None, (), ('systemd:example.service',)])
def test_missing_evidence(context, observations):
    context['observations'] = observations
    assert not assess(**context).candidate


@pytest.mark.parametrize('field,value', [
    ('source', 'TMUX'), ('subject', 'raw_command'), ('investigation_id', 'foreign'),
    ('component_id', 'systemd:foreign.service'), ('observation_id', 'foreign'),
    ('value', None), ('value', {'unit_name': 'example.service'}),
])
def test_untrusted_or_unbound_observation(context, field, value):
    setattr(context['observations'][0], field, value)
    assert not assess(**context).candidate


def test_mismatched_identity(context):
    observation = context['observations'][0]
    observation.value = replace(observation.value, identity=replace(identity(), unit_name='other.service'))
    assert 'systemd_identity_mismatch' in assess(**context).reasons


@pytest.mark.parametrize('changes', [{'active_state': 'active'}, {'load_state': 'not-found'}, {'identity': None}])
def test_invalid_snapshot(context, changes):
    context['observations'][0].value = replace(context['observations'][0].value, **changes)
    assert not assess(**context).candidate


def test_duplicate_evidence(context):
    context['observations'] *= 2
    assert 'ambiguous_systemd_evidence' in assess(**context).reasons


def test_conflicting_snapshots(context):
    second = deepcopy(context['observations'][0])
    second.observation_id = 'second'
    second.value = replace(second.value, invocation_id='b' * 32)
    context['observations'] += (second,)
    context['diagnosis'].supporting_evidence_ids.append('second')
    context['investigation'].evidence_ids.append('second')
    context['investigation'].observation_ids.append('second')
    context['request'] = replace(context['request'], supporting_evidence_ids=('evidence-d86', 'second'))
    assert 'ambiguous_systemd_snapshots' in assess(**context).reasons


def test_assessment_has_no_authority_or_effects_and_runtime_stays_inert(context, monkeypatch, tmp_path):
    from sentinel.runtime import SentinelRuntime
    from sentinel.remediation_policy import RemediationPolicy
    from sentinel.systemd_production_target_policy import SystemdProductionTargetPolicy
    from sentinel.systemd_production_runtime_guard import SystemdProductionAttemptLedger, SystemdProductionEffectLease
    from sentinel.systemd_commander_integration import SystemdCommanderIntegration
    from sentinel.execution import ExecutionBoundary
    from sentinel.systemd_remediation_safety import SystemdRestartVerifier
    from sentinel.commander_intent_decider import CommanderIntentDecider
    from sentinel.final_outcome_mapper import FinalOutcomeMapper
    from test_systemd_production_runtime_composition_v1 import assert_inert
    monkeypatch.setenv('AIRIV_SENTINEL_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('AIRIV_SENTINEL_DIAGNOSTIC_DIR', str(tmp_path / 'diagnostic'))
    forbidden = Mock(side_effect=AssertionError('dispatch crossed authority boundary'))
    for owner, method in (
        (RemediationPolicy, 'evaluate'), (RemediationPolicy, 'evaluate_bound'),
        (RemediationPolicy, 'evaluate_systemd_production_bound'),
        (SystemdProductionTargetPolicy, 'assess'),
        (SystemdProductionAttemptLedger, '__init__'), (SystemdProductionAttemptLedger, 'append'),
        (SystemdProductionEffectLease, '__init__'), (SystemdProductionEffectLease, 'acquire'),
        (SystemdCommanderIntegration, 'execute_verified'), (ExecutionBoundary, 'execute'),
        (SystemdRestartVerifier, 'verify'), (IncidentManager, 'resolve'),
        (CommanderIntentDecider, 'decide'), (DiagnosisEvaluator, 'evaluate'),
        (FinalOutcomeMapper, 'map'),
    ):
        monkeypatch.setattr(owner, method, forbidden)
    monkeypatch.setattr('subprocess.run', forbidden)
    before = deepcopy(context)
    runtime = SentinelRuntime()
    assert assess(**context).candidate
    assert context['incident'].to_dict() == before['incident'].to_dict()
    for key in context.keys() - {'incident'}:
        assert context[key] == before[key]
    assert_inert(runtime)
    forbidden.assert_not_called()


def test_static_authority_surface():
    import sentinel.systemd_incident_dispatch as module
    source = inspect.getsource(module)
    for token in ('subprocess', 'systemctl', 'sudo', 'pkexec', 'systemd-run',
                  '.evaluate(', '.execute(', '.resolve(', '.verify(', 'production_runtime_guard(',
                  'build_bound_systemd_remediation_plan(', 'uuid4('):
        assert token not in source
