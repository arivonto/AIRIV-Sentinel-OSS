"""Gate 1 Commander-approved final-outcome semantics."""

from types import SimpleNamespace

import pytest

from sentinel.commander_intent import CommanderIntent
from sentinel.final_outcome_mapper import (
    FinalOutcomeMapper,
    FinalOutcomeMappingError,
)
from sentinel.remediation_policy import PolicyDecision
from sentinel.systemd_production_commander_authorization import (
    SystemdProductionCommanderAuthorizationContext,
)
from test_systemd_production_commander_incident_continuation_v1 import _build


def authorization_for(continuation):
    authorization = object.__new__(
        SystemdProductionCommanderAuthorizationContext
    )
    object.__setattr__(
        authorization,
        "binding",
        SimpleNamespace(
            prepared=continuation.prepared,
            approval_id=continuation.approval_id,
            incident_id=continuation.incident_id,
            component_id=continuation.component_id,
            execution_id=continuation.execution_id,
        ),
    )
    object.__setattr__(
        authorization,
        "approval",
        continuation.approval,
    )
    return authorization


def map_result(policy, execution=None, verification=None):
    continuation, *_ = _build()
    return FinalOutcomeMapper.map_commander_approved_remediation(
        intent=CommanderIntent.NEED_COMMANDER,
        continuation=continuation,
        commander_authorization=authorization_for(continuation),
        policy_decision=policy,
        execution_succeeded=execution,
        verification_succeeded=verification,
    )


def test_commander_approved_deny_stays_escalated():
    assert map_result(PolicyDecision.DENY) == "ESCALATED"


def test_commander_approved_allow_without_execution_is_unresolved():
    assert map_result(PolicyDecision.ALLOW) == "UNRESOLVED"


def test_commander_approved_execution_failure_is_unresolved():
    assert map_result(PolicyDecision.ALLOW, False) == "UNRESOLVED"


def test_commander_approved_verification_failure_is_unresolved():
    assert map_result(PolicyDecision.ALLOW, True, False) == "UNRESOLVED"


def test_commander_approved_verified_success_is_recovered():
    assert map_result(PolicyDecision.ALLOW, True, True) == "RECOVERED"


def test_commander_approved_path_cannot_be_relabeled_autonomous():
    continuation, *_ = _build()
    with pytest.raises(
        FinalOutcomeMappingError,
        match="requires NEED_COMMANDER intent",
    ):
        FinalOutcomeMapper.map_commander_approved_remediation(
            intent=CommanderIntent.AUTONOMOUS_REMEDIATE,
            continuation=continuation,
            commander_authorization=authorization_for(continuation),
            policy_decision=PolicyDecision.ALLOW,
            execution_succeeded=True,
            verification_succeeded=True,
        )


def test_commander_approved_continuity_mismatch_fails_closed():
    continuation, *_ = _build()
    authorization = authorization_for(continuation)
    authorization.binding.prepared = object()

    with pytest.raises(
        FinalOutcomeMappingError,
        match="authorization continuation mismatch",
    ):
        FinalOutcomeMapper.map_commander_approved_remediation(
            intent=CommanderIntent.NEED_COMMANDER,
            continuation=continuation,
            commander_authorization=authorization,
            policy_decision=PolicyDecision.ALLOW,
            execution_succeeded=True,
            verification_succeeded=True,
        )
