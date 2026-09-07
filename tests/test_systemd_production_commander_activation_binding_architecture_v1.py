import ast
from pathlib import Path

from sentinel.runtime import SentinelRuntime


MODULE = Path(
    "sentinel/systemd_production_commander_activation_binding.py"
)


def _tree():
    return ast.parse(
        MODULE.read_text()
    )


def test_d819_does_not_construct_consumed_activation_binding():
    tree = _tree()

    constructors = 0

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            == "SystemdProductionConsumedActivationBinding"
        ):
            constructors += 1

    assert constructors == 0


def test_exactly_one_delegation_to_d810c():
    tree = _tree()

    calls = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            == "bind_consumed_activation_to_prepared_effect"
        ):
            calls.append(node)

    assert len(calls) == 1


def test_commander_authorization_not_constructed():
    source = MODULE.read_text()

    assert (
        "SystemdProductionCommanderAuthorizationContext"
        not in source
    )

    assert (
        "systemd_production_commander_authorization"
        not in source
    )


def test_no_policy_execution_verification_or_lifecycle_authority():
    tree = _tree()

    forbidden_modules = (
        "remediation_policy",
        "commander_authorization",
        "systemd_commander_integration",
        "execution_boundary",
        "remediation_verifier",
        "final_outcome_mapper",
        "incidents.manager",
        "runtime",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                assert not any(
                    part in item.name
                    for part in forbidden_modules
                )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            assert not any(
                part in module
                for part in forbidden_modules
            )

    forbidden_calls = {
        "evaluate",
        "consume",
        "execute",
        "execute_verified",
        "verify",
        "resolve",
        "update_status",
        "remediate",
        "map",
    }

    calls = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)

        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)

    assert not (
        calls & forbidden_calls
    )


def test_runtime_does_not_wire_d819():
    source = Path(
        "sentinel/runtime.py"
    ).read_text()

    assert (
        "systemd_production_commander_activation_binding"
        not in source
    )


def test_generic_production_runtime_remains_fail_closed():
    runtime = SentinelRuntime()

    assert (
        runtime.policy.list_systemd_production_targets()
        == ()
    )

    assert (
        runtime.systemd_production_activation_runtime_bridge.enabled
        is False
    )

    assert (
        runtime.systemd_production_runtime_delegation_bridge.enabled
        is False
    )

    assert (
        runtime.systemd_production_runtime_invocation.enabled
        is False
    )

    assert (
        runtime.systemd_production_execution_dispatch_gate.enabled
        is False
    )
