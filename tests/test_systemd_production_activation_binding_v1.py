import ast
import dataclasses
import inspect
import textwrap
from types import SimpleNamespace

import pytest

import sentinel.systemd_production_activation_binding as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
    bind_consumed_activation_to_prepared_effect,
)


class FakeGrant:
    activation_id = "ACT-D810C"
    approval_id = "APPROVAL-D810C"

    incident_id = "INC-D810C"
    component_id = "systemd:example.service"
    execution_id = "EXEC-D810C"
    effect_fingerprint = "f" * 64

    issued_at = 100.0
    expires_at = 200.0

    fingerprint = "a" * 64

    def is_active(
        self,
        now,
    ):
        return (
            self.issued_at
            <= now
            < self.expires_at
        )


class FakeConsumption:
    activation_id = "ACT-D810C"
    approval_id = "APPROVAL-D810C"

    incident_id = "INC-D810C"
    component_id = "systemd:example.service"
    execution_id = "EXEC-D810C"
    effect_fingerprint = "f" * 64

    grant_fingerprint = "a" * 64
    consumed_at = 120.0


class FakePlan:
    def __init__(
        self,
    ):
        self.effect = SimpleNamespace(
            incident_id="INC-D810C",
            component_id="systemd:example.service",
            execution_id="EXEC-D810C",
            fingerprint="f" * 64,
        )


class FakeEvidenceBinding:
    def __init__(
        self,
        *,
        expires_at=190.0,
    ):
        self.expires_at = expires_at
        self.calls = []

    def is_fresh(
        self,
        now,
    ):
        self.calls.append(
            now
        )

        return now < self.expires_at


class FakePrepared:
    def __init__(
        self,
        *,
        evidence_expires_at=190.0,
    ):
        self.plan = FakePlan()

        self.binding = FakeEvidenceBinding(
            expires_at=evidence_expires_at
        )


def install_fakes(
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "SystemdProductionActivationGrant",
        FakeGrant,
    )

    monkeypatch.setattr(
        module,
        "SystemdProductionActivationConsumptionRecord",
        FakeConsumption,
    )

    monkeypatch.setattr(
        module,
        "PreparedSystemdProductionRemediation",
        FakePrepared,
    )

    monkeypatch.setattr(
        module,
        "BoundSystemdRemediationPlan",
        FakePlan,
    )

    monkeypatch.setattr(
        module,
        "TrustedSystemdDispatchEvidenceBinding",
        FakeEvidenceBinding,
    )


def bind(
    monkeypatch,
    *,
    grant=None,
    consumption=None,
    prepared=None,
    now=150.0,
):
    install_fakes(
        monkeypatch
    )

    return bind_consumed_activation_to_prepared_effect(
        grant=(
            FakeGrant()
            if grant is None
            else grant
        ),
        consumption=(
            FakeConsumption()
            if consumption is None
            else consumption
        ),
        prepared=(
            FakePrepared()
            if prepared is None
            else prepared
        ),
        now=now,
    )


def test_exact_continuity_binds(
    monkeypatch,
):
    result = bind(
        monkeypatch
    )

    assert isinstance(
        result,
        SystemdProductionConsumedActivationBinding,
    )

    assert result.activation_id == "ACT-D810C"
    assert result.approval_id == "APPROVAL-D810C"
    assert result.incident_id == "INC-D810C"

    assert (
        result.component_id
        == "systemd:example.service"
    )

    assert result.execution_id == "EXEC-D810C"
    assert result.effect_fingerprint == "f" * 64
    assert result.grant_fingerprint == "a" * 64
    assert result.bound_at == 150.0

    assert (
        result.prepared.binding.calls
        == [
            150.0,
        ]
    )


@pytest.mark.parametrize(
    (
        "field",
        "value",
        "reason",
    ),
    (
        (
            "activation_id",
            "ACT-OTHER",
            "activation_consumption_activation_id_mismatch",
        ),
        (
            "approval_id",
            "APPROVAL-OTHER",
            "activation_consumption_approval_id_mismatch",
        ),
        (
            "incident_id",
            "INC-OTHER",
            "activation_consumption_incident_id_mismatch",
        ),
        (
            "component_id",
            "systemd:other.service",
            "activation_consumption_component_id_mismatch",
        ),
        (
            "execution_id",
            "EXEC-OTHER",
            "activation_consumption_execution_id_mismatch",
        ),
        (
            "effect_fingerprint",
            "e" * 64,
            "activation_consumption_effect_fingerprint_mismatch",
        ),
        (
            "grant_fingerprint",
            "b" * 64,
            "activation_consumption_grant_fingerprint_mismatch",
        ),
    ),
)
def test_grant_consumption_substitution_fails_closed(
    monkeypatch,
    field,
    value,
    reason,
):
    install_fakes(
        monkeypatch
    )

    consumption = FakeConsumption()

    setattr(
        consumption,
        field,
        value,
    )

    with pytest.raises(
        ValueError,
        match=reason,
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=consumption,
            prepared=FakePrepared(),
            now=150.0,
        )


