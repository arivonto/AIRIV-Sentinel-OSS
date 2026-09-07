from __future__ import annotations

import inspect

import pytest

import sentinel.systemd_canary_bootstrap_manifest as module

from sentinel.systemd_canary_bootstrap_manifest import (
    COMMANDER_CANARY_INSTALL_APPROVAL,
    COMMANDER_SENTINEL_NNP_APPROVAL,
    SENTINEL_DROPIN_PATH,
    SENTINEL_DROPIN_TEXT,
    BootstrapFileManifest,
    canonical_bootstrap_manifest,
    evaluate_bootstrap_readiness,
)

from sentinel.systemd_canary_least_privilege import (
    CANARY_POLKIT_RULE,
    POLKIT_RULE_PATH,
)

from sentinel.systemd_live_canary_preflight import (
    CANARY_FRAGMENT_PATH,
    CANARY_UNIT_TEXT,
)


def test_exact_three_file_manifest():
    manifest = canonical_bootstrap_manifest()

    assert manifest.expected_pre_nnp is False
    assert manifest.target_nnp is True

    assert (
        manifest.sentinel_dropin.destination
        == SENTINEL_DROPIN_PATH
    )
    assert (
        manifest.sentinel_dropin.content
        == SENTINEL_DROPIN_TEXT
    )

    assert (
        manifest.canary_unit.destination
        == CANARY_FRAGMENT_PATH
    )
    assert manifest.canary_unit.content == CANARY_UNIT_TEXT

    assert manifest.polkit_rule.destination == POLKIT_RULE_PATH
    assert manifest.polkit_rule.content == CANARY_POLKIT_RULE


def test_all_bootstrap_files_are_root_owned_0644():
    manifest = canonical_bootstrap_manifest()

    for item in (
        manifest.sentinel_dropin,
        manifest.canary_unit,
        manifest.polkit_rule,
    ):
        assert item.owner_uid == 0
        assert item.owner_gid == 0
        assert item.mode == 0o644
        assert len(item.content_sha256) == 64
        assert len(item.fingerprint) == 64


def test_dropin_changes_only_nnp():
    assert SENTINEL_DROPIN_TEXT == (
        "[Service]\n"
        "NoNewPrivileges=yes\n"
    )


def test_install_role_order_exact():
    manifest = canonical_bootstrap_manifest()

    assert manifest.install_roles == (
        "sentinel_nnp_dropin",
        "canary_unit",
        "canary_polkit_rule",
    )


def test_apply_lifecycle_order_exact():
    manifest = canonical_bootstrap_manifest()

    assert [
        command.argv
        for command in manifest.apply_commands
    ] == [
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "daemon-reload",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "restart",
            "airiv-sentinel.service",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "start",
            "airiv-sentinel-remediation-canary.service",
        ),
    ]


def test_rollback_file_removal_order_exact():
    manifest = canonical_bootstrap_manifest()

    assert manifest.rollback_remove_paths == (
        POLKIT_RULE_PATH,
        CANARY_FRAGMENT_PATH,
        SENTINEL_DROPIN_PATH,
    )


def test_rollback_lifecycle_order_exact():
    manifest = canonical_bootstrap_manifest()

    assert [
        command.argv
        for command in manifest.rollback_commands
    ] == [
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "stop",
            "airiv-sentinel-remediation-canary.service",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "daemon-reload",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "restart",
            "airiv-sentinel.service",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "reset-failed",
            "airiv-sentinel-remediation-canary.service",
        ),
    ]


def test_tampered_hash_rejected():
    manifest = canonical_bootstrap_manifest()

    with pytest.raises(
        ValueError,
        match="content hash mismatch",
    ):
        BootstrapFileManifest(
            role="tampered",
            destination=manifest.canary_unit.destination,
            content=manifest.canary_unit.content,
            content_sha256="0" * 64,
            owner_uid=0,
            owner_gid=0,
            mode=0o644,
        )


def test_manifest_fingerprint_stable():
    first = canonical_bootstrap_manifest()
    second = canonical_bootstrap_manifest()

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


def test_gate_requires_runtime_capabilities():
    gate = evaluate_bootstrap_readiness(
        system_unit_supported=False,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval=COMMANDER_SENTINEL_NNP_APPROVAL,
        canary_approval=COMMANDER_CANARY_INSTALL_APPROVAL,
    )

    assert not gate.capability_ready
    assert not gate.mutation_ready


def test_gate_requires_expected_nnp_precondition():
    gate = evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=True,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval=COMMANDER_SENTINEL_NNP_APPROVAL,
        canary_approval=COMMANDER_CANARY_INSTALL_APPROVAL,
    )

    assert not gate.precondition_ready
    assert not gate.mutation_ready


def test_gate_requires_collision_free_paths():
    gate = evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=True,
        rule_collision=False,
        sentinel_approval=COMMANDER_SENTINEL_NNP_APPROVAL,
        canary_approval=COMMANDER_CANARY_INSTALL_APPROVAL,
    )

    assert not gate.collision_free
    assert not gate.mutation_ready


def test_gate_requires_both_exact_commander_tokens():
    missing = evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval=None,
        canary_approval=None,
    )

    wrong = evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval="APPROVE",
        canary_approval="APPROVE",
    )

    assert not missing.approvals_complete
    assert not missing.mutation_ready
    assert not wrong.approvals_complete
    assert not wrong.mutation_ready


def test_synthetic_exact_dual_approval_is_ready():
    gate = evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval=COMMANDER_SENTINEL_NNP_APPROVAL,
        canary_approval=COMMANDER_CANARY_INSTALL_APPROVAL,
    )

    assert gate.capability_ready
    assert gate.precondition_ready
    assert gate.collision_free
    assert gate.approvals_complete
    assert gate.mutation_ready


def test_module_has_no_host_execution_authority():
    source = inspect.getsource(module)

    forbidden = (
        "subprocess",
        "os.system",
        "Popen",
        "execute_argv",
        "execute_bound",
        "claim_live_run_permit",
        ".write_text(",
        ".write_bytes(",
        ".unlink(",
        ".chmod(",
        ".chown(",
    )

    for token in forbidden:
        assert token not in source
