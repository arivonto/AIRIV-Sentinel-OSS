from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(
    "sentinel/systemd_evidence_plan_handoff.py"
).read_text(
    encoding="utf-8"
)


def _handoff():
    tree = ast.parse(
        SOURCE
    )

    functions = [
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name
        == "build_bound_systemd_plan_from_trusted_binding"
    ]

    assert len(functions) == 1

    return functions[0]


def _calls():
    result = []

    for node in ast.walk(
        _handoff()
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
            result.append(
                (
                    node.func.id,
                    node.lineno,
                )
            )

        elif isinstance(
            node.func,
            ast.Attribute,
        ):
            result.append(
                (
                    node.func.attr,
                    node.lineno,
                )
            )

    return result


def test_no_manual_post_init_invocation():
    assert "__post_init__" not in {
        name
        for name, _ in _calls()
    }


def test_freshness_is_checked_before_scope_and_plan_construction():
    calls = _calls()

    fresh_line = min(
        line
        for name, line in calls
        if name == "is_fresh"
    )

    scope_line = min(
        line
        for name, line in calls
        if name == "BoundSystemdActionScope"
    )

    plan_line = min(
        line
        for name, line in calls
        if name
        == "build_bound_systemd_remediation_plan"
    )

    assert fresh_line < scope_line
    assert fresh_line < plan_line


def test_no_downstream_authority_calls():
    names = {
        name
        for name, _ in _calls()
    }

    prohibited = {
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "production_runtime_guard",
        "execute",
        "execute_argv",
        "claim",
        "record_plan",
        "acquire",
        "verify",
        "resolve",
        "systemctl",
        "run",
        "Popen",
    }

    assert not (
        names
        & prohibited
    )


def test_canonical_builder_is_used_once():
    names = [
        name
        for name, _ in _calls()
    ]

    assert (
        names.count(
            "build_bound_systemd_remediation_plan"
        )
        == 1
    )

    assert (
        names.count(
            "BoundSystemdActionScope"
        )
        == 1
    )