@pytest.mark.parametrize(
    (
        "field",
        "value",
        "reason",
    ),
    (
        (
            "incident_id",
            "INC-OTHER",
            "consumption_prepared_incident_id_mismatch",
        ),
        (
            "component_id",
            "systemd:other.service",
            "consumption_prepared_component_id_mismatch",
        ),
        (
            "execution_id",
            "EXEC-OTHER",
            "consumption_prepared_execution_id_mismatch",
        ),
        (
            "fingerprint",
            "e" * 64,
            "consumption_prepared_effect_fingerprint_mismatch",
        ),
    ),
)
def test_prepared_effect_substitution_fails_closed(
    monkeypatch,
    field,
    value,
    reason,
):
    install_fakes(
        monkeypatch
    )

    prepared = FakePrepared()

    setattr(
        prepared.plan.effect,
        field,
        value,
    )

    with pytest.raises(
        ValueError,
        match=reason,
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=FakeConsumption(),
            prepared=prepared,
            now=150.0,
        )


def test_expired_activation_cannot_bind(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="activation_not_active_at_prepared_binding",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=FakeConsumption(),
            prepared=FakePrepared(),
            now=200.0,
        )


@pytest.mark.parametrize(
    "consumed_at",
    (
        99.0,
        200.0,
        201.0,
    ),
)
def test_consumption_must_be_inside_activation_window(
    monkeypatch,
    consumed_at,
):
    install_fakes(
        monkeypatch
    )

    value = FakeConsumption()
    value.consumed_at = consumed_at

    with pytest.raises(
        ValueError,
        match="consumption_timestamp_outside_activation_window",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=value,
            prepared=FakePrepared(),
            now=150.0,
        )


def test_future_consumption_fails_closed(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    value = FakeConsumption()
    value.consumed_at = 170.0

    with pytest.raises(
        ValueError,
        match="consumption_timestamp_in_future",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=value,
            prepared=FakePrepared(),
            now=150.0,
        )


def test_stale_trusted_evidence_cannot_bind(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    prepared = FakePrepared(
        evidence_expires_at=140.0
    )

    with pytest.raises(
        ValueError,
        match="trusted_evidence_stale_at_activation_binding",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=FakeConsumption(),
            prepared=prepared,
            now=150.0,
        )

    assert (
        prepared.binding.calls
        == [
            150.0,
        ]
    )


def test_current_rechecks_both_activation_and_evidence(
    monkeypatch,
):
    result = bind(
        monkeypatch
    )

    assert result.is_current(
        160.0
    )

    assert not result.is_current(
        190.0
    )

    assert not result.is_current(
        200.0
    )

    assert not result.is_current(
        149.0
    )


def test_invalid_types_fail_closed(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    with pytest.raises(
        TypeError,
        match="SystemdProductionActivationGrant required",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=object(),
            consumption=FakeConsumption(),
            prepared=FakePrepared(),
            now=150.0,
        )

    with pytest.raises(
        TypeError,
        match="SystemdProductionActivationConsumptionRecord required",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=object(),
            prepared=FakePrepared(),
            now=150.0,
        )

    with pytest.raises(
        TypeError,
        match="PreparedSystemdProductionRemediation required",
    ):
        bind_consumed_activation_to_prepared_effect(
            grant=FakeGrant(),
            consumption=FakeConsumption(),
            prepared=object(),
            now=150.0,
        )


def test_runtime_has_no_d810c_binding_path():
    runtime = SentinelRuntime()

    assert not hasattr(
        runtime,
        "systemd_production_activation_binding",
    )

    assert (
        runtime
        .systemd_production_runtime_delegation_bridge
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_runtime_invocation
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_execution_dispatch_gate
        .enabled
        is False
    )

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_run_once_has_no_d810c_path():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "activation_binding"
        not in source
    )

    assert (
        "bind_consumed_activation"
        not in source
    )


def test_binding_has_no_persistence_or_downstream_authority():
    source = inspect.getsource(
        module
    )

    for token in (
        "SystemdProductionActivationConsumptionStore",
        "SystemdProductionRuntimeDelegationBridge",
        "SystemdProductionExecutionDelegationBoundary",
        "SystemdCommanderIntegration",
        "ExecutionBoundary",
        "IncidentManager",
        "FinalOutcomeMapper",
        "subprocess",
        "systemctl",
        "sudo",
        "pkexec",
        "systemd-run",
        "os.open",
        "os.fsync",
    ):
        assert token not in source


def test_post_init_call_surface_is_closed():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionConsumedActivationBinding
            .__post_init__
        )
    )

    tree = ast.parse(
        source
    )

    calls = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if isinstance(
            node.func,
            ast.Name,
        ):
            calls.append(
                node.func.id
            )

        elif isinstance(
            node.func,
            ast.Attribute,
        ):
            calls.append(
                node.func.attr
            )

    assert (
        calls.count(
            "is_active"
        )
        == 1
    )

    assert (
        calls.count(
            "is_fresh"
        )
        == 1
    )

    for prohibited in (
        "consume",
        "records",
        "append",
        "evaluate",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "production_runtime_guard",
        "invoke_explicit",
        "delegate_for_test",
        "execute",
        "execute_verified",
        "execute_argv",
        "acquire",
        "verify",
        "resolve",
    ):
        assert prohibited not in calls
