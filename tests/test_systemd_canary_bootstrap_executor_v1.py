from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import inspect

import pytest

import sentinel.systemd_canary_bootstrap_executor as module

from sentinel.systemd_canary_bootstrap_executor import (
    BootstrapAuthorization,
    BootstrapCommandResult,
    BootstrapExecutor,
    prepare_bootstrap_authorization,
)

from sentinel.systemd_canary_bootstrap_manifest import (
    COMMANDER_CANARY_INSTALL_APPROVAL,
    COMMANDER_SENTINEL_NNP_APPROVAL,
    SENTINEL_DROPIN_PATH,
    canonical_bootstrap_manifest,
    evaluate_bootstrap_readiness,
)


class FakeFilesystem:
    def __init__(
        self,
        *,
        fail_install_role=None,
        fail_verify_role=None,
        tamper_role=None,
    ):
        self.files = {}
        self.fail_install_role = fail_install_role
        self.fail_verify_role = fail_verify_role
        self.tamper_role = tamper_role

    def exists(self, path):
        return path in self.files

    def install_exact(self, manifest):
        if manifest.role == self.fail_install_role:
            raise RuntimeError(
                f"injected_install_failure:{manifest.role}"
            )

        self.files[manifest.destination] = {
            "content": manifest.content,
            "uid": manifest.owner_uid,
            "gid": manifest.owner_gid,
            "mode": manifest.mode,
        }

        if manifest.role == self.tamper_role:
            self.files[
                manifest.destination
            ]["content"] += "\nTAMPERED"

    def verify_exact(self, manifest):
        if manifest.role == self.fail_verify_role:
            return False

        current = self.files.get(
            manifest.destination
        )

        if current is None:
            return False

        digest = sha256(
            current["content"].encode("utf-8")
        ).hexdigest()

        return (
            digest == manifest.content_sha256
            and current["uid"] == manifest.owner_uid
            and current["gid"] == manifest.owner_gid
            and current["mode"] == manifest.mode
        )

    def remove_exact(self, manifest):
        if not self.verify_exact(manifest):
            raise RuntimeError(
                f"remove_exact_mismatch:{manifest.role}"
            )

        del self.files[
            manifest.destination
        ]


class FakeSystemctl:
    def __init__(
        self,
        filesystem,
        *,
        fail_command=None,
        force_nnp_false=False,
        force_same_invocation=False,
        force_canary_inactive=False,
        rollback_fail_command=None,
    ):
        self.filesystem = filesystem
        self.fail_command = fail_command
        self.force_nnp_false = force_nnp_false
        self.force_same_invocation = force_same_invocation
        self.force_canary_inactive = force_canary_inactive
        self.rollback_fail_command = rollback_fail_command

        self._sentinel_active = True
        self._sentinel_nnp = False
        self._sentinel_invocation = "INV-BEFORE"
        self._canary_active = False

        self.calls = []

    def run(self, command, timeout):
        self.calls.append(
            (
                command.name,
                command.argv,
                timeout,
            )
        )

        if command.name == self.fail_command:
            return BootstrapCommandResult(
                returncode=1,
                stderr="injected apply failure",
            )

        if command.name == self.rollback_fail_command:
            return BootstrapCommandResult(
                returncode=1,
                stderr="injected rollback failure",
            )

        if command.name == "restart_sentinel":
            self._sentinel_active = True

            if not self.force_same_invocation:
                self._sentinel_invocation = "INV-AFTER"

            if self.force_nnp_false:
                self._sentinel_nnp = False
            else:
                self._sentinel_nnp = self.filesystem.exists(
                    SENTINEL_DROPIN_PATH
                )

        elif command.name == "start_canary":
            self._canary_active = (
                False
                if self.force_canary_inactive
                else True
            )

        elif command.name == "stop_canary":
            self._canary_active = False

        elif command.name == "restart_sentinel_after_restore":
            self._sentinel_active = True
            self._sentinel_invocation = "INV-ROLLBACK"
            self._sentinel_nnp = self.filesystem.exists(
                SENTINEL_DROPIN_PATH
            )

        return BootstrapCommandResult(
            returncode=0
        )

    def sentinel_active(self):
        return self._sentinel_active

    def sentinel_no_new_privileges(self):
        return self._sentinel_nnp

    def sentinel_invocation_id(self):
        return self._sentinel_invocation

    def canary_active(self):
        return self._canary_active


