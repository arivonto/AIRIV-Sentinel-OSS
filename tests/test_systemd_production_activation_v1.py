import ast
import inspect
import math
import textwrap

import pytest

import sentinel.systemd_production_activation as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_activation import (
    SystemdProductionActivationBoundary,
    SystemdProductionActivationGrant,
)


def grant(
    **overrides,
):
    values = {
        "activation_id":
            "ACT-D810A-001",

        "approval_id":
            "APPROVAL-D810A-001",

        "incident_id":
            "INC-D810A",

        "component_id":
            "systemd:example.service",

        "execution_id":
            "EXEC-D810A",

        "effect_fingerprint":
            "f" * 64,

        "issued_at":
            100.0,

        "expires_at":
            160.0,
    }

    values.update(
        overrides
    )

    return SystemdProductionActivationGrant(
        **values
    )


def test_grant_is_immutable():
    value = grant()

    with pytest.raises(
        Exception,
    ):
        value.activation_id = (
            "OTHER"
        )


def test_grant_fingerprint_is_deterministic():
    first = grant()
    second = grant()

    assert (
        first.fingerprint
        == second.fingerprint
    )

    assert len(
        first.fingerprint
    ) == 64


@pytest.mark.parametrize(
    (
        "now",
        "expected",
    ),
    (
        (
            99.999,
            False,
        ),
        (
            100.0,
            True,
        ),
        (
            159.999,
            True,
        ),
        (
            160.0,
            False,
        ),
        (
            161.0,
            False,
        ),
    ),
)
def test_active_interval_is_explicit(
    now,
    expected,
):
    assert (
        grant().is_active(
            now
        )
        is expected
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
def test_invalid_time_fails_closed(
    now,
):
    with pytest.raises(
        ValueError,
    ):
        grant().is_active(
            now
        )


@pytest.mark.parametrize(
    (
        "field",
        "value",
    ),
    (
        (
            "activation_id",
            "",
        ),
        (
            "activation_id",
            "contains space",
        ),
        (
            "approval_id",
            "",
        ),
        (
            "approval_id",
            "human approval phrase",
        ),
        (
            "incident_id",
            "",
        ),
        (
            "component_id",
            "",
        ),
        (
            "execution_id",
            "",
        ),
        (
            "effect_fingerprint",
            "",
        ),
    ),
)
def test_invalid_required_identity_fails_closed(
    field,
    value,
):
    with pytest.raises(
        ValueError,
    ):
        grant(
            **{
                field:
                    value,
            }
        )


def test_expiry_must_be_after_issuance():
    with pytest.raises(
        ValueError,
    ):
        grant(
            issued_at=100.0,
            expires_at=100.0,
        )

    with pytest.raises(
        ValueError,
    ):
        grant(
            issued_at=101.0,
            expires_at=100.0,
        )


def test_matching_effect_is_exact():
    value = grant()

    assert value.matches_effect(
        incident_id="INC-D810A",
        component_id="systemd:example.service",
        execution_id="EXEC-D810A",
        effect_fingerprint="f" * 64,
    )

    assert not value.matches_effect(
        incident_id="INC-OTHER",
        component_id="systemd:example.service",
        execution_id="EXEC-D810A",
        effect_fingerprint="f" * 64,
    )


def test_boundary_accepts_only_active_exact_binding():
    value = grant()

    result = (
        SystemdProductionActivationBoundary()
        .assess(
            grant=value,
            now=120.0,
            incident_id="INC-D810A",
            component_id="systemd:example.service",
            execution_id="EXEC-D810A",
            effect_fingerprint="f" * 64,
        )
    )

    assert result.eligible is True

    assert (
        result.reason
        == "activation_binding_valid"
    )

    assert (
        result.activation_fingerprint
        == value.fingerprint
    )


def test_boundary_blocks_expired_grant():
    value = grant()

    result = (
        SystemdProductionActivationBoundary()
        .assess(
            grant=value,
            now=160.0,
            incident_id="INC-D810A",
            component_id="systemd:example.service",
            execution_id="EXEC-D810A",
            effect_fingerprint="f" * 64,
        )
    )

    assert result.eligible is False

    assert (
        result.reason
        == "activation_not_active"
    )


@pytest.mark.parametrize(
    (
        "field",
        "value",
    ),
    (
        (
            "incident_id",
            "INC-OTHER",
        ),
        (
            "component_id",
            "systemd:other.service",
        ),
        (
            "execution_id",
            "EXEC-OTHER",
        ),
        (
            "effect_fingerprint",
            "e" * 64,
        ),
    ),
)
def test_boundary_blocks_any_effect_substitution(
    field,
    value,
):
    params = {
        "grant":
            grant(),

        "now":
            120.0,

        "incident_id":
            "INC-D810A",

        "component_id":
            "systemd:example.service",

        "execution_id":
            "EXEC-D810A",

        "effect_fingerprint":
            "f" * 64,
    }

    params[field] = value

    result = (
        SystemdProductionActivationBoundary()
        .assess(
            **params
        )
    )

    assert result.eligible is False

    assert (
        result.reason
        == "activation_effect_binding_mismatch"
    )


def test_runtime_does_not_own_activation_grant():
    runtime = SentinelRuntime()

    assert not hasattr(
        runtime,
        "systemd_production_activation",
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


def test_runtime_run_once_has_no_activation_path():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "SystemdProductionActivation"
        not in source
    )

    assert (
        "activation_grant"
        not in source
    )


def test_activation_assess_call_surface_is_pure():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionActivationBoundary
            .assess
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


def test_module_has_no_host_or_runtime_mutation_primitive():
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
        "SystemdCommanderIntegration",
        "IncidentManager",
        "FinalOutcomeMapper",
        "SystemdProductionRuntimeDelegationBridge",
    ):
        assert token not in source
