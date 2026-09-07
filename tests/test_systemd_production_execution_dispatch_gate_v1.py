import ast
import inspect
import math
import textwrap
from types import SimpleNamespace

import pytest

import sentinel.systemd_production_execution_dispatch_gate as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_execution_dispatch_gate import (
    ProductionExecutionDispatchState,
    SystemdProductionExecutionDispatchGate,
)


class FakeBinding:
    def __init__(
        self,
        *,
        fresh=True,
    ):
        self.fresh = fresh

        identity = SimpleNamespace(
            fingerprint="target-fingerprint",
        )

        snapshot = SimpleNamespace(
            identity=identity,
            invocation_id="a" * 32,
        )

        self.evidence = SimpleNamespace(
            incident_id="INC-D89A",
            component_id="systemd:example.service",
            snapshot=snapshot,
        )

    def is_fresh(
        self,
        now,
    ):
        return self.fresh


class FakePermitBinding:
    def __init__(
        self,
        *,
        matches=True,
    ):
        self._matches = matches

    def matches(
        self,
        effect,
    ):
        return self._matches


class FakePlan:
    def __init__(
        self,
        *,
        binding,
        permit_matches=True,
    ):
        self.before = (
            binding.evidence.snapshot
        )

        self.effect = SimpleNamespace(
            incident_id=(
                binding.evidence.incident_id
            ),
            component_id=(
                binding.evidence.component_id
            ),
            execution_id="EXEC-D89A",
            target_fingerprint=(
                binding.evidence
                .snapshot.identity.fingerprint
            ),
            fingerprint="effect-fingerprint",
        )

        self.permit_binding = (
            FakePermitBinding(
                matches=permit_matches,
            )
        )


def prepared(
    monkeypatch,
    *,
    enabled_fresh=True,
    prepared_at=10.0,
):
    binding = FakeBinding(
        fresh=enabled_fresh,
    )

    plan = FakePlan(
        binding=binding,
    )

    monkeypatch.setattr(
        module,
        "TrustedSystemdDispatchEvidenceBinding",
        FakeBinding,
    )

    monkeypatch.setattr(
        module,
        "BoundSystemdRemediationPlan",
        FakePlan,
    )

    class FakePrepared:
        pass

    monkeypatch.setattr(
        module,
        "PreparedSystemdProductionRemediation",
        FakePrepared,
    )

    obj = FakePrepared()
    obj.binding = binding
    obj.plan = plan
    obj.prepared_at = prepared_at

    return obj


def test_default_gate_is_disabled():
    gate = (
        SystemdProductionExecutionDispatchGate()
    )

    assert gate.enabled is False


def test_runtime_gate_is_disabled_by_default():
    runtime = SentinelRuntime()

    gate = (
        runtime
        .systemd_production_execution_dispatch_gate
    )

    assert isinstance(
        gate,
        SystemdProductionExecutionDispatchGate,
    )

    assert gate.enabled is False

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_disabled_gate_returns_blocked(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
    )

    result = (
        SystemdProductionExecutionDispatchGate()
        .assess(
            prepared=obj,
            now=10.0,
        )
    )

    assert (
        result.state
        is ProductionExecutionDispatchState.BLOCKED
    )

    assert (
        result.reason
        == "production_execution_dispatch_disabled"
    )

    assert result.ready_for_policy is False


def test_enabled_gate_means_ready_for_policy_only(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
    )

    result = (
        SystemdProductionExecutionDispatchGate(
            enabled=True,
        )
        .assess(
            prepared=obj,
            now=10.0,
        )
    )

    assert (
        result.state
        is ProductionExecutionDispatchState.READY_FOR_POLICY
    )

    assert result.ready_for_policy is True

    assert (
        result.reason
        == "ready_for_downstream_canonical_policy_evaluation"
    )


