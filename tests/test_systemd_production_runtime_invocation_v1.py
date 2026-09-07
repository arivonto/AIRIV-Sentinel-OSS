import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

import sentinel.systemd_production_runtime_invocation as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_runtime_invocation import (
    ProductionRuntimeInvocationState,
    SystemdProductionRuntimeInvocationBoundary,
)


class FakePrepared:
    pass


class FakeGate:
    def __init__(
        self,
        *,
        ready=False,
        reason="gate_blocked",
    ):
        self.ready = ready
        self.reason = reason
        self.calls = []

    def assess(
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

        return SimpleNamespace(
            ready_for_policy=self.ready,
            reason=(
                "ready_for_downstream_canonical_policy_evaluation"
                if self.ready
                else self.reason
            ),
        )


def install_fake_types(
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "PreparedSystemdProductionRemediation",
        FakePrepared,
    )

    monkeypatch.setattr(
        module,
        "SystemdProductionExecutionDispatchGate",
        FakeGate,
    )


def test_default_surface_is_disabled(
    monkeypatch,
):
    install_fake_types(
        monkeypatch,
    )

    surface = (
        SystemdProductionRuntimeInvocationBoundary(
            gate=FakeGate(),
        )
    )

    assert surface.enabled is False


def test_disabled_surface_does_not_call_gate(
    monkeypatch,
):
    install_fake_types(
        monkeypatch,
    )

    gate = FakeGate(
        ready=True,
    )

    surface = (
        SystemdProductionRuntimeInvocationBoundary(
            gate=gate,
            enabled=False,
        )
    )

    result = surface.assess_explicit(
        prepared=FakePrepared(),
        now=10.0,
    )

    assert gate.calls == []

    assert (
        result.state
        is ProductionRuntimeInvocationState.BLOCKED
    )

    assert (
        result.reason
        == "production_runtime_invocation_disabled"
    )

    assert result.dispatch_decision is None
    assert result.ready_for_delegation is False


def test_enabled_surface_calls_gate_exactly_once_and_propagates_block(
    monkeypatch,
):
    install_fake_types(
        monkeypatch,
    )

    gate = FakeGate(
        ready=False,
        reason="production_execution_dispatch_disabled",
    )

    prepared = FakePrepared()

    surface = (
        SystemdProductionRuntimeInvocationBoundary(
            gate=gate,
            enabled=True,
        )
    )

    result = surface.assess_explicit(
        prepared=prepared,
        now=20.0,
    )

    assert gate.calls == [
        (
            prepared,
            20.0,
        )
    ]

    assert (
        result.state
        is ProductionRuntimeInvocationState.BLOCKED
    )

    assert (
        result.reason
        == "production_execution_dispatch_disabled"
    )

    assert result.ready_for_delegation is False


def test_enabled_surface_can_report_ready_for_delegation_only(
    monkeypatch,
):
    install_fake_types(
        monkeypatch,
    )

    gate = FakeGate(
        ready=True,
    )

    surface = (
        SystemdProductionRuntimeInvocationBoundary(
            gate=gate,
            enabled=True,
        )
    )

    result = surface.assess_explicit(
        prepared=FakePrepared(),
        now=30.0,
    )

    assert len(gate.calls) == 1

    assert (
        result.state
        is ProductionRuntimeInvocationState.READY_FOR_DELEGATION
    )

    assert (
        result.reason
        == "ready_for_explicit_canonical_delegation"
    )

    assert result.ready_for_delegation is True
    assert result.dispatch_decision is not None


def test_invalid_prepared_type_fails_before_gate(
    monkeypatch,
):
    install_fake_types(
        monkeypatch,
    )

    gate = FakeGate(
        ready=True,
    )

    surface = (
        SystemdProductionRuntimeInvocationBoundary(
            gate=gate,
            enabled=True,
        )
    )

    with pytest.raises(
        TypeError,
        match="PreparedSystemdProductionRemediation required",
    ):
        surface.assess_explicit(
            prepared=object(),
            now=10.0,
        )

    assert gate.calls == []


def test_runtime_owns_exact_same_disabled_d89a_gate():
    runtime = SentinelRuntime()

    surface = (
        runtime
        .systemd_production_runtime_invocation
    )

    gate = (
        runtime
        .systemd_production_execution_dispatch_gate
    )

    assert isinstance(
        surface,
        SystemdProductionRuntimeInvocationBoundary,
    )

    assert surface.gate is gate
    assert surface.enabled is False
    assert gate.enabled is False

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_runtime_constructor_does_not_assess():
    source = inspect.getsource(
        SentinelRuntime.__init__
    )

    assert (
        "SystemdProductionRuntimeInvocationBoundary("
        in source
    )

    assert (
        "assess_explicit("
        not in source
    )


def test_run_once_does_not_use_runtime_invocation_surface():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "systemd_production_runtime_invocation"
        not in source
    )

    assert (
        "assess_explicit"
        not in source
    )


def test_assess_explicit_calls_only_d89a_gate_once():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionRuntimeInvocationBoundary
            .assess_explicit
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
            "assess"
        )
        == 1
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


def test_module_has_no_downstream_or_host_authority_surface():
    source = inspect.getsource(
        module
    )

    forbidden = (
        "execute_" + "verified",
        "SystemdCommander" + "Integration",
        "delegate_" + "for_test",
        "SystemdProductionExecution" + "DelegationBoundary",
        "production_runtime_guard",
        "ExecutionBoundary",
        "execute_argv",
        "IncidentManager",
        "FinalOutcomeMapper",
        "subprocess",
        "systemctl",
        "sudo",
        "pkexec",
        "systemd-run",
    )

    for token in forbidden:
        assert token not in source
