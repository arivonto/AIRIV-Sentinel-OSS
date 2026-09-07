from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from sentinel.systemd_canary_bootstrap_corrective_semantics import (
    PKCHECK_FORBIDDEN_PROOF_CLAIMS,
    PKCHECK_PROVABLE_CLAIMS,
    POLKIT_INSTALL_DIRECT_FINAL_PATH,
    canonical_d7d1_corrective_semantics,
)
from sentinel.systemd_canary_bootstrap_manifest import (
    canonical_bootstrap_manifest,
)
from sentinel.systemd_canary_least_privilege import (
    CANARY_POLKIT_RULE,
)


EXPECTED_CANONICAL_RULE_SHA = (
    "7f745b343ca7e9746a39b5484b61097e"
    "3346e20b91ef0f62d21532d584741b1d"
)

POLKIT_PATH = (
    "/etc/polkit-1/rules.d/"
    "49-airiv-sentinel-canary.rules"
)


def semantics():
    manifest = canonical_bootstrap_manifest()

    return canonical_d7d1_corrective_semantics(
        manifest.fingerprint,
    )


def test_corrective_semantics_are_manifest_bound_and_deterministic():
    first = semantics()
    second = semantics()

    assert first.manifest_fingerprint
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


def test_direct_final_path_polkit_install_is_required():
    policy = semantics()

    assert (
        policy.polkit_install_mode
        == POLKIT_INSTALL_DIRECT_FINAL_PATH
    )

    policy.validate_polkit_install(
        destination_path=POLKIT_PATH,
        write_path=POLKIT_PATH,
        rename_into_destination=False,
    )


def test_hidden_temporary_file_then_rename_is_rejected():
    policy = semantics()

    with pytest.raises(
        ValueError,
        match="directly to final path",
    ):
        policy.validate_polkit_install(
            destination_path=POLKIT_PATH,
            write_path=(
                "/etc/polkit-1/rules.d/"
                ".airiv-bootstrap.ABC123"
            ),
            rename_into_destination=True,
        )


def test_same_path_with_rename_semantics_is_still_rejected():
    policy = semantics()

    with pytest.raises(
        ValueError,
        match="rename/move",
    ):
        policy.validate_polkit_install(
            destination_path=POLKIT_PATH,
            write_path=POLKIT_PATH,
            rename_into_destination=True,
        )


@pytest.mark.parametrize(
    "claim",
    sorted(PKCHECK_PROVABLE_CLAIMS),
)
def test_pkcheck_claims_are_limited_to_synthetic_evidence(claim):
    semantics().validate_pkcheck_claim(claim)


@pytest.mark.parametrize(
    "claim",
    sorted(PKCHECK_FORBIDDEN_PROOF_CLAIMS),
)
def test_pkcheck_cannot_claim_safe_pidfd_or_real_dbus_authorization(
    claim,
):
    with pytest.raises(
        ValueError,
        match="pkcheck cannot prove",
    ):
        semantics().validate_pkcheck_claim(claim)


def test_unknown_pkcheck_claim_fails_closed():
    with pytest.raises(
        ValueError,
        match="unknown D7D.1 pkcheck claim",
    ):
        semantics().validate_pkcheck_claim(
            "future_unreviewed_claim"
        )


def test_real_authorization_is_deferred_to_d7d2():
    assert (
        semantics().real_authorization_validation_phase
        == "2.13D.D7D.2"
    )


def test_canonical_least_privilege_rule_is_unchanged():
    import hashlib

    assert hashlib.sha256(
        CANARY_POLKIT_RULE.encode("utf-8")
    ).hexdigest() == EXPECTED_CANONICAL_RULE_SHA

    assert (
        'subject.system_unit == "airiv-sentinel.service"'
        in CANARY_POLKIT_RULE
    )

    assert (
        "subject.no_new_privileges === true"
        in CANARY_POLKIT_RULE
    )


def test_corrective_semantics_module_has_no_host_execution_authority():
    import sentinel.systemd_canary_bootstrap_corrective_semantics as module

    source = inspect.getsource(module)
    tree = ast.parse(source)

    forbidden_names = {
        "subprocess",
        "systemctl",
        "pkcheck",
        "sudo",
        "pkexec",
    }

    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert not imports & forbidden_names

    call_names = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            call_names.add(node.func.id)

        elif isinstance(node.func, ast.Attribute):
            call_names.add(node.func.attr)

    assert not call_names & {
        "run",
        "Popen",
        "system",
        "execv",
        "execve",
        "spawn",
    }


def test_contracts_lock_corrected_verification_boundary():
    root = Path(__file__).resolve().parents[1]

    manifest_contract = (
        root
        / "contracts"
        / "SYSTEMD_CANARY_BOOTSTRAP_MANIFEST_CONTRACT.md"
    ).read_text(encoding="utf-8")

    executor_contract = (
        root
        / "contracts"
        / "SYSTEMD_CANARY_BOOTSTRAP_EXECUTOR_CONTRACT.md"
    ).read_text(encoding="utf-8")

    combined = manifest_contract + "\n" + executor_contract

    assert "direct final-path" in combined
    assert "hidden temporary" in combined
    assert "safe pidfd" in combined
    assert "D7D.2" in combined

    assert (
        "MUST NOT claim that `pkcheck --process` proves "
        "`subject.system_unit`"
        in combined
    )
