import ast
from pathlib import Path

from sentinel.runtime import SentinelRuntime


MODULE = Path(
    "sentinel/systemd_production_commander_authorization_handoff.py"
)


def _tree():
    return ast.parse(
        MODULE.read_text()
    )


def test_exactly_one_d815_context_construction():
    tree = _tree()

    calls = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            == "SystemdProductionCommanderAuthorizationContext"
        ):
            calls.append(node)

    assert len(calls) == 1


def test_no_competing_trusted_approval_construction():
    tree = _tree()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            == "TrustedSystemdProductionCommanderApproval"
        ):
            raise AssertionError(
                "D8.20 must not construct Commander approval"
            )


def test_ledger_owners_are_inputs_not_authority_calls():
    tree = _tree()

    forbidden_methods = {
        "issue",
        "consume",
        "records",
        "consumed",
    }

    seen = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        ):
            seen.add(
                node.func.attr
            )

    assert not (
        seen & forbidden_methods
    )


def test_no_policy_execution_verification_or_lifecycle_calls():
    tree = _tree()

    forbidden_modules = (
        "remediation_policy",
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
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "execute",
        "execute_verified",
        "verify",
        "resolve",
        "update_status",
        "remediate",
        "map",
        "matches",
    }

    seen = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            seen.add(
                node.func.id
            )

        elif isinstance(node.func, ast.Attribute):
            seen.add(
                node.func.attr
            )

    assert not (
        seen & forbidden_calls
    )


def test_runtime_does_not_wire_d820():
    source = Path(
        "sentinel/runtime.py"
    ).read_text()

    assert (
        "systemd_production_commander_authorization_handoff"
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
