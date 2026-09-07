from types import SimpleNamespace

import pytest

import sentinel.systemd_production_commander_authorization_handoff as d820

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
    SystemdProductionActivationConsumptionStore,
)
from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer,
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


def _fixture():
    evidence = _exact_shell(
        TrustedSystemdDispatchEvidenceBinding,
    )

    permit = SimpleNamespace(
        incident_id="incident-d820",
        component_id="systemd:d820-test.service",
        execution_id="execution-d820",
        effect_fingerprint="f" * 64,
    )

    effect = SimpleNamespace(
        incident_id="incident-d820",
        component_id="systemd:d820-test.service",
        action=ACTION_RESTART,
        execution_id="execution-d820",
        effect_fingerprint="f" * 64,
    )

    plan = SimpleNamespace(
        effect=effect,
        permit_binding=permit,
    )

    prepared = _exact_shell(
        PreparedSystemdProductionRemediation,
        binding=evidence,
        plan=plan,
        prepared_at=110.0,
    )

    approval = _exact_shell(
        TrustedSystemdProductionCommanderApproval,
        approval_id="approval-d820",
        effect=permit,
        issued_at=100.0,
        expires_at=200.0,
    )

    continuation = (
        SystemdProductionCommanderIncidentContinuation(
            incident_id="incident-d820",
            component_id="systemd:d820-test.service",
            action=ACTION_RESTART,
            execution_id="execution-d820",
            approval_id="approval-d820",
            continued_at=120.0,
            approval_expires_at=200.0,
            binding=evidence,
            prepared=prepared,
            approval=approval,
        )
    )

    grant = SystemdProductionActivationGrant(
        activation_id="ACT-D820",
        approval_id="approval-d820",
        incident_id="incident-d820",
        component_id="systemd:d820-test.service",
        execution_id="execution-d820",
        effect_fingerprint="f" * 64,
        issued_at=100.0,
        expires_at=200.0,
    )

    consumption = (
        SystemdProductionActivationConsumptionRecord(
            activation_id=grant.activation_id,
            approval_id=grant.approval_id,
            incident_id=grant.incident_id,
            component_id=grant.component_id,
            execution_id=grant.execution_id,
            effect_fingerprint=grant.effect_fingerprint,
            grant_fingerprint=grant.fingerprint,
            consumed_at=130.0,
        )
    )

    binding = _exact_shell(
        SystemdProductionConsumedActivationBinding,
        grant=grant,
        consumption=consumption,
        prepared=prepared,
        bound_at=140.0,
    )

    issuer = object.__new__(
        SystemdProductionCommanderApprovalIssuer
    )

    store = object.__new__(
        SystemdProductionActivationConsumptionStore
    )

    return (
        continuation,
        binding,
        issuer,
        store,
    )


class _FakeContext:
    calls = []

    def __init__(
        self,
        *,
        binding,
        issuer,
        consumption_store,
    ):
        type(self).calls.append(
            dict(
                binding=binding,
                issuer=issuer,
                consumption_store=consumption_store,
            )
        )

        self.binding = binding

        grant = binding.grant

        self.approval = SimpleNamespace(
            approval_id=grant.approval_id,
            effect=binding.prepared.plan.permit_binding,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
        )


def _install_context_fake(monkeypatch):
    _FakeContext.calls = []

    monkeypatch.setattr(
        d820,
        "SystemdProductionCommanderAuthorizationContext",
        _FakeContext,
    )


def test_delegates_exactly_once_to_d815_context(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    _install_context_fake(
        monkeypatch
    )

    context = (
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )
    )

    assert type(context) is _FakeContext
    assert len(_FakeContext.calls) == 1

    call = _FakeContext.calls[0]

    assert call["binding"] is binding
    assert call["issuer"] is issuer
    assert call["consumption_store"] is store


@pytest.mark.parametrize(
    "field,value,match",
    [
        (
            "continuation",
            object(),
            "canonical Commander incident continuation",
        ),
        (
            "binding",
            object(),
            "canonical consumed activation binding",
        ),
        (
            "issuer",
            object(),
            "canonical approval issuer",
        ),
        (
            "consumption_store",
            object(),
            "canonical consumption store",
        ),
    ],
)
def test_exact_input_types_required(
    monkeypatch,
    field,
    value,
    match,
):
    continuation, binding, issuer, store = _fixture()

    args = dict(
        continuation=continuation,
        binding=binding,
        issuer=issuer,
        consumption_store=store,
    )

    args[field] = value

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        TypeError,
        match=match,
    ):
        d820.build_systemd_production_commander_authorization_context(
            **args
        )

    assert _FakeContext.calls == []


