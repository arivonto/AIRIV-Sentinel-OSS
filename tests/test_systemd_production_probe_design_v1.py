import ast
import inspect
from pathlib import Path

from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_probe_design import (
    PROBE_ACTION,
    PROBE_ACTIVATION_TTL_SECONDS,
    PROBE_COMPONENT_ID,
    PROBE_EFFECT_ARGV,
    PROBE_FRAGMENT_PATH,
    PROBE_MAX_ATTEMPTS,
    PROBE_POLICY_MODE,
    PROBE_POLKIT_RULE_PATH,
    PROBE_POLKIT_RULE_SHA256,
    PROBE_POLKIT_RULE_TEXT,
    PROBE_RETRY_WINDOW_SECONDS,
    PROBE_COOLDOWN_SECONDS,
    PROBE_UNIT,
    PROBE_UNIT_SHA256,
    PROBE_UNIT_TEXT,
    SystemdProductionProbeDesign,
    production_probe_design,
)


def test_exact_target_identity():
    assert (
        PROBE_UNIT
        == "airiv-sentinel-production-remediation-probe.service"
    )

    assert (
        PROBE_COMPONENT_ID
        == "systemd:"
        + PROBE_UNIT
    )

    assert (
        PROBE_FRAGMENT_PATH
        == "/etc/systemd/system/"
        + PROBE_UNIT
    )


def test_probe_is_sleep_only_nonbusiness_workload():
    assert (
        "ExecStart=/usr/bin/sleep infinity"
        in PROBE_UNIT_TEXT
    )

    assert "Restart=no" in PROBE_UNIT_TEXT

    for forbidden in (
        "docker",
        "postgres",
        "odoo",
        "cloudflared",
        "ssh",
        "network",
        "curl",
        "wget",
    ):
        assert forbidden not in PROBE_UNIT_TEXT.lower()


def test_probe_hardening_exact_minimum():
    for required in (
        "DynamicUser=yes",
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "RestrictSUIDSGID=yes",
        "LockPersonality=yes",
        "MemoryDenyWriteExecute=yes",
    ):
        assert required in PROBE_UNIT_TEXT


def test_future_effect_is_exact_restart_only():
    assert PROBE_ACTION == "RESTART"

    assert PROBE_EFFECT_ARGV == (
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        PROBE_UNIT,
    )


def test_initial_policy_is_commander_only_and_conservative():
    assert (
        PROBE_POLICY_MODE
        == "COMMANDER_ONLY"
    )

    assert (
        PROBE_COOLDOWN_SECONDS
        == 3600.0
    )

    assert (
        PROBE_RETRY_WINDOW_SECONDS
        == 86400.0
    )

    assert PROBE_MAX_ATTEMPTS == 1

    assert (
        PROBE_ACTIVATION_TTL_SECONDS
        == 300.0
    )


def test_polkit_rule_is_exact_subject_and_exact_target():
    assert (
        PROBE_POLKIT_RULE_PATH
        == "/etc/polkit-1/rules.d/"
        "49-airiv-sentinel-production-probe.rules"
    )

    assert (
        'action.id == "org.freedesktop.systemd1.manage-units"'
        in PROBE_POLKIT_RULE_TEXT
    )

    assert (
        'action.lookup("unit") == '
        '"airiv-sentinel-production-remediation-probe.service"'
        in PROBE_POLKIT_RULE_TEXT
    )

    assert (
        'action.lookup("verb") == "restart"'
        in PROBE_POLKIT_RULE_TEXT
    )

    assert (
        'subject.user == "arivonto"'
        in PROBE_POLKIT_RULE_TEXT
    )

    assert (
        'subject.system_unit == "airiv-sentinel.service"'
        in PROBE_POLKIT_RULE_TEXT
    )

    assert (
        "subject.no_new_privileges === true"
        in PROBE_POLKIT_RULE_TEXT
    )

    assert (
        "polkit.Result.NOT_HANDLED"
        in PROBE_POLKIT_RULE_TEXT
    )


