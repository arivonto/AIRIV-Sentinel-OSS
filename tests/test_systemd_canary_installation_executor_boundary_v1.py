from __future__ import annotations

import inspect

import pytest

import sentinel.systemd_canary_installation_executor_boundary as module

from sentinel.systemd_canary_installation_executor_boundary import (
    CanaryInstallationExecutorSafetyBoundary,
)

from sentinel.systemd_canary_installation_plan import (
    COMMANDER_INSTALL_APPROVAL,
    build_canary_installation_plan,
)

from sentinel.systemd_live_canary_preflight import (
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
    }[status]

    return CommandProbe(
        argv=("probe",),
        returncode=rc,
        stdout="",
        stderr="",
        status=status,
    )


def preflight(
    privilege,
):
    design = canonical_canary_design()

    return SystemdCanaryPreflight(
        design=design,
        executable_ok=True,
        fragment_collision=False,
        loaded_unit_collision=False,
        sentinel_distinct=True,
        offline_verify=probe("PASS"),
        sudo_probe=probe("DENIED"),
        polkit_probe=probe(
            privilege
        ),
        privilege_result=privilege,
    )


def test_current_denied_privilege_cannot_prepare():
    pf = preflight(
        "DENIED"
    )

    plan = build_canary_installation_plan(
        pf
    )

    boundary = (
        CanaryInstallationExecutorSafetyBoundary()
    )

    with pytest.raises(
        PermissionError,
        match="privilege_not_authorized",
    ):
        boundary.prepare(
            preflight=pf,
            plan=plan,
            commander_approval=(
                COMMANDER_INSTALL_APPROVAL
            ),
        )


def test_authorized_without_commander_approval_cannot_prepare():
    pf = preflight(
        "AUTHORIZED"
    )

    plan = build_canary_installation_plan(
        pf
    )

    boundary = (
        CanaryInstallationExecutorSafetyBoundary()
    )

    with pytest.raises(
        PermissionError,
        match="commander_approval_required",
    ):
        boundary.prepare(
            preflight=pf,
            plan=plan,
            commander_approval=None,
        )


def test_exact_authorized_synthetic_gate_prepares_envelope_only():
    pf = preflight(
        "AUTHORIZED"
    )

    plan = build_canary_installation_plan(
        pf
    )

    envelope = (
        CanaryInstallationExecutorSafetyBoundary()
        .prepare(
            preflight=pf,
            plan=plan,
            commander_approval=(
                COMMANDER_INSTALL_APPROVAL
            ),
        )
    )

    assert (
        envelope.plan_fingerprint
        == plan.fingerprint
    )

    assert (
        envelope.design_fingerprint
        == pf.design.fingerprint
    )

    assert (
        envelope.file_manifest_fingerprint
        == plan.file_manifest.fingerprint
    )

    assert (
        envelope.privilege_result
        == "AUTHORIZED"
    )

    assert envelope.commander_approved

    assert (
        "airiv-sentinel.service"
        not in {
            token
            for argv
            in (
                envelope.install_argv
                + envelope.rollback_argv
            )
            for token in argv
        }
    )


def test_boundary_has_no_host_mutation_primitive():
    source = inspect.getsource(
        module
    )

    forbidden = (
        "subprocess",
        "os.system",
        "Popen",
        "execute_argv",
        "execute_bound",
        "claim_live_run_permit",
        "write_text",
        "write_bytes",
        "unlink",
        "chmod",
        "chown",
        "sudo",
        "pkexec",
    )

    for token in forbidden:
        assert token not in source


def test_boundary_has_no_execute_method():
    boundary = (
        CanaryInstallationExecutorSafetyBoundary()
    )

    assert not hasattr(
        boundary,
        "execute"
    )

    assert not hasattr(
        boundary,
        "run"
    )
