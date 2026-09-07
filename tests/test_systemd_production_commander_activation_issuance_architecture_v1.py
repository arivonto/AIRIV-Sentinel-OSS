import ast
from pathlib import Path

from sentinel.runtime import SentinelRuntime


MODULE = Path(
    "sentinel/systemd_production_commander_activation_issuance.py"
)


def _tree():
    return ast.parse(
        MODULE.read_text()
    )


def test_d817_does_not_construct_activation_grant():
    tree = _tree()

    calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            calls.append(
                node.func.id
            )

        elif isinstance(node.func, ast.Attribute):
            calls.append(
                node.func.attr
            )

    assert (
        calls.count(
            "SystemdProductionActivationGrant"
        )
        == 0
    )


def test_exactly_one_delegation_to_existing_issuer():
    tree = _tree()

    issue_calls = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "issue"
        ):
            issue_calls.append(node)

    assert len(issue_calls) == 1

    call = issue_calls[0]

    assert (
        isinstance(call.func.value, ast.Name)
        and call.func.value.id == "issuer"
    )


def test_no_policy_consumption_execution_or_lifecycle_authority():
    tree = _tree()

    forbidden_modules = (
        "remediation_policy",
        "activation_consumption",
        "activation_binding",
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
        "bind_consumed_activation_to_prepared_effect",
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
            calls.add(
                node.func.id
            )

        elif isinstance(node.func, ast.Attribute):
            calls.add(
                node.func.attr
            )

    assert not (
        calls & forbidden_calls
    )


def test_runtime_does_not_wire_d817():
    source = Path(
        "sentinel/runtime.py"
    ).read_text()

    assert (
        "systemd_production_commander_activation_issuance"
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
