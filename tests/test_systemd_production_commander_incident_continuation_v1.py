import pytest

from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_decider import (
    CommanderIntentDecision,
)
from sentinel.incidents.manager import Incident
from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_approval_issuance import (
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_commander_incident_continuation import (
    SystemdProductionCommanderIncidentContinuation,
    build_systemd_production_commander_incident_continuation,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
)


class _Effect:
    incident_id = "incident-d816"
    component_id = "systemd:d816-test.service"
    action = ACTION_RESTART
    execution_id = "execution-d816"


class _Plan:
    effect = _Effect()
    permit_binding = object()


def _exact_shell(cls, **values):
    obj = object.__new__(cls)

    for name, value in values.items():
        object.__setattr__(
            obj,
            name,
            value,
        )

    return obj


def _fixture():
    incident = Incident(
        "incident-d816",
        "systemd:d816-test.service",
        "sentinel",
        "SYSTEMD_TEST",
    )

    incident.status = "INVESTIGATING"
    incident.lifecycle_state = "INVESTIGATING"
    incident.final_outcome = None

    decision = _exact_shell(
        CommanderIntentDecision,
        intent=CommanderIntent.NEED_COMMANDER,
    )

    binding = _exact_shell(
        TrustedSystemdDispatchEvidenceBinding,
    )

    prepared = _exact_shell(
        PreparedSystemdProductionRemediation,
        binding=binding,
        plan=_Plan(),
        prepared_at=100.0,
    )

    approval = _exact_shell(
        TrustedSystemdProductionCommanderApproval,
        approval_id="approval-d816",
        effect=_Plan.permit_binding,
        issued_at=100.0,
        expires_at=200.0,
    )

    return (
        incident,
        decision,
        binding,
        prepared,
        approval,
    )


def _build(now=150.0):
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    continuation = (
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=now,
        )
    )

    return (
        continuation,
        incident,
        decision,
        binding,
        prepared,
        approval,
    )


def test_exact_commander_only_continuation():
    continuation, *_ = _build()

    assert (
        type(continuation)
        is SystemdProductionCommanderIncidentContinuation
    )

    assert continuation.incident_id == "incident-d816"
    assert continuation.component_id == (
        "systemd:d816-test.service"
    )
    assert continuation.action == ACTION_RESTART
    assert continuation.execution_id == "execution-d816"
    assert continuation.approval_id == "approval-d816"


def test_need_commander_is_required():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    object.__setattr__(
        decision,
        "intent",
        CommanderIntent.AUTONOMOUS_REMEDIATE,
    )

    with pytest.raises(
        ValueError,
        match="requires_need_commander",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_incident_must_be_investigating():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    incident.status = "TERMINAL"
    incident.lifecycle_state = "TERMINAL"
    incident.final_outcome = "ESCALATED"

    with pytest.raises(
        ValueError,
        match="requires_active_investigation",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_terminalized_incident_cannot_continue():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    incident.final_outcome = "ESCALATED"

    with pytest.raises(
        ValueError,
        match="requires_active_investigation",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_incident_binding_mismatch_denied():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    incident.incident_id = "wrong-incident"

    with pytest.raises(
        ValueError,
        match="incident_binding_mismatch",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_component_binding_mismatch_denied():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    incident.component_id = (
        "systemd:wrong.service"
    )

    with pytest.raises(
        ValueError,
        match="component_binding_mismatch",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_evidence_binding_mismatch_denied():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    other = _exact_shell(
        TrustedSystemdDispatchEvidenceBinding,
    )

    object.__setattr__(
        prepared,
        "binding",
        other,
    )

    with pytest.raises(
        ValueError,
        match="trusted_evidence_binding_mismatch",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_approval_effect_binding_mismatch_denied():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    object.__setattr__(
        approval,
        "effect",
        object(),
    )

    with pytest.raises(
        ValueError,
        match="approval_effect_binding_mismatch",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=150.0,
        )


def test_expired_approval_denied():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    with pytest.raises(
        ValueError,
        match="commander_approval_not_current",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=200.0,
        )


def test_future_approval_denied():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    with pytest.raises(
        ValueError,
        match="commander_approval_not_current",
    ):
        build_systemd_production_commander_incident_continuation(
            incident=incident,
            decision=decision,
            binding=binding,
            prepared=prepared,
            approval=approval,
            now=99.0,
        )


def test_builder_does_not_mutate_incident():
    (
        incident,
        decision,
        binding,
        prepared,
        approval,
    ) = _fixture()

    before = (
        incident.status,
        incident.lifecycle_state,
        incident.final_outcome,
        incident.incident_id,
        incident.component_id,
    )

    build_systemd_production_commander_incident_continuation(
        incident=incident,
        decision=decision,
        binding=binding,
        prepared=prepared,
        approval=approval,
        now=150.0,
    )

    after = (
        incident.status,
        incident.lifecycle_state,
        incident.final_outcome,
        incident.incident_id,
        incident.component_id,
    )

    assert after == before
