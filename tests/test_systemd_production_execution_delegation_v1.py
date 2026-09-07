import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

import sentinel.systemd_production_execution_delegation as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_execution_delegation import (
    SystemdProductionExecutionDelegationBoundary,
)
from sentinel.systemd_production_execution_dispatch_gate import (
    ProductionExecutionDispatchState,
)


class FakeBinding:
    def __init__(
        self,
        *,
        fresh=True,
    ):
        self.fresh = fresh

    def is_fresh(
        self,
        now,
    ):
        return self.fresh


class FakePermitBinding:
    def __init__(
        self,
        matches=True,
    ):
        self.value = matches

    def matches(
        self,
        effect,
    ):
        return self.value


class FakePlan:
    def __init__(
        self,
    ):
        self.effect = SimpleNamespace(
            incident_id="INC-D89B",
            component_id="systemd:example.service",
            execution_id="EXEC-D89B",
            fingerprint="effect-fingerprint-d89b",
        )

        self.permit_binding = (
            FakePermitBinding()
        )


class FakePrepared:
    def __init__(
        self,
        *,
        fresh=True,
    ):
        self.binding = FakeBinding(
            fresh=fresh,
        )

        self.plan = FakePlan()


class FakeDecision:
    def __init__(
        self,
        *,
        ready=True,
    ):
        self.state = (
            ProductionExecutionDispatchState.READY_FOR_POLICY
            if ready
            else ProductionExecutionDispatchState.BLOCKED
        )

        self.ready_for_policy = ready
        self.incident_id = "INC-D89B"
        self.component_id = "systemd:example.service"
        self.execution_id = "EXEC-D89B"
        self.effect_fingerprint = "effect-fingerprint-d89b"