def test_stale_binding_blocks_even_when_gate_enabled(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
        enabled_fresh=False,
    )

    result = (
        SystemdProductionExecutionDispatchGate(
            enabled=True,
        )
        .assess(
            prepared=obj,
            now=20.0,
        )
    )

    assert (
        result.state
        is ProductionExecutionDispatchState.BLOCKED
    )

    assert (
        result.reason
        == "trusted_evidence_stale"
    )


@pytest.mark.parametrize(
    "now",
    (
        -1.0,
        math.nan,
        math.inf,
        -math.inf,
    ),
)
def test_invalid_now_fails_closed(
    monkeypatch,
    now,
):
    obj = prepared(
        monkeypatch,
    )

    with pytest.raises(
        ValueError,
    ):
        (
            SystemdProductionExecutionDispatchGate()
            .assess(
                prepared=obj,
                now=now,
            )
        )


def test_future_prepared_at_fails_closed(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
        prepared_at=11.0,
    )

    with pytest.raises(
        ValueError,
    ):
        (
            SystemdProductionExecutionDispatchGate()
            .assess(
                prepared=obj,
                now=10.0,
            )
        )


def test_snapshot_substitution_fails_closed(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
    )

    obj.plan.before = SimpleNamespace(
        identity=SimpleNamespace(
            fingerprint="other",
        ),
        invocation_id="b" * 32,
    )

    with pytest.raises(
        ValueError,
        match="prepared_snapshot_binding_mismatch",
    ):
        (
            SystemdProductionExecutionDispatchGate(
                enabled=True,
            )
            .assess(
                prepared=obj,
                now=10.0,
            )
        )


def test_incident_substitution_fails_closed(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
    )

    obj.plan.effect.incident_id = (
        "INC-OTHER"
    )

    with pytest.raises(
        ValueError,
        match="prepared_incident_id_mismatch",
    ):
        (
            SystemdProductionExecutionDispatchGate(
                enabled=True,
            )
            .assess(
                prepared=obj,
                now=10.0,
            )
        )


def test_component_substitution_fails_closed(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
    )

    obj.plan.effect.component_id = (
        "systemd:other.service"
    )

    with pytest.raises(
        ValueError,
        match="prepared_component_id_mismatch",
    ):
        (
            SystemdProductionExecutionDispatchGate(
                enabled=True,
            )
            .assess(
                prepared=obj,
                now=10.0,
            )
        )


def test_permit_binding_mismatch_fails_closed(
    monkeypatch,
):
    obj = prepared(
        monkeypatch,
    )

    obj.plan.permit_binding = (
        FakePermitBinding(
            matches=False,
        )
    )

    with pytest.raises(
        ValueError,
        match="prepared_permit_binding_mismatch",
    ):
        (
            SystemdProductionExecutionDispatchGate(
                enabled=True,
            )
            .assess(
                prepared=obj,
                now=10.0,
            )
        )


def test_runtime_run_once_does_not_use_dispatch_gate():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "systemd_production_execution_dispatch_gate"
        not in source
    )

    assert ".assess(" not in source


def test_gate_has_no_execution_method():
    gate = (
        SystemdProductionExecutionDispatchGate()
    )

    for name in (
        "execute",
        "execute_verified",
        "authorize",
        "resolve",
        "verify",
    ):
        assert not hasattr(
            gate,
            name,
        )


def test_assess_call_surface_contains_no_downstream_authority():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionExecutionDispatchGate.assess
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


def test_source_has_no_system_or_effect_calls():
    source = inspect.getsource(
        module
    )

    for token in (
        "systemctl",
        "subprocess",
        "sudo",
        "pkexec",
        "systemd-run",
        "ExecutionBoundary",
        "SystemdCommanderIntegration",
        "IncidentManager",
        "FinalOutcomeMapper",
    ):
        assert token not in source


def test_runtime_constructor_does_not_enable_gate():
    source = inspect.getsource(
        SentinelRuntime.__init__
    )

    assert (
        "SystemdProductionExecutionDispatchGate("
        in source
    )

    assert (
        "enabled=False"
        in source
    )
