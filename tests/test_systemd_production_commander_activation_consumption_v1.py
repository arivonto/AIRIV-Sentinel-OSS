from types import SimpleNamespace

import pytest

from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionRecord,
    SystemdProductionActivationConsumptionStore,
)
from sentinel.systemd_production_approval_issuance import (
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_commander_activation_consumption import (
    consume_systemd_production_activation_from_commander_continuation,
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


def _fixture():
    binding = _exact_shell(
        TrustedSystemdDispatchEvidenceBinding,
    )

    permit = SimpleNamespace(
        incident_id="incident-d818",
        component_id="systemd:d818-test.service",
        execution_id="execution-d818",
        effect_fingerprint="fingerprint-d818",
    )

    effect = SimpleNamespace(
        incident_id="incident-d818",
        component_id="systemd:d818-test.service",
        action=ACTION_RESTART,
        execution_id="execution-d818",
        effect_fingerprint="fingerprint-d818",
    )

    plan = SimpleNamespace(
        effect=effect,
        permit_binding=permit,
    )

    prepared = _exact_shell(
        PreparedSystemdProductionRemediation,
        binding=binding,
        plan=plan,
        prepared_at=110.0,
    )

    approval = _exact_shell(
        TrustedSystemdProductionCommanderApproval,
        approval_id="approval-d818",
        effect=permit,
        issued_at=100.0,
        expires_at=200.0,
    )

    continuation = (
        SystemdProductionCommanderIncidentContinuation(
            incident_id="incident-d818",
            component_id="systemd:d818-test.service",
            action=ACTION_RESTART,
            execution_id="execution-d818",
            approval_id="approval-d818",
            continued_at=120.0,
            approval_expires_at=200.0,
            binding=binding,
            prepared=prepared,
            approval=approval,
        )
    )

    grant = SystemdProductionActivationGrant(
        activation_id="activation-d818",
        approval_id="approval-d818",
        incident_id="incident-d818",
        component_id="systemd:d818-test.service",
        execution_id="execution-d818",
        effect_fingerprint="fingerprint-d818",
        issued_at=100.0,
        expires_at=200.0,
    )

    store = object.__new__(
        SystemdProductionActivationConsumptionStore
    )

    return continuation, grant, store


def _record(
    grant,
    consumed_at=130.0,
    **changes,
):
    values = dict(
        activation_id=grant.activation_id,
        approval_id=grant.approval_id,
        incident_id=grant.incident_id,
        component_id=grant.component_id,
        execution_id=grant.execution_id,
        effect_fingerprint=grant.effect_fingerprint,
        grant_fingerprint=grant.fingerprint,
        consumed_at=consumed_at,
    )

    values.update(changes)

    return SystemdProductionActivationConsumptionRecord(
        **values
    )


def test_delegates_exactly_once_to_d810b(
    monkeypatch,
):
    continuation, grant, store = _fixture()

    calls = []

    def fake_consume(
        self,
        *,
        grant,
        now,
        incident_id,
        component_id,
        execution_id,
        effect_fingerprint,
    ):
        calls.append(
            dict(
                self=self,
                grant=grant,
                now=now,
                incident_id=incident_id,
                component_id=component_id,
                execution_id=execution_id,
                effect_fingerprint=effect_fingerprint,
            )
        )

        return _record(
            grant,
            consumed_at=now,
        )

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        fake_consume,
    )

    record = (
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=130.0,
        )
    )

    assert (
        type(record)
        is SystemdProductionActivationConsumptionRecord
    )

    assert len(calls) == 1

    call = calls[0]

    assert call["self"] is store
    assert call["grant"] is grant
    assert call["now"] == 130.0
    assert call["incident_id"] == continuation.incident_id
    assert call["component_id"] == continuation.component_id
    assert call["execution_id"] == continuation.execution_id
    assert (
        call["effect_fingerprint"]
        == grant.effect_fingerprint
    )


def test_continuation_type_is_exact(
    monkeypatch,
):
    _, grant, store = _fixture()

    with pytest.raises(
        TypeError,
        match="canonical Commander incident continuation",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=object(),
            grant=grant,
            consumption_store=store,
            now=130.0,
        )


def test_grant_type_is_exact():
    continuation, _, store = _fixture()

    with pytest.raises(
        TypeError,
        match="canonical activation grant",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=object(),
            consumption_store=store,
            now=130.0,
        )


def test_store_type_is_exact():
    continuation, grant, _ = _fixture()

    with pytest.raises(
        TypeError,
        match="canonical activation consumption store",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=object(),
            now=130.0,
        )


def test_time_reversal_denied_before_consumption(
    monkeypatch,
):
    continuation, grant, store = _fixture()

    called = False

    def fake_consume(self, **kwargs):
        nonlocal called
        called = True
        return _record(
            kwargs["grant"],
            consumed_at=kwargs["now"],
        )

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        fake_consume,
    )

    with pytest.raises(
        ValueError,
        match="activation_consumption_time_reversal",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=119.0,
        )

    assert called is False


