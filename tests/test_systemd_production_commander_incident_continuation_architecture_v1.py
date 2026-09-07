import ast
from pathlib import Path

from sentinel.runtime import SentinelRuntime


MODULE = Path(
    "sentinel/systemd_production_commander_incident_continuation.py"
)


def test_fact_boundary_has_no_policy_execution_or_lifecycle_authority():
    tree = ast.parse(
        MODULE.read_text()
    )

    forbidden_imports = (
        "remediation_policy",
        "final_outcome_mapper",
        "systemd_commander_integration",
        "execution_boundary",
        "systemd_production_activation_consumption",
        "systemd_production_runtime",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                assert not any(
                    part in item.name
                    for part in forbidden_imports
                )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            assert not any(
                part in module
                for part in forbidden_imports
            )

    forbidden_calls = {
        "resolve",
        "update_status",
        "evaluate",
        "issue",
        "consume",
        "execute",
        "execute_verified",
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


def test_existing_autonomous_dispatch_remains_unchanged():
    source = Path(
        "sentinel/systemd_incident_dispatch.py"
    ).read_text()

    assert (
        "CommanderIntent.AUTONOMOUS_REMEDIATE"
        in source
    )

    assert (
        "commander_action_required is not False"
        in source
    )


def test_existing_need_commander_mapper_remains_unchanged():
    source = Path(
        "sentinel/final_outcome_mapper.py"
    ).read_text()

    assert (
        "CommanderIntent.NEED_COMMANDER"
        in source
    )

    assert '"ESCALATED"' in source


def test_d816_not_wired_into_runtime():
    source = Path(
        "sentinel/runtime.py"
    ).read_text()

    assert (
        "systemd_production_commander_incident_continuation"
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
