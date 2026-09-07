import pytest

import sentinel.systemd_production_commander_activation_binding as d819

from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionRecord,
)
from sentinel.systemd_production_approval_issuance import (
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_commander_incident_continuation import (
    SystemdProductionCommanderIncidentContinuation,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
)


def _exact_shell(cls, **values):
    obj = object.__new__(cls)

    for name, value in values.items():
        object.__setattr__(
            obj,
            name,
            value,
        )

    return obj


class _Effect:
    incident_id = "incident-d819"
    component_id = "systemd:d819-test.service"
    action = ACTION_RESTART
    execution_id = "execution-d819"
    fingerprint = "f" * 64


class _Plan:
    effect = _Effect()
    permit_binding = object()


def _fixture():
    evidence = _exact_shell(
        TrustedSystemdDispatchEvidenceBinding,
    )

    prepared = _exact_shell(
        PreparedSystemdProductionRemediation,
        binding=evidence,
        plan=_Plan(),
        prepared_at=110.0,
    )

    approval = _exact_shell(
        TrustedSystemdProductionCommanderApproval,
        approval_id="approval-d819",
        effect=_Plan.permit_binding,
        issued_at=100.0,
        expires_at=200.0,
    )

    continuation = (
        SystemdProductionCommanderIncidentContinuation(
            incident_id="incident-d819",
            component_id="systemd:d819-test.service",
            action=ACTION_RESTART,
            execution_id="execution-d819",
            approval_id="approval-d819",
            continued_at=120.0,
            approval_expires_at=200.0,
            binding=evidence,
            prepared=prepared,
            approval=approval,
        )
    )

    grant = SystemdProductionActivationGrant(
        activation_id="ACT-D819",
        approval_id="approval-d819",
        incident_id="incident-d819",
        component_id="systemd:d819-test.service",
        execution_id="execution-d819",
        effect_fingerprint="f" * 64,
        issued_at=100.0,
        expires_at=200.0,
    )

    consumption = SystemdProductionActivationConsumptionRecord(
        activation_id=grant.activation_id,
        approval_id=grant.approval_id,
        incident_id=grant.incident_id,
        component_id=grant.component_id,
        execution_id=grant.execution_id,
        effect_fingerprint=grant.effect_fingerprint,
        grant_fingerprint=grant.fingerprint,
        consumed_at=130.0,
    )

    return (
        continuation,
        grant,
        consumption,
    )


def _binding(
    grant,
    consumption,
    prepared,
    bound_at,
):
    return _exact_shell(
        SystemdProductionConsumedActivationBinding,
        grant=grant,
        consumption=consumption,
        prepared=prepared,
        bound_at=bound_at,
    )


def _install_canonical_fake(
    monkeypatch,
    calls,
):
    def fake_bind(
        *,
        grant,
        consumption,
        prepared,
        now,
    ):
        calls.append(
            dict(
                grant=grant,
                consumption=consumption,
                prepared=prepared,
                now=now,
            )
        )

        return _binding(
            grant,
            consumption,
            prepared,
            now,
        )

    monkeypatch.setattr(
        d819,
        "bind_consumed_activation_to_prepared_effect",
        fake_bind,
    )


def test_delegates_exactly_once_to_d810c(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    binding = (
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )
    )

    assert (
        type(binding)
        is SystemdProductionConsumedActivationBinding
    )

    assert len(calls) == 1

    call = calls[0]

    assert call["grant"] is grant
    assert call["consumption"] is consumption
    assert call["prepared"] is continuation.prepared
    assert call["now"] == 140.0


def test_exact_input_types_required(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    with pytest.raises(
        TypeError,
        match="canonical Commander incident continuation",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=object(),
            grant=grant,
            consumption=consumption,
            now=140.0,
        )

    with pytest.raises(
        TypeError,
        match="canonical activation grant",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=object(),
            consumption=consumption,
            now=140.0,
        )

    with pytest.raises(
        TypeError,
        match="canonical activation consumption record",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=object(),
            now=140.0,
        )


def test_time_reversal_fails_before_d810c(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    with pytest.raises(
        ValueError,
        match="activation_binding_time_reversal",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=119.0,
        )

    assert calls == []


def test_consumption_before_commander_continuation_fails_closed(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    object.__setattr__(
        consumption,
        "consumed_at",
        119.0,
    )

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    with pytest.raises(
        ValueError,
        match="consumption_precedes_commander_continuation",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )

    assert calls == []


def test_future_consumption_fails_before_d810c(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    object.__setattr__(
        consumption,
        "consumed_at",
        150.0,
    )

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    with pytest.raises(
        ValueError,
        match="consumption_timestamp_in_future_at_commander_handoff",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )

    assert calls == []


def test_expired_continuation_fails_before_d810c(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    with pytest.raises(
        ValueError,
        match="commander_continuation_expired_before_binding",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=200.0,
        )

    assert calls == []


@pytest.mark.parametrize(
    "field,value,match",
    [
        (
            "activation_id",
            "ACT-D819-OTHER",
            "commander_consumption_activation_id_continuity_mismatch",
        ),
        (
            "approval_id",
            "approval-d819-other",
            "commander_consumption_approval_id_continuity_mismatch",
        ),
        (
            "incident_id",
            "incident-d819-other",
            "commander_consumption_incident_id_continuity_mismatch",
        ),
        (
            "component_id",
            "systemd:d819-other.service",
            "commander_consumption_component_id_continuity_mismatch",
        ),
        (
            "execution_id",
            "execution-d819-other",
            "commander_consumption_execution_id_continuity_mismatch",
        ),
        (
            "effect_fingerprint",
            "e" * 64,
            "commander_consumption_effect_fingerprint_continuity_mismatch",
        ),
        (
            "grant_fingerprint",
            "0" * 64,
            "commander_consumption_grant_fingerprint_continuity_mismatch",
        ),
    ],
)
def test_consumption_to_grant_mismatch_fails_before_d810c(
    monkeypatch,
    field,
    value,
    match,
):
    continuation, grant, consumption = _fixture()

    object.__setattr__(
        consumption,
        field,
        value,
    )

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )

    assert calls == []


def test_upstream_continuation_is_revalidated(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    object.__setattr__(
        continuation,
        "incident_id",
        "incident-d819-wrong",
    )

    calls = []
    _install_canonical_fake(
        monkeypatch,
        calls,
    )

    with pytest.raises(
        ValueError,
        match="incident_binding_mismatch",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )

    assert calls == []


def test_noncanonical_returned_binding_rejected(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    monkeypatch.setattr(
        d819,
        "bind_consumed_activation_to_prepared_effect",
        lambda **kwargs: object(),
    )

    with pytest.raises(
        TypeError,
        match="canonical consumed activation binding",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )


@pytest.mark.parametrize(
    "field,value_factory,match",
    [
        (
            "grant",
            lambda grant, consumption, prepared: (
                SystemdProductionActivationGrant(
                    activation_id="ACT-D819-ALT",
                    approval_id=grant.approval_id,
                    incident_id=grant.incident_id,
                    component_id=grant.component_id,
                    execution_id=grant.execution_id,
                    effect_fingerprint=grant.effect_fingerprint,
                    issued_at=grant.issued_at,
                    expires_at=grant.expires_at,
                )
            ),
            "returned_binding_grant_identity_mismatch",
        ),
        (
            "consumption",
            lambda grant, consumption, prepared: (
                SystemdProductionActivationConsumptionRecord(
                    activation_id=consumption.activation_id,
                    approval_id=consumption.approval_id,
                    incident_id=consumption.incident_id,
                    component_id=consumption.component_id,
                    execution_id=consumption.execution_id,
                    effect_fingerprint=consumption.effect_fingerprint,
                    grant_fingerprint=consumption.grant_fingerprint,
                    consumed_at=consumption.consumed_at,
                )
            ),
            "returned_binding_consumption_identity_mismatch",
        ),
        (
            "prepared",
            lambda grant, consumption, prepared: (
                _exact_shell(
                    PreparedSystemdProductionRemediation,
                    binding=prepared.binding,
                    plan=prepared.plan,
                    prepared_at=prepared.prepared_at,
                )
            ),
            "returned_binding_prepared_identity_mismatch",
        ),
    ],
)
def test_returned_binding_identity_is_exact(
    monkeypatch,
    field,
    value_factory,
    match,
):
    continuation, grant, consumption = _fixture()

    def fake_bind(
        *,
        grant,
        consumption,
        prepared,
        now,
    ):
        values = dict(
            grant=grant,
            consumption=consumption,
            prepared=prepared,
            bound_at=now,
        )

        values[field] = value_factory(
            grant,
            consumption,
            prepared,
        )

        return _exact_shell(
            SystemdProductionConsumedActivationBinding,
            **values,
        )

    monkeypatch.setattr(
        d819,
        "bind_consumed_activation_to_prepared_effect",
        fake_bind,
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )


def test_returned_binding_timestamp_is_exact(
    monkeypatch,
):
    continuation, grant, consumption = _fixture()

    monkeypatch.setattr(
        d819,
        "bind_consumed_activation_to_prepared_effect",
        lambda **kwargs: _binding(
            kwargs["grant"],
            kwargs["consumption"],
            kwargs["prepared"],
            141.0,
        ),
    )

    with pytest.raises(
        ValueError,
        match="returned_binding_timestamp_mismatch",
    ):
        d819.bind_systemd_production_commander_consumption_to_prepared_effect(
            continuation=continuation,
            grant=grant,
            consumption=consumption,
            now=140.0,
        )