def test_expired_continuation_denied_before_consumption(
    monkeypatch,
):
    continuation, grant, store = _fixture()

    called = False

    def fake_consume(self, **kwargs):
        nonlocal called
        called = True
        return _record(
            kwargs["grant"],
            consumed_at=kwargs["now"],
        )

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        fake_consume,
    )

    with pytest.raises(
        ValueError,
        match="commander_continuation_expired_before_consumption",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=200.0,
        )

    assert called is False


def test_upstream_continuation_is_revalidated_before_consumption(
    monkeypatch,
):
    continuation, grant, store = _fixture()

    object.__setattr__(
        continuation,
        "incident_id",
        "wrong-incident",
    )

    called = False

    def fake_consume(self, **kwargs):
        nonlocal called
        called = True
        return _record(
            kwargs["grant"],
            consumed_at=kwargs["now"],
        )

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        fake_consume,
    )

    with pytest.raises(
        ValueError,
        match="incident_binding_mismatch",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=130.0,
        )

    assert called is False


@pytest.mark.parametrize(
    "field,value,match",
    [
        (
            "approval_id",
            "wrong-approval",
            "approval_id_continuity_mismatch",
        ),
        (
            "incident_id",
            "wrong-incident",
            "activation_effect_continuity_mismatch",
        ),
        (
            "component_id",
            "systemd:wrong.service",
            "activation_effect_continuity_mismatch",
        ),
        (
            "execution_id",
            "wrong-execution",
            "activation_effect_continuity_mismatch",
        ),
        (
            "effect_fingerprint",
            "wrong-fingerprint",
            "activation_effect_continuity_mismatch",
        ),
    ],
)
def test_grant_mismatch_denied_before_consumption(
    monkeypatch,
    field,
    value,
    match,
):
    continuation, grant, store = _fixture()

    object.__setattr__(
        grant,
        field,
        value,
    )

    called = False

    def fake_consume(self, **kwargs):
        nonlocal called
        called = True
        return _record(
            kwargs["grant"],
            consumed_at=kwargs["now"],
        )

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        fake_consume,
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=130.0,
        )

    assert called is False


def test_noncanonical_record_rejected(
    monkeypatch,
):
    continuation, grant, store = _fixture()

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        lambda self, **kwargs: object(),
    )

    with pytest.raises(
        TypeError,
        match="canonical activation consumption record",
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=130.0,
        )


@pytest.mark.parametrize(
    "changes,match",
    [
        (
            dict(
                activation_id="different-activation",
            ),
            "consumption_activation_id_continuity_mismatch",
        ),
        (
            dict(
                approval_id="different-approval",
            ),
            "consumption_approval_id_continuity_mismatch",
        ),
        (
            dict(
                incident_id="different-incident",
            ),
            "consumption_incident_id_continuity_mismatch",
        ),
        (
            dict(
                component_id="systemd:different.service",
            ),
            "consumption_component_id_continuity_mismatch",
        ),
        (
            dict(
                execution_id="different-execution",
            ),
            "consumption_execution_id_continuity_mismatch",
        ),
        (
            dict(
                effect_fingerprint="different-fingerprint",
            ),
            "consumption_effect_fingerprint_continuity_mismatch",
        ),
        (
            dict(
                grant_fingerprint="0" * 64,
            ),
            "consumption_grant_fingerprint_continuity_mismatch",
        ),
        (
            dict(
                consumed_at=131.0,
            ),
            "consumption_timestamp_continuity_mismatch",
        ),
    ],
)
def test_returned_record_continuity_revalidated(
    monkeypatch,
    changes,
    match,
):
    continuation, grant, store = _fixture()

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        
lambda self, **kwargs: _record(
            kwargs["grant"],
            **(
                {"consumed_at": kwargs["now"]}
                | changes
            ),
        ),

    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        consume_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            grant=grant,
            consumption_store=store,
            now=130.0,
        )


def test_no_incident_or_continuation_mutation(
    monkeypatch,
):
    continuation, grant, store = _fixture()

    before = (
        continuation.incident_id,
        continuation.component_id,
        continuation.execution_id,
        continuation.approval_id,
        grant.activation_id,
        grant.approval_id,
    )

    monkeypatch.setattr(
        SystemdProductionActivationConsumptionStore,
        "consume",
        lambda self, **kwargs: _record(
            kwargs["grant"],
            consumed_at=kwargs["now"],
        ),
    )

    consume_systemd_production_activation_from_commander_continuation(
        continuation=continuation,
        grant=grant,
        consumption_store=store,
        now=130.0,
    )

    after = (
        continuation.incident_id,
        continuation.component_id,
        continuation.execution_id,
        continuation.approval_id,
        grant.activation_id,
        grant.approval_id,
    )

    assert after == before