def test_artifact_hashes_are_stable():
    import hashlib

    assert (
        hashlib.sha256(
            PROBE_UNIT_TEXT.encode(
                "utf-8"
            )
        ).hexdigest()
        == PROBE_UNIT_SHA256
    )

    assert (
        hashlib.sha256(
            PROBE_POLKIT_RULE_TEXT.encode(
                "utf-8"
            )
        ).hexdigest()
        == PROBE_POLKIT_RULE_SHA256
    )


def test_design_object_is_exact():
    design = production_probe_design()

    assert isinstance(
        design,
        SystemdProductionProbeDesign,
    )

    assert design.unit == PROBE_UNIT

    assert (
        design.component_id
        == PROBE_COMPONENT_ID
    )

    assert (
        design.future_policy_rule
        == {
            "unit":
                PROBE_UNIT,

            "action":
                "RESTART",

            "mode":
                "COMMANDER_ONLY",

            "cooldown_seconds":
                3600.0,

            "retry_window_seconds":
                86400.0,

            "max_attempts":
                1,
        }
    )

    activation = (
        design
        .future_activation_requirements
    )

    assert (
        activation[
            "durable_single_use_consumption"
        ]
        is True
    )

    assert (
        activation[
            "commander_approval_required"
        ]
        is True
    )

    assert (
        activation[
            "ttl_seconds"
        ]
        == 300.0
    )


def test_runtime_remains_entirely_disabled_and_empty():
    runtime = SentinelRuntime()

    assert (
        runtime
        .systemd_production_activation_runtime_bridge
        .enabled
        is False
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

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_runtime_has_no_probe_design_wiring():
    source = inspect.getsource(
        SentinelRuntime
    )

    assert (
        "SystemdProductionProbeDesign"
        not in source
    )

    assert (
        "production_probe_design"
        not in source
    )

    assert (
        PROBE_UNIT
        not in source
    )


def test_design_module_has_no_effect_calls():
    import sentinel.systemd_production_probe_design as module

    source = inspect.getsource(
        module
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
        "run",
        "Popen",
        "system",
        "execute",
        "execute_verified",
        "execute_argv",
        "invoke_explicit",
        "delegate_for_test",
        "evaluate",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "production_runtime_guard",
        "consume",
        "append",
        "acquire",
        "verify",
        "resolve",
    ):
        assert prohibited not in calls




def test_design_declares_exact_host_paths_without_mutation():
    import ast
    import inspect

    import sentinel.systemd_production_probe_design as module

    assert (
        PROBE_FRAGMENT_PATH
        == "/etc/systemd/system/"
        "airiv-sentinel-production-remediation-probe.service"
    )

    assert (
        PROBE_POLKIT_RULE_PATH
        == "/etc/polkit-1/rules.d/"
        "49-airiv-sentinel-production-probe.rules"
    )

    # The design is REQUIRED to contain canonical systemctl argv
    # as immutable metadata. Authority checks therefore inspect
    # imports/calls, not harmless string constants.
    source = inspect.getsource(module)
    tree = ast.parse(source)

    forbidden_import_roots = {
        "subprocess",
        "shutil",
    }

    forbidden_calls = {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "unlink",
        "remove",
        "rename",
        "replace",
        "mkdir",
        "makedirs",
        "chmod",
        "chown",
        "system",
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "invoke_explicit",
        "execute",
        "execute_verified",
        "execute_argv",
        "consume",
        "append",
        "acquire",
        "resolve",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert (
                    alias.name.split(".", 1)[0]
                    not in forbidden_import_roots
                )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert (
                    node.module.split(".", 1)[0]
                    not in forbidden_import_roots
                )

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id

            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr

            else:
                continue

            assert name not in forbidden_calls

    # Canonical effect command must remain present as DATA.
    assert PROBE_EFFECT_ARGV == (
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        PROBE_UNIT,
    )