class FakeProbe:
    def __init__(
        self,
        *,
        daemon="AUTHORIZED",
        shell="DENIED",
    ):
        self.daemon = daemon
        self.shell = shell

    def daemon_status(self):
        return self.daemon

    def shell_status(self):
        return self.shell


def ready_gate():
    return evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval=(
            COMMANDER_SENTINEL_NNP_APPROVAL
        ),
        canary_approval=(
            COMMANDER_CANARY_INSTALL_APPROVAL
        ),
    )


def authorization():
    manifest = canonical_bootstrap_manifest()

    return prepare_bootstrap_authorization(
        manifest=manifest,
        readiness=ready_gate(),
    )


def test_prepare_authorization_requires_ready_dual_gate():
    manifest = canonical_bootstrap_manifest()

    blocked = evaluate_bootstrap_readiness(
        system_unit_supported=True,
        no_new_privileges_supported=True,
        current_nnp=False,
        dropin_collision=False,
        canary_collision=False,
        rule_collision=False,
        sentinel_approval=None,
        canary_approval=None,
    )

    with pytest.raises(
        PermissionError,
        match="bootstrap_gate_not_ready",
    ):
        prepare_bootstrap_authorization(
            manifest=manifest,
            readiness=blocked,
        )


def test_authorization_is_bound_to_exact_manifest():
    manifest = canonical_bootstrap_manifest()
    auth = authorization()

    assert (
        auth.manifest_fingerprint
        == manifest.fingerprint
    )

    assert auth.sentinel_hardening_approved
    assert auth.canary_bootstrap_approved


def test_manifest_substitution_is_rejected():
    manifest = canonical_bootstrap_manifest()
    auth = authorization()

    bad = replace(
        auth,
        manifest_fingerprint="0" * 64,
    )

    executor = BootstrapExecutor()

    with pytest.raises(
        PermissionError,
        match="manifest_fingerprint_mismatch",
    ):
        executor.execute(
            manifest=manifest,
            authorization=bad,
            filesystem=FakeFilesystem(),
            systemctl=FakeSystemctl(
                FakeFilesystem()
            ),
            authorization_probe=FakeProbe(),
        )


def test_happy_path_succeeds_with_exact_fake_effects():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()
    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "SUCCEEDED"
    assert result.succeeded
    assert not result.rollback_errors

    assert fs.exists(
        manifest.sentinel_dropin.destination
    )
    assert fs.exists(
        manifest.canary_unit.destination
    )
    assert fs.exists(
        manifest.polkit_rule.destination
    )

    assert ctl.sentinel_active()
    assert ctl.sentinel_no_new_privileges()
    assert ctl.sentinel_invocation_id() == "INV-AFTER"
    assert ctl.canary_active()

    assert "probe:daemon:AUTHORIZED" in result.events
    assert "probe:shell:DENIED" in result.events


def test_collision_blocks_before_any_mutation():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()

    fs.files[
        manifest.canary_unit.destination
    ] = {
        "content": "FOREIGN",
        "uid": 0,
        "gid": 0,
        "mode": 0o644,
    }

    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "BLOCKED"
    assert result.error == "collision:canary_unit"
    assert ctl.calls == []


def test_first_install_failure_has_no_mutation_and_no_rollback():
    manifest = canonical_bootstrap_manifest()

    fs = FakeFilesystem(
        fail_install_role="sentinel_nnp_dropin"
    )
    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "FAILED_NO_MUTATION"
    assert fs.files == {}
    assert ctl.calls == []