class FakeIntegration:
    def __init__(
        self,
    ):
        self.calls = []

    def execute_verified(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return SimpleNamespace(
            result="delegated",
        )


def install_types(
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "SystemdCommanderIntegration",
        FakeIntegration,
    )

    monkeypatch.setattr(
        module,
        "ProductionExecutionDispatchDecision",
        FakeDecision,
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


def test_ready_decision_delegates_exactly_once(
    monkeypatch,
):
    install_types(
        monkeypatch,
    )

    integration = FakeIntegration()
    decision = FakeDecision()
    prepared = FakePrepared()

    provider = lambda: None

    result = (
        SystemdProductionExecutionDelegationBoundary()
        .delegate_for_test(
            integration=integration,
            decision=decision,
            prepared=prepared,
            incident_state="INVESTIGATING",
            after_snapshot_provider=provider,
            production_now=50.0,
            timeout=4.0,
            production_attempts=("attempt",),
            active_production_effects=0,
        )
    )

    assert result.result == "delegated"
    assert len(integration.calls) == 1

    call = integration.calls[0]

    assert call["plan"] is prepared.plan
    assert call["incident_state"] == "INVESTIGATING"
    assert call["after_snapshot_provider"] is provider
    assert call["production_now"] == 50.0
    assert call["timeout"] == 4.0
    assert call["production_attempts"] == ("attempt",)
    assert call["active_production_effects"] == 0


def test_blocked_decision_never_delegates(
    monkeypatch,
):
    install_types(
        monkeypatch,
    )

    integration = FakeIntegration()

    with pytest.raises(
        ValueError,
        match="production_dispatch_not_ready_for_policy",
    ):
        (
            SystemdProductionExecutionDelegationBoundary()
            .delegate_for_test(
                integration=integration,
                decision=FakeDecision(
                    ready=False,
                ),
                prepared=FakePrepared(),
                incident_state="INVESTIGATING",
                after_snapshot_provider=lambda: None,
                production_now=50.0,
            )
        )

    assert integration.calls == []


def test_stale_binding_never_delegates(
    monkeypatch,
):
    install_types(
        monkeypatch,
    )

    integration = FakeIntegration()

    with pytest.raises(
        ValueError,
        match="trusted_evidence_stale_at_execution_delegation",
    ):
        (
            SystemdProductionExecutionDelegationBoundary()
            .delegate_for_test(
                integration=integration,
                decision=FakeDecision(),
                prepared=FakePrepared(
                    fresh=False,
                ),
                incident_state="INVESTIGATING",
                after_snapshot_provider=lambda: None,
                production_now=50.0,
            )
        )

    assert integration.calls == []


@pytest.mark.parametrize(
    (
        "field",
        "value",
        "error",
    ),
    (
        (
            "incident_id",
            "INC-OTHER",
            "dispatch_incident_id_mismatch",
        ),
        (
            "component_id",
            "systemd:other.service",
            "dispatch_component_id_mismatch",
        ),
        (
            "execution_id",
            "EXEC-OTHER",
            "dispatch_execution_id_mismatch",
        ),
        (
            "effect_fingerprint",
            "other-fingerprint",
            "dispatch_effect_fingerprint_mismatch",
        ),
    ),
)
def test_decision_identity_substitution_never_delegates(
    monkeypatch,
    field,
    value,
    error,
):
    install_types(
        monkeypatch,
    )

    integration = FakeIntegration()
    decision = FakeDecision()

    setattr(
        decision,
        field,
        value,
    )

    with pytest.raises(
        ValueError,
        match=error,
    ):
        (
            SystemdProductionExecutionDelegationBoundary()
            .delegate_for_test(
                integration=integration,
                decision=decision,
                prepared=FakePrepared(),
                incident_state="INVESTIGATING",
                after_snapshot_provider=lambda: None,
                production_now=50.0,
            )
        )

    assert integration.calls == []


def test_permit_binding_mismatch_never_delegates(
    monkeypatch,
):
    install_types(
        monkeypatch,
    )

    integration = FakeIntegration()
    prepared = FakePrepared()

    prepared.plan.permit_binding = (
        FakePermitBinding(
            matches=False,
        )
    )

    with pytest.raises(
        ValueError,
        match="prepared_permit_binding_mismatch",
    ):
        (
            SystemdProductionExecutionDelegationBoundary()
            .delegate_for_test(
                integration=integration,
                decision=FakeDecision(),
                prepared=prepared,
                incident_state="INVESTIGATING",
                after_snapshot_provider=lambda: None,
                production_now=50.0,
            )
        )

    assert integration.calls == []


def test_runtime_does_not_own_delegation_boundary():
    runtime = SentinelRuntime()

    assert not hasattr(
        runtime,
        "systemd_production_execution_delegation",
    )

    assert (
        runtime
        .systemd_production_execution_dispatch_gate
        .enabled
        is False
    )


def test_runtime_paths_do_not_reference_delegation():
    init_source = inspect.getsource(
        SentinelRuntime.__init__
    )

    run_once_source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "SystemdProductionExecutionDelegationBoundary"
        not in init_source
    )

    assert (
        "SystemdProductionExecutionDelegationBoundary"
        not in run_once_source
    )

    assert (
        "delegate_for_test"
        not in run_once_source
    )


def test_delegation_call_surface_has_exactly_one_execute_verified():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionExecutionDelegationBoundary
            .delegate_for_test
        )
    )

    tree = ast.parse(
        source
    )

    calls = []

    for node in ast.walk(tree):
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
            "execute_verified"
        )
        == 1
    )

    assert (
        calls.count(
            "is_fresh"
        )
        == 1
    )

    assert (
        calls.count(
            "matches"
        )
        == 1
    )


def test_no_duplicate_downstream_authority_calls():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionExecutionDelegationBoundary
            .delegate_for_test
        )
    )

    tree = ast.parse(
        source
    )

    calls = set()

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if isinstance(
            node.func,
            ast.Name,
        ):
            calls.add(
                node.func.id
            )

        elif isinstance(
            node.func,
            ast.Attribute,
        ):
            calls.add(
                node.func.attr
            )

    for prohibited in (
        "evaluate",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "production_runtime_guard",
        "execute",
        "execute_argv",
        "acquire",
        "verify",
        "resolve",
    ):
        assert prohibited not in calls


def test_module_has_no_host_execution_primitive():
    source = inspect.getsource(
        module
    )

    for token in (
        "subprocess",
        "systemctl",
        "sudo",
        "pkexec",
        "systemd-run",
        "ExecutionBoundary",
        "IncidentManager",
        "FinalOutcomeMapper",
    ):
        assert token not in source