def test_d816_continuation_revalidated_before_context(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        continuation,
        "incident_id",
        "wrong-incident",
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="incident_binding_mismatch",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


def test_prepared_identity_mismatch_denied_before_context(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        binding,
        "prepared",
        object(),
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="commander_authorization_prepared_identity_mismatch",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


@pytest.mark.parametrize(
    "field,value,match",
    [
        (
            "approval_id",
            "other-approval",
            "commander_authorization_approval_id_mismatch",
        ),
        (
            "incident_id",
            "other-incident",
            "commander_authorization_incident_id_mismatch",
        ),
        (
            "component_id",
            "systemd:other.service",
            "commander_authorization_component_id_mismatch",
        ),
        (
            "execution_id",
            "other-execution",
            "commander_authorization_execution_id_mismatch",
        ),
    ],
)
def test_binding_continuity_mismatch_denied_before_context(
    monkeypatch,
    field,
    value,
    match,
):
    continuation, binding, issuer, store = _fixture()

    if field == "approval_id":
        object.__setattr__(
            binding.grant,
            "approval_id",
            value,
        )
    else:
        object.__setattr__(
            binding.consumption,
            field,
            value,
        )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


def test_consumption_before_continuation_denied(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        binding.consumption,
        "consumed_at",
        119.0,
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="commander_authorization_consumption_precedes_continuation",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


def test_consumption_after_binding_denied(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        binding.consumption,
        "consumed_at",
        141.0,
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="commander_authorization_consumption_after_binding",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


def test_binding_before_continuation_denied(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        binding,
        "bound_at",
        119.0,
    )

    object.__setattr__(
        binding.consumption,
        "consumed_at",
        119.0,
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="commander_authorization_consumption_precedes_continuation",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


def test_binding_at_or_after_expiry_denied(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        binding,
        "bound_at",
        200.0,
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="commander_authorization_binding_after_approval_expiry",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


@pytest.mark.parametrize(
    "field,value,match",
    [
        (
            "approval_id",
            "other-approval",
            "commander_authorization_approval_id_mismatch",
        ),
        (
            "issued_at",
            101.0,
            "commander_authorization_grant_issued_at_mismatch",
        ),
        (
            "expires_at",
            199.0,
            "commander_authorization_grant_expiry_mismatch",
        ),
    ],
)
def test_grant_to_commander_approval_mismatch_denied(
    monkeypatch,
    field,
    value,
    match,
):
    continuation, binding, issuer, store = _fixture()

    object.__setattr__(
        binding.grant,
        field,
        value,
    )

    _install_context_fake(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )

    assert _FakeContext.calls == []


def test_noncanonical_returned_context_rejected(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    monkeypatch.setattr(
        d820,
        "SystemdProductionCommanderAuthorizationContext",
        lambda **kwargs: object(),
    )

    with pytest.raises(
        TypeError,
        match="canonical Commander authorization context",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )


def test_returned_binding_identity_is_exact(
    monkeypatch,
):
    continuation, binding, issuer, store = _fixture()

    class WrongBindingContext(_FakeContext):
        def __init__(
            self,
            *,
            binding,
            issuer,
            consumption_store,
        ):
            super().__init__(
                binding=binding,
                issuer=issuer,
                consumption_store=consumption_store,
            )
            self.binding = object()

    WrongBindingContext.calls = []

    monkeypatch.setattr(
        d820,
        "SystemdProductionCommanderAuthorizationContext",
        WrongBindingContext,
    )

    with pytest.raises(
        ValueError,
        match="returned_commander_authorization_binding_identity_mismatch",
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )


@pytest.mark.parametrize(
    "field,value,match",
    [
        (
            "approval_id",
            "wrong",
            "returned_commander_authorization_approval_id_mismatch",
        ),
        (
            "effect",
            object(),
            "returned_commander_authorization_effect_mismatch",
        ),
        (
            "issued_at",
            101.0,
            "returned_commander_authorization_issued_at_mismatch",
        ),
        (
            "expires_at",
            201.0,
            "returned_commander_authorization_expiry_mismatch",
        ),
    ],
)
def test_returned_approval_continuity_is_exact(
    monkeypatch,
    field,
    value,
    match,
):
    continuation, binding, issuer, store = _fixture()

    class WrongApprovalContext(_FakeContext):
        def __init__(
            self,
            *,
            binding,
            issuer,
            consumption_store,
        ):
            super().__init__(
                binding=binding,
                issuer=issuer,
                consumption_store=consumption_store,
            )

            setattr(
                self.approval,
                field,
                value,
            )

    WrongApprovalContext.calls = []

    monkeypatch.setattr(
        d820,
        "SystemdProductionCommanderAuthorizationContext",
        WrongApprovalContext,
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        d820.build_systemd_production_commander_authorization_context(
            continuation=continuation,
            binding=binding,
            issuer=issuer,
            consumption_store=store,
        )
