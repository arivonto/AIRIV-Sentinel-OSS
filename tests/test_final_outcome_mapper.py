import pytest

from sentinel.commander_intent import CommanderIntent
from sentinel.final_outcome_mapper import (
    FinalOutcomeMapper,
    FinalOutcomeMappingError,
)
from sentinel.incidents.manager import Incident
from sentinel.remediation_policy import PolicyDecision


def test_no_action_does_not_terminalize():
    assert (
        FinalOutcomeMapper.map(
            intent=CommanderIntent.NO_ACTION,
        )
        is None
    )


def test_insufficient_evidence_maps_to_insufficient_evidence():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.INSUFFICIENT_EVIDENCE,
    ) == "INSUFFICIENT_EVIDENCE"


def test_need_commander_maps_to_escalated():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.NEED_COMMANDER,
    ) == "ESCALATED"


def test_autonomous_remediation_deny_maps_to_escalated():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.DENY,
    ) == "ESCALATED"


def test_allow_without_execution_proof_maps_to_unresolved():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
    ) == "UNRESOLVED"


def test_execution_failure_maps_to_unresolved():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=False,
    ) == "UNRESOLVED"


def test_execution_success_without_verification_maps_to_unresolved():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
    ) == "UNRESOLVED"


def test_verification_failure_maps_to_unresolved():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
        verification_succeeded=False,
    ) == "UNRESOLVED"


def test_verified_success_maps_to_recovered():
    assert FinalOutcomeMapper.map(
        intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        policy_decision=PolicyDecision.ALLOW,
        execution_succeeded=True,
        verification_succeeded=True,
    ) == "RECOVERED"


def test_autonomous_remediation_requires_policy_decision():
    with pytest.raises(
        FinalOutcomeMappingError,
        match="requires PolicyDecision",
    ):
        FinalOutcomeMapper.map(
            intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
        )


def test_denied_execution_cannot_claim_execution_or_verification():
    with pytest.raises(
        FinalOutcomeMappingError,
        match="DENY must not contain",
    ):
        FinalOutcomeMapper.map(
            intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
            policy_decision=PolicyDecision.DENY,
            execution_succeeded=True,
            verification_succeeded=True,
        )


@pytest.mark.parametrize(
    "intent",
    [
        CommanderIntent.NO_ACTION,
        CommanderIntent.NEED_COMMANDER,
        CommanderIntent.INSUFFICIENT_EVIDENCE,
    ],
)
def test_non_remediation_intent_rejects_remediation_facts(intent):
    with pytest.raises(
        FinalOutcomeMappingError,
        match="non-remediation intent",
    ):
        FinalOutcomeMapper.map(
            intent=intent,
            policy_decision=PolicyDecision.ALLOW,
        )


def test_every_terminal_mapper_result_is_canonical_incident_outcome():
    cases = [
        FinalOutcomeMapper.map(
            intent=CommanderIntent.INSUFFICIENT_EVIDENCE,
        ),
        FinalOutcomeMapper.map(
            intent=CommanderIntent.NEED_COMMANDER,
        ),
        FinalOutcomeMapper.map(
            intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
            policy_decision=PolicyDecision.DENY,
        ),
        FinalOutcomeMapper.map(
            intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
            policy_decision=PolicyDecision.ALLOW,
            execution_succeeded=False,
        ),
        FinalOutcomeMapper.map(
            intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
            policy_decision=PolicyDecision.ALLOW,
            execution_succeeded=True,
            verification_succeeded=True,
        ),
    ]

    assert all(
        outcome in Incident.VALID_OUTCOMES
        for outcome in cases
    )
