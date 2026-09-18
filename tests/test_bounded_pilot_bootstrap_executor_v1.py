"""Bounded pilot bootstrap executor regression."""

from dataclasses import replace
from hashlib import sha256
import inspect

import pytest

import sentinel.bounded_pilot_bootstrap_executor as module

from sentinel.bounded_pilot_bootstrap_executor import (
    BoundedPilotBootstrapAuthorization,
    BoundedPilotBootstrapExecutor,
    BoundedPilotCommandResult,
    prepare_bounded_pilot_bootstrap_authorization,
)
from sentinel.bounded_pilot_helper_manifest import (
    canonical_bounded_pilot_helper_manifest,
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
            raise RuntimeError(f"injected_install_failure:{manifest.role}")
        self.files[manifest.destination] = {
            "content": manifest.content,
            "uid": manifest.owner_uid,
            "gid": manifest.owner_gid,
            "mode": manifest.mode,
        }
        if manifest.role == self.tamper_role:
            self.files[manifest.destination]["content"] += "\nTAMPERED"

    def verify_exact(self, manifest):
        if manifest.role == self.fail_verify_role:
            return False
        current = self.files.get(manifest.destination)
        if current is None:
            return False
        digest = sha256(current["content"].encode("utf-8")).hexdigest()
        return (
            digest == manifest.content_sha256
            and current["uid"] == manifest.owner_uid
            and current["gid"] == manifest.owner_gid
            and current["mode"] == manifest.mode
        )

    def remove_exact(self, manifest):
        if not self.verify_exact(manifest):
            raise RuntimeError(f"remove_exact_mismatch:{manifest.role}")
        del self.files[manifest.destination]


class FakeSystemctl:
    def __init__(self, *, fail_first=False, rollback_fail=False):
        self.fail_first = fail_first
        self.rollback_fail = rollback_fail
        self.calls = []

    def run(self, command, timeout):
        self.calls.append((command.name, command.argv, timeout))
        if len(self.calls) > 1 and self.rollback_fail:
            return BoundedPilotCommandResult(returncode=1)
        if len(self.calls) == 1 and self.fail_first:
            return BoundedPilotCommandResult(returncode=1)
        return BoundedPilotCommandResult(returncode=0)


class FakeProbe:
    def __init__(self, *, daemon="AUTHORIZED", shell="DENIED"):
        self.daemon = daemon
        self.shell = shell

    def daemon_status(self):
        return self.daemon

    def shell_status(self):
        return self.shell


def manifest():
    return canonical_bounded_pilot_helper_manifest()


def authorization():
    return prepare_bounded_pilot_bootstrap_authorization(
        manifest=manifest(),
        helper_readiness_ready=True,
    )


def test_prepare_authorization_requires_ready_gate():
    with pytest.raises(
        PermissionError,
        match="bounded_pilot_helper_gate_not_ready",
    ):
        prepare_bounded_pilot_bootstrap_authorization(
            manifest=manifest(),
            helper_readiness_ready=False,
        )


def test_authorization_is_bound_to_exact_manifest():
    auth = authorization()

    assert auth.manifest_fingerprint == manifest().fingerprint
    assert auth.helper_install_approved is True


def test_manifest_substitution_is_rejected():
    bad = replace(authorization(), manifest_fingerprint="0" * 64)

    with pytest.raises(PermissionError, match="manifest_fingerprint_mismatch"):
        BoundedPilotBootstrapExecutor().execute(
            manifest=manifest(),
            authorization=bad,
            filesystem=FakeFilesystem(),
            systemctl=FakeSystemctl(),
            authorization_probe=FakeProbe(),
        )


def test_happy_path_installs_helper_and_polkit_only():
    current = manifest()
    fs = FakeFilesystem()
    ctl = FakeSystemctl()

    result = BoundedPilotBootstrapExecutor().execute(
        manifest=current,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.succeeded
    assert fs.exists(current.helper.destination)
    assert fs.exists(current.polkit_rule.destination)
    assert ctl.calls == [
        (
            "daemon_reload",
            (
                "/usr/bin/systemctl",
                "--no-ask-password",
                "daemon-reload",
            ),
            5.0,
        )
    ]
    assert "probe:daemon:AUTHORIZED" in result.events
    assert "probe:shell:DENIED" in result.events


def test_collision_blocks_before_any_mutation():
    current = manifest()
    fs = FakeFilesystem()
    fs.files[current.helper.destination] = {
        "content": "foreign",
        "uid": 0,
        "gid": 0,
        "mode": 0o755,
    }
    ctl = FakeSystemctl()

    result = BoundedPilotBootstrapExecutor().execute(
        manifest=current,
        authorization=authorization(),
        filesystem=fs,
        systemctl=ctl,
        authorization_probe=FakeProbe(),
    )

    assert result.status == "BLOCKED"
    assert result.error == "collision:helper"
    assert len(fs.files) == 1
    assert ctl.calls == []


def test_first_install_failure_has_no_mutation_and_no_rollback():
    result = BoundedPilotBootstrapExecutor().execute(
        manifest=manifest(),
        authorization=authorization(),
        filesystem=FakeFilesystem(fail_install_role="helper"),
        systemctl=FakeSystemctl(),
        authorization_probe=FakeProbe(),
    )

    assert result.status == "FAILED_NO_MUTATION"
    assert result.rollback_errors == ()


@pytest.mark.parametrize(
    "fail_role",
    ["polkit_rule"],
)
def test_later_install_failure_rolls_back(fail_role):
    fs = FakeFilesystem(fail_install_role=fail_role)

    result = BoundedPilotBootstrapExecutor().execute(
        manifest=manifest(),
        authorization=authorization(),
        filesystem=fs,
        systemctl=FakeSystemctl(),
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLED_BACK"
    assert fs.files == {}


@pytest.mark.parametrize(
    "failure",
    [
        {"systemctl": FakeSystemctl(fail_first=True), "probe": FakeProbe()},
        {"systemctl": FakeSystemctl(), "probe": FakeProbe(daemon="DENIED")},
        {"systemctl": FakeSystemctl(), "probe": FakeProbe(shell="AUTHORIZED")},
    ],
)
def test_apply_or_probe_failure_rolls_back(failure):
    fs = FakeFilesystem()

    result = BoundedPilotBootstrapExecutor().execute(
        manifest=manifest(),
        authorization=authorization(),
        filesystem=fs,
        systemctl=failure["systemctl"],
        authorization_probe=failure["probe"],
    )

    assert result.status == "ROLLED_BACK"
    assert fs.files == {}


def test_tampered_artifact_is_never_blindly_removed():
    current = manifest()
    fs = FakeFilesystem(tamper_role="polkit_rule")

    result = BoundedPilotBootstrapExecutor().execute(
        manifest=current,
        authorization=authorization(),
        filesystem=fs,
        systemctl=FakeSystemctl(),
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLBACK_FAILED"
    assert fs.exists(current.polkit_rule.destination)
    assert any(
        "rollback_artifact_mismatch:polkit_rule" == item
        for item in result.rollback_errors
    )


def test_rollback_daemon_reload_failure_is_reported():
    fs = FakeFilesystem()

    result = BoundedPilotBootstrapExecutor().execute(
        manifest=manifest(),
        authorization=authorization(),
        filesystem=fs,
        systemctl=FakeSystemctl(fail_first=True, rollback_fail=True),
        authorization_probe=FakeProbe(),
    )

    assert result.status == "ROLLBACK_FAILED"
    assert "rollback_command_failed:daemon_reload" in result.rollback_errors


def test_executor_module_has_no_direct_host_io_or_restart_authority():
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
        '"restart"',
        '"start"',
        '"stop"',
    )

    for token in forbidden:
        assert token not in source
