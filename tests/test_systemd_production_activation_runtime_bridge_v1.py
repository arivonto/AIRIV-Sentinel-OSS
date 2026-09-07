import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

import sentinel.systemd_production_activation_runtime_bridge as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_activation_runtime_bridge import (
    ProductionActivationRuntimeState,
    SystemdProductionActivationRuntimeBridge,
)


class FakeActivationBinding:
    def __init__(
        self,
        *,
        current=True,
    ):
        self.current = current
        self.current_calls = []

        self.activation_id = (
            "ACT-D810D"
        )

        self.approval_id = (
            "APPROVAL-D810D"
        )

        self.prepared = object()

    def is_current(
        self,
        now,
    ):
        self.current_calls.append(
            now
        )

        return self.current


class FakeDelegation:
    pass


class FakeIntegration:
    pass


class FakeRuntimeBridge:
    def __init__(
        self,
    ):
        self.calls = []

    def invoke_explicit(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return SimpleNamespace(
            delegated=True,
            reason="fake-runtime-delegation",
        )


def install_fakes(
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "SystemdProductionConsumedActivationBinding",
        FakeActivationBinding,
    )

    monkeypatch.setattr(
        module,
        "SystemdProductionRuntimeDelegationBridge",
        FakeRuntimeBridge,
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


def test_default_bridge_disabled(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    boundary = (
        SystemdProductionActivationRuntimeBridge(
            runtime_bridge=FakeRuntimeBridge(),
        )
    )

    assert boundary.enabled is False


def test_disabled_bridge_touches_nothing_downstream(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    binding = FakeActivationBinding(
        current=True
    )

    downstream = FakeRuntimeBridge()

    boundary = (
        SystemdProductionActivationRuntimeBridge(
            runtime_bridge=downstream,
            enabled=False,
        )
    )

    result = boundary.invoke_explicit(
        activation_binding=binding,
        delegation=FakeDelegation(),
        integration=FakeIntegration(),
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: None,
        production_now=150.0,
    )

    assert (
        result.state
        is ProductionActivationRuntimeState.BLOCKED
    )

    assert (
        result.reason
        == "production_activation_runtime_bridge_disabled"
    )

    assert result.delegated is False
    assert binding.current_calls == []
    assert downstream.calls == []


def test_enabled_stale_binding_blocks_before_runtime_bridge(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    binding = FakeActivationBinding(
        current=False
    )

    downstream = FakeRuntimeBridge()

    boundary = (
        SystemdProductionActivationRuntimeBridge(
            runtime_bridge=downstream,
            enabled=True,
        )
    )

    result = boundary.invoke_explicit(
        activation_binding=binding,
        delegation=FakeDelegation(),
        integration=FakeIntegration(),
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: None,
        production_now=150.0,
    )

    assert binding.current_calls == [
        150.0,
    ]

    assert downstream.calls == []

    assert (
        result.state
        is ProductionActivationRuntimeState.BLOCKED
    )

    assert (
        result.reason
        == "consumed_activation_binding_not_current"
    )

    assert result.delegated is False


def test_enabled_current_binding_routes_once_to_fake_d89d(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    binding = FakeActivationBinding(
        current=True
    )

    downstream = FakeRuntimeBridge()
    delegation = FakeDelegation()
    integration = FakeIntegration()
    provider = lambda: None

    boundary = (
        SystemdProductionActivationRuntimeBridge(
            runtime_bridge=downstream,
            enabled=True,
        )
    )

    result = boundary.invoke_explicit(
        activation_binding=binding,
        delegation=delegation,
        integration=integration,
        incident_state="INVESTIGATING",
        after_snapshot_provider=provider,
        production_now=150.0,
        timeout=4.0,
        production_attempts=("attempt",),
        active_production_effects=0,
    )

    assert binding.current_calls == [
        150.0,
    ]

    assert len(
        downstream.calls
    ) == 1

    call = downstream.calls[0]

    assert (
        call["prepared"]
        is binding.prepared
    )

    assert (
        call["delegation"]
        is delegation
    )

    assert (
        call["integration"]
        is integration
    )

    assert (
        call["after_snapshot_provider"]
        is provider
    )

    assert call["production_now"] == 150.0
    assert call["timeout"] == 4.0

    assert (
        call["production_attempts"]
        == ("attempt",)
    )

    assert (
        call["active_production_effects"]
        == 0
    )

    assert (
        result.state
        is ProductionActivationRuntimeState
        .DELEGATED_TO_RUNTIME_BRIDGE
    )

    assert result.delegated is True

    assert result.activation_id == "ACT-D810D"

    assert (
        result.approval_id
        == "APPROVAL-D810D"
    )


def test_no_second_prepared_argument_exists():
    signature = inspect.signature(
        SystemdProductionActivationRuntimeBridge
        .invoke_explicit
    )

    assert (
        "prepared"
        not in signature.parameters
    )

    assert (
        "activation_binding"
        in signature.parameters
    )


def test_runtime_owns_fourth_disabled_layer():
    runtime = SentinelRuntime()

    activation = (
        runtime
        .systemd_production_activation_runtime_bridge
    )

    bridge = (
        runtime
        .systemd_production_runtime_delegation_bridge
    )

    surface = (
        runtime
        .systemd_production_runtime_invocation
    )

    gate = (
        runtime
        .systemd_production_execution_dispatch_gate
    )

    assert isinstance(
        activation,
        SystemdProductionActivationRuntimeBridge,
    )

    assert (
        activation.runtime_bridge
        is bridge
    )

    assert activation.enabled is False
    assert bridge.enabled is False
    assert surface.enabled is False
    assert gate.enabled is False

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_runtime_owns_no_activation_grant_or_store():
    runtime = SentinelRuntime()

    assert not hasattr(
        runtime,
        "systemd_production_activation_grant",
    )

    assert not hasattr(
        runtime,
        "systemd_production_activation_consumption",
    )


def test_run_once_has_no_d810d_path():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "systemd_production_activation_runtime_bridge"
        not in source
    )

    assert (
        "invoke_explicit"
        not in source
    )


def test_call_surface_has_one_current_check_and_one_d89d_call():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionActivationRuntimeBridge
            .invoke_explicit
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
            "is_current"
        )
        == 1
    )

    assert (
        calls.count(
            "invoke_explicit"
        )
        == 1
    )


def test_no_direct_lower_authority():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionActivationRuntimeBridge
            .invoke_explicit
        )
    )

    tree = ast.parse(
        source
    )

    calls = set()

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
        "consume",
        "records",
        "append",
        "evaluate",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "production_runtime_guard",
        "delegate_for_test",
        "execute",
        "execute_verified",
        "execute_argv",
        "acquire",
        "verify",
        "resolve",
    ):
        assert prohibited not in calls


def test_module_has_no_host_or_persistence_primitives():
    source = inspect.getsource(
        module
    )

    for token in (
        "SystemdProductionActivationConsumptionStore",
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
        "write_text",
    ):
        assert token not in source


def test_invalid_binding_type_fails_before_downstream(
    monkeypatch,
):
    install_fakes(
        monkeypatch
    )

    downstream = FakeRuntimeBridge()

    boundary = (
        SystemdProductionActivationRuntimeBridge(
            runtime_bridge=downstream,
            enabled=True,
        )
    )

    with pytest.raises(
        TypeError,
        match="SystemdProductionConsumedActivationBinding required",
    ):
        boundary.invoke_explicit(
            activation_binding=object(),
            delegation=FakeDelegation(),
            integration=FakeIntegration(),
            incident_state="INVESTIGATING",
            after_snapshot_provider=lambda: None,
            production_now=150.0,
        )

    assert downstream.calls == []
