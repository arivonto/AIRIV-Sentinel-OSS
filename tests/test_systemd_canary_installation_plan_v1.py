from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

import sentinel.systemd_canary_installation_plan as module

from sentinel.systemd_canary_installation_plan import (
    COMMANDER_INSTALL_APPROVAL,
    CanaryFileManifest,
    build_canary_installation_plan,
    evaluate_canary_pre_mutation_gate,
)

from sentinel.systemd_live_canary_preflight import (
    CANARY_FRAGMENT_PATH,
    CANARY_UNIT,
    CommandProbe,
    SystemdCanaryPreflight,
    canonical_canary_design,
)


def probe(status):
    rc = {
        "PASS": 0,
        "AUTHORIZED": 0,
        "DENIED": 1,
        "UNKNOWN": 2,
        "UNAVAILABLE": None,
    }[status]

    return CommandProbe(
        argv=("probe",),
        returncode=rc,
        stdout="",
        stderr="",
        status=status,
    )


def preflight(
    *,
    privilege="AUTHORIZED",
    fragment_collision=False,
    loaded_collision=False,
):
    design = canonical_canary_design()

    return SystemdCanaryPreflight(
        design=design,
        executable_ok=True,

        fragment_collision=(
            fragment_collision
        ),

        loaded_unit_collision=(
            loaded_collision
        ),

        sentinel_distinct=True,

        offline_verify=probe("PASS"),

        sudo_probe=probe("DENIED"),

        polkit_probe=probe(
            privilege
            if privilege
            in {
                "AUTHORIZED",
                "DENIED",
                "UNKNOWN",
            }
            else "UNKNOWN"
        ),

        privilege_result=privilege,
    )


def test_exact_file_manifest():
    pf = preflight()

    plan = build_canary_installation_plan(
        pf
    )

    manifest = plan.file_manifest

    assert (
        manifest.destination
        == CANARY_FRAGMENT_PATH
    )

    assert manifest.owner_uid == 0
    assert manifest.owner_gid == 0
    assert manifest.mode == 0o644

    assert (
        manifest.content
        == pf.design.unit_text
    )

    assert (
        manifest.content_sha256
        == pf.design.unit_sha256
    )


def test_installation_commands_are_exact():
    plan = build_canary_installation_plan(
        preflight()
    )

    assert [
        command.argv
        for command
        in plan.install_commands
    ] == [
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "daemon-reload",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "start",
            CANARY_UNIT,
        ),
    ]


def test_rollback_commands_are_exact_and_canary_only():
    plan = build_canary_installation_plan(
        preflight()
    )

    assert [
        command.argv
        for command
        in plan.rollback_commands
    ] == [
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "stop",
            CANARY_UNIT,
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "daemon-reload",
        ),
        (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "reset-failed",
            CANARY_UNIT,
        ),
    ]

    for command in (
        plan.install_commands
        + plan.rollback_commands
    ):
        assert (
            "airiv-sentinel.service"
            not in command.argv
        )


def test_unknown_privilege_blocks_even_without_approval():
    pf = preflight(
        privilege="UNKNOWN"
    )

    plan = build_canary_installation_plan(
        pf
    )

    result = (
        evaluate_canary_pre_mutation_gate(
            preflight=pf,
            plan=plan,
            commander_approval=None,
        )
    )

    assert not result.ready

    assert (
        result.reason
        == "privilege_not_authorized"
    )


def test_denied_privilege_blocks_even_with_exact_approval():
    pf = preflight(
        privilege="DENIED"
    )

    plan = build_canary_installation_plan(
        pf
    )

    result = (
        evaluate_canary_pre_mutation_gate(
            preflight=pf,
            plan=plan,
            commander_approval=(
                COMMANDER_INSTALL_APPROVAL
            ),
        )
    )

    assert not result.ready

    assert (
        result.reason
        == "privilege_not_authorized"
    )


def test_authorized_privilege_still_requires_exact_commander_approval():
    pf = preflight(
        privilege="AUTHORIZED"
    )

    plan = build_canary_installation_plan(
        pf
    )

    missing = (
        evaluate_canary_pre_mutation_gate(
            preflight=pf,
            plan=plan,
            commander_approval=None,
        )
    )

    wrong = (
        evaluate_canary_pre_mutation_gate(
            preflight=pf,
            plan=plan,
            commander_approval="APPROVE",
        )
    )

    assert not missing.ready
    assert not wrong.ready

    assert (
        missing.reason
        == "commander_approval_required"
    )

    assert (
        wrong.reason
        == "commander_approval_required"
    )


def test_exact_authorized_state_can_be_ready_as_data_only():
    pf = preflight(
        privilege="AUTHORIZED"
    )

    plan = build_canary_installation_plan(
        pf
    )

    result = (
        evaluate_canary_pre_mutation_gate(
            preflight=pf,
            plan=plan,
            commander_approval=(
                COMMANDER_INSTALL_APPROVAL
            ),
        )
    )

    assert result.ready

    assert (
        result.reason
        == "exact_canary_install_authorized"
    )

    assert (
        result.plan_fingerprint
        == plan.fingerprint
    )


def test_plan_rejects_collision():
    with pytest.raises(
        RuntimeError,
        match="design is not ready",
    ):
        build_canary_installation_plan(
            preflight(
                fragment_collision=True
            )
        )


def test_tampered_manifest_hash_is_rejected():
    pf = preflight()

    plan = build_canary_installation_plan(
        pf
    )

    manifest = plan.file_manifest

    with pytest.raises(
        ValueError,
        match="content hash mismatch",
    ):
        CanaryFileManifest(
            destination=(
                manifest.destination
            ),

            content=manifest.content,

            content_sha256="0" * 64,

            owner_uid=0,
            owner_gid=0,
            mode=0o644,
        )


def test_module_has_no_execution_or_host_mutation_authority():
    source = inspect.getsource(
        module
    )

    forbidden = (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "shell=True",
        "execute_argv",
        "execute_bound",
        "claim_live_run_permit",
        "open(",
        "write_text(",
        "unlink(",
        "chmod(",
        "chown(",
    )

    for token in forbidden:
        assert token not in source