@pytest.mark.parametrize(
    "fail_role",
    [
        "canary_unit",
        "canary_polkit_rule",
    ],
)
def test_later_install_failure_rolls_back(
    fail_role,
):
    manifest = canonical_bootstrap_manifest()

    fs = FakeFilesystem(
        fail_install_role=fail_role
    )
    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLED_BACK"
    assert fs.files == {}
    assert ctl.sentinel_active()
    assert not ctl.sentinel_no_new_privileges()
    assert not ctl.canary_active()


@pytest.mark.parametrize(
    "command_name",
    [
        "daemon_reload",
        "restart_sentinel",
        "start_canary",
    ],
)
def test_apply_command_failure_rolls_back(
    command_name,
):
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()

    ctl = FakeSystemctl(
        fs,
        fail_command=command_name,
    )

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLED_BACK"
    assert fs.files == {}
    assert ctl.sentinel_active()
    assert not ctl.sentinel_no_new_privileges()
    assert not ctl.canary_active()


def test_nnp_verification_failure_rolls_back():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()

    ctl = FakeSystemctl(
        fs,
        force_nnp_false=True,
    )

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLED_BACK"
    assert result.error == "sentinel_nnp_not_enabled"
    assert fs.files == {}


def test_invocation_must_change_after_restart():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()

    ctl = FakeSystemctl(
        fs,
        force_same_invocation=True,
    )

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLED_BACK"
    assert result.error == "sentinel_invocation_not_changed"
    assert fs.files == {}


def test_canary_active_verification_failure_rolls_back():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()

    ctl = FakeSystemctl(
        fs,
        force_canary_inactive=True,
    )

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLED_BACK"
    assert result.error == "canary_not_active"
    assert fs.files == {}


def test_daemon_polkit_denial_rolls_back():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()
    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(
            daemon="DENIED"
        ),
    )

    assert result.status == "ROLLED_BACK"

    assert (
        result.error
        == "daemon_runtime_authorization_not_granted"
    )

    assert fs.files == {}


def test_shell_authorization_is_security_failure_and_rolls_back():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()
    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(
            daemon="AUTHORIZED",
            shell="AUTHORIZED",
        ),
    )

    assert result.status == "ROLLED_BACK"

    assert (
        result.error
        == "shell_runtime_authorization_must_be_denied"
    )

    assert fs.files == {}


def test_tampered_artifact_is_never_blindly_removed():
    manifest = canonical_bootstrap_manifest()

    fs = FakeFilesystem(
        tamper_role="canary_polkit_rule"
    )
    ctl = FakeSystemctl(fs)

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLBACK_FAILED"

    assert fs.exists(
        manifest.polkit_rule.destination
    )

    assert any(
        "rollback_artifact_mismatch:canary_polkit_rule"
        in item
        for item in result.rollback_errors
    )


def test_rollback_command_failure_is_reported_fail_closed():
    manifest = canonical_bootstrap_manifest()
    fs = FakeFilesystem()

    ctl = FakeSystemctl(
        fs,
        fail_command="daemon_reload",
        rollback_fail_command=(
            "restart_sentinel_after_restore"
        ),
    )

    result = BootstrapExecutor().execute(
        manifest=manifest,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLBACK_FAILED"

    assert any(
        "rollback_command_failed:"
        "restart_sentinel_after_restore"
        == item
        for item in result.rollback_errors
    )


def test_executor_module_has_no_direct_host_io_authority():
    source = inspect.getsource(module)

    forbidden = (
        "subprocess",
        "os.system",
        "Popen",
        "Path(",
        "open(",
        ".write_text(",
        ".write_bytes(",
        ".unlink(",
        ".chmod(",
        ".chown(",
        "/etc/systemd/system",
        "/etc/polkit-1",
        "sudo ",
        "pkexec ",
    )

    for token in forbidden:
        assert token not in source
