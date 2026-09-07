import ast
import inspect
import textwrap

import pytest

import sentinel.systemd_production_preparation as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
    SystemdProductionPreparationBoundary,
)


def test_prepare_composes_binding_then_canonical_plan_builder(
    monkeypatch,
):
    events = []

    assessment = object()
    evidence = object()
    privilege = object()
    fake_plan = object()

    class FakeBinding:
        def __init__(
            self,
            **kwargs,
        ):
            events.append(
                (
                    "binding",
                    kwargs,
                )
            )

            self.kwargs = kwargs

    def fake_builder(
        **kwargs,
    ):
        events.append(
            (
                "plan",
                kwargs,
            )
        )

        return fake_plan

    monkeypatch.setattr(
        module,
        "TrustedSystemdDispatchEvidenceBinding",
        FakeBinding,
    )

    monkeypatch.setattr(
        module,
        "build_bound_systemd_plan_from_trusted_binding",
        fake_builder,
    )

    result = (
        SystemdProductionPreparationBoundary()
        .prepare(
            assessment=assessment,
            evidence=evidence,
            now=125.0,
            max_age_seconds=30.0,
            privilege=privilege,
            run_id="RUN-D88B",
            execution_id="EXEC-D88B",
            permit_id="PERMIT-D88B",
        )
    )

    assert isinstance(
        result,
        PreparedSystemdProductionRemediation,
    )

    assert len(events) == 2

    assert events[0][0] == "binding"
    assert events[1][0] == "plan"

    binding = result.binding

    assert (
        events[0][1]["assessment"]
        is assessment
    )

    assert (
        events[0][1]["evidence"]
        is evidence
    )

    assert (
        events[0][1]["now"]
        == 125.0
    )

    assert (
        events[0][1]["max_age_seconds"]
        == 30.0
    )

    assert (
        events[1][1]["binding"]
        is binding
    )

    assert (
        events[1][1]["now"]
        == 125.0
    )

    assert (
        events[1][1]["privilege"]
        is privilege
    )

    assert (
        events[1][1]["run_id"]
        == "RUN-D88B"
    )

    assert (
        events[1][1]["execution_id"]
        == "EXEC-D88B"
    )

    assert (
        events[1][1]["permit_id"]
        == "PERMIT-D88B"
    )

    assert result.plan is fake_plan
    assert result.prepared_at == 125.0


def test_binding_failure_stops_before_plan_builder(
    monkeypatch,
):
    called = {
        "plan": False,
    }

    class BindingError(
        ValueError
    ):
        pass

    def bad_binding(
        **kwargs,
    ):
        raise BindingError(
            "binding failed"
        )

    def builder(
        **kwargs,
    ):
        called["plan"] = True
        return object()

    monkeypatch.setattr(
        module,
        "TrustedSystemdDispatchEvidenceBinding",
        bad_binding,
    )

    monkeypatch.setattr(
        module,
        "build_bound_systemd_plan_from_trusted_binding",
        builder,
    )

    with pytest.raises(
        BindingError,
    ):
        (
            SystemdProductionPreparationBoundary()
            .prepare(
                assessment=object(),
                evidence=object(),
                now=10.0,
                max_age_seconds=5.0,
                privilege=object(),
                run_id="r",
                execution_id="e",
                permit_id="p",
            )
        )

    assert called["plan"] is False


def test_plan_builder_failure_is_propagated_without_alternate_path(
    monkeypatch,
):
    class FakeBinding:
        def __init__(
            self,
            **kwargs,
        ):
            pass

    class PlanFailure(
        ValueError
    ):
        pass

    monkeypatch.setattr(
        module,
        "TrustedSystemdDispatchEvidenceBinding",
        FakeBinding,
    )

    def fail_builder(
        **kwargs,
    ):
        raise PlanFailure(
            "plan rejected"
        )

    monkeypatch.setattr(
        module,
        "build_bound_systemd_plan_from_trusted_binding",
        fail_builder,
    )

    with pytest.raises(
        PlanFailure,
    ):
        (
            SystemdProductionPreparationBoundary()
            .prepare(
                assessment=object(),
                evidence=object(),
                now=10.0,
                max_age_seconds=5.0,
                privilege=object(),
                run_id="r",
                execution_id="e",
                permit_id="p",
            )
        )


def test_boundary_has_no_execution_or_policy_authority():
    boundary = (
        SystemdProductionPreparationBoundary()
    )

    for name in (
        "execute",
        "execute_verified",
        "evaluate",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "verify",
        "resolve",
        "acquire",
    ):
        assert not hasattr(
            boundary,
            name,
        )


def test_runtime_exposes_one_inert_preparation_boundary():
    runtime = SentinelRuntime()

    assert isinstance(
        runtime.systemd_production_preparation,
        SystemdProductionPreparationBoundary,
    )

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_runtime_preparation_and_execution_integration_are_separate():
    runtime = SentinelRuntime()

    assert (
        runtime.systemd_production_preparation
        is not runtime.systemd_production_integration
    )

    assert not hasattr(
        runtime.systemd_production_preparation,
        "commander",
    )


def test_runtime_run_once_does_not_auto_prepare_production_systemd():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "systemd_production_preparation"
        not in source
    )

    assert (
        ".prepare("
        not in source
    )


def test_static_call_surface_is_closed():
    """Only inspect the operational prepare() method call surface.

    Module-level decorators such as @dataclass are declaration-time
    structure, not D8.8B orchestration authority.
    """
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionPreparationBoundary.prepare
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

    assert calls <= {
        "TrustedSystemdDispatchEvidenceBinding",
        "build_bound_systemd_plan_from_trusted_binding",
        "PreparedSystemdProductionRemediation",
    }


def test_static_source_has_no_downstream_authority():
    source = inspect.getsource(
        module
    )

    prohibited = (
        "execute_verified",
        "production_runtime_guard",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "execute_argv",
        "IncidentManager",
        ".resolve(",
        "FinalOutcomeMapper",
        "systemctl",
        "subprocess",
        "sudo",
        "pkexec",
        "systemd-run",
    )

    for token in prohibited:
        assert token not in source


def test_static_composition_uses_locked_boundaries_exactly_once():
    source = inspect.getsource(
        SystemdProductionPreparationBoundary.prepare
    )

    assert (
        source.count(
            "TrustedSystemdDispatchEvidenceBinding("
        )
        == 1
    )

    assert (
        source.count(
            "build_bound_systemd_plan_from_trusted_binding("
        )
        == 1
    )


def test_runtime_constructor_does_not_invoke_prepare():
    source = inspect.getsource(
        SentinelRuntime.__init__
    )

    assert (
        "SystemdProductionPreparationBoundary()"
        in source
    )

    assert (
        ".prepare("
        not in source
    )
