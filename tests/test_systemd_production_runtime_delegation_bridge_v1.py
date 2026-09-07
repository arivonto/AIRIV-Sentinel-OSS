import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

import sentinel.systemd_production_runtime_delegation_bridge as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_runtime_delegation_bridge import (
    ProductionRuntimeDelegationState,
    SystemdProductionRuntimeDelegationBridge,
)


class FakePrepared:
    pass


class FakeIntegration:
    pass


class FakeDelegation:
    def __init__(
        self,
    ):
        self.calls = []

    def delegate_for_test(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return SimpleNamespace(
            result="fake-integration-result",
        )


class FakeInvocation:
    def __init__(
        self,
        *,
        ready=False,
        reason="runtime_invocation_blocked",
    ):
        self.ready = ready
        self.reason = reason
        self.calls = []

    def assess_explicit(
        self,
        *,
        prepared,
        now,
    ):
        self.calls.append(
            (
                prepared,
                now,
            )
        )

        decision = (
            SimpleNamespace(
                ready_for_policy=True,
            )
            if self.ready
            else None
        )

        return SimpleNamespace(
            ready_for_delegation=self.ready,
            reason=(
                "ready_for_explicit_canonical_delegation"
                if self.ready
                else self.reason
            ),
            dispatch_decision=decision,
        )


def install_fakes(
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "SystemdProductionRuntimeInvocationBoundary",
        FakeInvocation,
    )

    monkeypatch.setattr(
        module,
        "SystemdProductionExecutionDelegationBoundary",
        FakeDelegation,
    )

    monkeypatch.setattr(
        module,
        "SystemdCommanderIntegration",
        FakeIntegration,
    )

    monkeypatch.setattr(
        module,
        "PreparedSystemdProductionRemediation",
        FakePrepared,
    )


def test_default_bridge_is_disabled(
    monkeypatch,
):
    install_fakes(
        monkeypatch,
    )

    bridge = (
        SystemdProductionRuntimeDelegationBridge(
            invocation=FakeInvocation(),
        )
    )

    assert bridge.enabled is False


def test_disabled_bridge_does_not_call_any_downstream_boundary(
    monkeypatch,
):
    install_fakes(
        monkeypatch,
    )

    invocation = FakeInvocation(
        ready=True,
    )

    delegation = FakeDelegation()

    bridge = (
        SystemdProductionRuntimeDelegationBridge(
            invocation=invocation,
            enabled=False,
        )
    )

    result = bridge.invoke_explicit(
        delegation=delegation,
        integration=FakeIntegration(),
        prepared=FakePrepared(),
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: None,
        production_now=10.0,
    )

    assert (
        result.state
        is ProductionRuntimeDelegationState.BLOCKED
    )

    assert (
        result.reason
        == "production_runtime_delegation_disabled"
    )

    assert result.delegated is False
    assert result.invocation_assessment is None
    assert result.integration_result is None

    assert invocation.calls == []
    assert delegation.calls == []


def test_enabled_bridge_calls_invocation_once_and_stops_on_block(
    monkeypatch,
):
    install_fakes(
        monkeypatch,
    )

    invocation = FakeInvocation(
        ready=False,
        reason="runtime_invocation_disabled",
    )

    delegation = FakeDelegation()

    prepared = FakePrepared()

    bridge = (
        SystemdProductionRuntimeDelegationBridge(
            invocation=invocation,
            enabled=True,
        )
    )

    result = bridge.invoke_explicit(
        delegation=delegation,
        integration=FakeIntegration(),
        prepared=prepared,
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: None,
        production_now=20.0,
    )

    assert invocation.calls == [
        (
            prepared,
            20.0,
        )
    ]

    assert delegation.calls == []

    assert (
        result.state
        is ProductionRuntimeDelegationState.BLOCKED
    )

    assert result.delegated is False


def test_enabled_ready_path_delegates_exactly_once_to_fake(
    monkeypatch,
):
    install_fakes(
        monkeypatch,
    )

    invocation = FakeInvocation(
        ready=True,
    )

    delegation = FakeDelegation()
    integration = FakeIntegration()
    prepared = FakePrepared()
    provider = lambda: None

    bridge = (
        SystemdProductionRuntimeDelegationBridge(
            invocation=invocation,
            enabled=True,
        )
    )

    result = bridge.invoke_explicit(
        delegation=delegation,
        integration=integration,
        prepared=prepared,
        incident_state="INVESTIGATING",
        after_snapshot_provider=provider,
        production_now=30.0,
        timeout=4.0,
        production_attempts=("attempt",),
        active_production_effects=0,
    )

    assert len(invocation.calls) == 1
    assert len(delegation.calls) == 1

    call = delegation.calls[0]

    assert call["integration"] is integration
    assert call["prepared"] is prepared
    assert call["incident_state"] == "INVESTIGATING"
    assert call["after_snapshot_provider"] is provider
    assert call["production_now"] == 30.0
    assert call["timeout"] == 4.0
    assert call["production_attempts"] == ("attempt",)
    assert call["active_production_effects"] == 0

    assert (
        result.state
        is ProductionRuntimeDelegationState
        .DELEGATED_TO_CANONICAL_INTEGRATION
    )

    assert result.delegated is True

    assert (
        result.integration_result.result
        == "fake-integration-result"
    )


def test_runtime_owns_disabled_bridge_sharing_exact_invocation_surface():
    runtime = SentinelRuntime()

    bridge = (
        runtime
        .systemd_production_runtime_delegation_bridge
    )

    invocation = (
        runtime
        .systemd_production_runtime_invocation
    )

    gate = (
        runtime
        .systemd_production_execution_dispatch_gate
    )

    assert isinstance(
        bridge,
        SystemdProductionRuntimeDelegationBridge,
    )

    assert bridge.invocation is invocation

    assert bridge.enabled is False
    assert invocation.enabled is False
    assert gate.enabled is False

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_runtime_does_not_store_delegation_or_integration_on_bridge():
    runtime = SentinelRuntime()

    bridge = (
        runtime
        .systemd_production_runtime_delegation_bridge
    )

    assert not hasattr(
        bridge,
        "delegation",
    )

    assert not hasattr(
        bridge,
        "integration",
    )


def test_run_once_has_no_bridge_path():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "systemd_production_runtime_delegation_bridge"
        not in source
    )

    assert (
        "invoke_explicit"
        not in source
    )


def test_bridge_call_surface_has_one_invocation_and_one_delegation():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionRuntimeDelegationBridge
            .invoke_explicit
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
            "assess_explicit"
        )
        == 1
    )

    assert (
        calls.count(
            "delegate_for_test"
        )
        == 1
    )


def test_bridge_has_no_direct_canonical_authority_calls():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionRuntimeDelegationBridge
            .invoke_explicit
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
        "execute_verified",
        "execute_argv",
        "acquire",
        "verify",
        "resolve",
    ):
        assert prohibited not in calls


def test_invalid_types_fail_before_delegation(
    monkeypatch,
):
    install_fakes(
        monkeypatch,
    )

    bridge = (
        SystemdProductionRuntimeDelegationBridge(
            invocation=FakeInvocation(
                ready=True,
            ),
            enabled=True,
        )
    )

    delegation = FakeDelegation()

    with pytest.raises(
        TypeError,
        match="SystemdProductionExecutionDelegationBoundary required",
    ):
        bridge.invoke_explicit(
            delegation=object(),
            integration=FakeIntegration(),
            prepared=FakePrepared(),
            incident_state="INVESTIGATING",
            after_snapshot_provider=lambda: None,
            production_now=10.0,
        )

    assert delegation.calls == []


def test_module_has_no_host_primitives():
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
