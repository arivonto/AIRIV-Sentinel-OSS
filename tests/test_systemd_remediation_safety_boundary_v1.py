from __future__ import annotations

import stat
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope,
    SystemdManagerIdentity,
    SystemdOperation,
    SystemdPrivilegeBoundary,
    SystemdReadOnlyInspector,
    SystemdRestartVerifier,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


BOOT = (
    "11111111-2222-3333-4444-555555555555"
)

FRAGMENT = (
    "/etc/systemd/system/example.service"
)

DIGEST = "a" * 64


def manager():
    return SystemdManagerIdentity(
        boot_id=BOOT,
        manager_pid=1,
        manager_start_ticks=100,
    )


def identity(
    *,
    digest=DIGEST,
):
    return SystemdUnitIdentity(
        manager=manager(),

        unit_name="example.service",

        fragment_path=FRAGMENT,
        fragment_sha256=digest,

        fragment_device=10,
        fragment_inode=20,
        fragment_uid=0,
        fragment_gid=0,
    )


def scope():
    return BoundSystemdActionScope(
        target=identity(),

        operation=(
            SystemdOperation.RESTART
        ),

        privilege=(
            SystemdPrivilegeBoundary(
                systemctl_binary=(
                    "/usr/bin/systemctl"
                )
            )
        ),
    )


def snapshot(
    *,
    target=None,
    active="active",
    invocation="a" * 32,
    pid=1000,
    started=10000,
):
    return SystemdUnitSnapshot(
        identity=(
            target
            or identity()
        ),

        load_state="loaded",
        active_state=active,
        sub_state=(
            "running"
            if active == "active"
            else "failed"
        ),
        unit_file_state="enabled",
        main_pid=pid,
        invocation_id=invocation,
        exec_main_start_timestamp_monotonic=started,
    )


def test_unit_identity_has_exact_component_id():
    target = identity()

    assert (
        target.component_id
        == "systemd:example.service"
    )

    assert target.live_eligible

    assert len(
        target.fingerprint
    ) == 64


def test_invalid_unit_name_rejected():
    with pytest.raises(
        ValueError,
        match="invalid_systemd_service_unit_name",
    ):
        SystemdUnitIdentity(
            manager=manager(),
            unit_name="../../evil",
            fragment_path=FRAGMENT,
            fragment_sha256=DIGEST,
            fragment_device=1,
            fragment_inode=2,
            fragment_uid=0,
            fragment_gid=0,
        )


def test_initial_operation_surface_is_restart_only():
    assert list(
        SystemdOperation
    ) == [
        SystemdOperation.RESTART
    ]


def test_exact_immutable_restart_argv():
    value = scope()

    assert value.argv == (
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        "example.service",
    )

    assert isinstance(
        value.argv,
        tuple,
    )

    assert "sudo" not in value.argv
    assert "pkexec" not in value.argv


def test_privilege_escalation_rejected():
    with pytest.raises(
        ValueError,
        match="sudo escalation prohibited",
    ):
        SystemdPrivilegeBoundary(
            systemctl_binary=(
                "/usr/bin/systemctl"
            ),
            allow_sudo=True,
        )

    with pytest.raises(
        ValueError,
        match="pkexec escalation prohibited",
    ):
        SystemdPrivilegeBoundary(
            systemctl_binary=(
                "/usr/bin/systemctl"
            ),
            allow_pkexec=True,
        )

    with pytest.raises(
        ValueError,
        match="shell execution prohibited",
    ):
        SystemdPrivilegeBoundary(
            systemctl_binary=(
                "/usr/bin/systemctl"
            ),
            allow_shell=True,
        )


def proc_stat():
    remainder = [
        "S",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "100",
        "0",
    ]

    return (
        "1 (systemd) "
        + " ".join(remainder)
    )


def test_read_only_inspector_uses_systemctl_show_only():
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,

            stdout=(
                "Id=example.service\n"
                "LoadState=loaded\n"
                "ActiveState=active\n"
                "SubState=running\n"
                "UnitFileState=enabled\n"
                f"FragmentPath={FRAGMENT}\n"
                "MainPID=1000\n"
                f"InvocationID={'a' * 32}\n"
                "ExecMainStartTimestampMonotonic=10000\n"
            ),

            stderr="",
        )
    )

    contents = {
        "/proc/sys/kernel/random/boot_id":
            BOOT,

        "/proc/1/stat":
            proc_stat(),

        FRAGMENT:
            "[Service]\nExecStart=/bin/true\n",
    }

    regular_mode = (
        stat.S_IFREG
        | 0o644
    )

    inspector = (
        SystemdReadOnlyInspector(
            runner=run,

            read_text=lambda path: (
                contents[path]
            ),

            lstat_fn=lambda path: (
                SimpleNamespace(
                    st_mode=regular_mode
                )
            ),

            stat_fn=lambda path: (
                SimpleNamespace(
                    st_dev=10,
                    st_ino=20,
                    st_uid=0,
                    st_gid=0,
                )
            ),
        )
    )

    value = inspector.inspect(
        "example.service"
    )

    assert (
        value.identity.unit_name
        == "example.service"
    )

    command = (
        run.call_args.args[0]
    )

    assert command[0:3] == [
        "/usr/bin/systemctl",
        "show",
        "--no-pager",
    ]

    assert command[-1] == (
        "example.service"
    )

    assert not any(
        item in command
        for item in (
            "restart",
            "start",
            "stop",
        )
    )

    assert (
        run.call_args.kwargs[
            "timeout"
        ]
        == 5.0
    )

    assert (
        run.call_args.kwargs[
            "check"
        ]
        is False
    )

    assert "shell" not in (
        run.call_args.kwargs
    )


def test_fragment_symlink_fails_closed():
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,

            stdout=(
                "Id=example.service\n"
                "LoadState=loaded\n"
                "ActiveState=active\n"
                "SubState=running\n"
                "UnitFileState=enabled\n"
                f"FragmentPath={FRAGMENT}\n"
                "MainPID=1000\n"
                f"InvocationID={'a' * 32}\n"
                "ExecMainStartTimestampMonotonic=10000\n"
            ),

            stderr="",
        )
    )

    inspector = (
        SystemdReadOnlyInspector(
            runner=run,

            read_text=lambda path: (
                BOOT
                if path.endswith(
                    "boot_id"
                )
                else proc_stat()
            ),

            lstat_fn=lambda path: (
                SimpleNamespace(
                    st_mode=(
                        stat.S_IFLNK
                        | 0o777
                    )
                )
            ),
        )
    )

    with pytest.raises(
        RuntimeError,
        match="fragment_symlink_rejected",
    ):
        inspector.inspect(
            "example.service"
        )


def test_restart_verification_requires_same_target():
    before = snapshot()

    changed = identity(
        digest="b" * 64
    )

    after = snapshot(
        target=changed,
        invocation="b" * 32,
    )

    result = (
        SystemdRestartVerifier()
        .verify(
            scope=scope(),
            before=before,
            after=after,
        )
    )

    assert not result.verified

    assert (
        result.reason
        == "systemd_target_identity_changed"
    )


def test_restart_verification_requires_active_after():
    before = snapshot()

    after = snapshot(
        active="failed",
        invocation="b" * 32,
    )

    result = (
        SystemdRestartVerifier()
        .verify(
            scope=scope(),
            before=before,
            after=after,
        )
    )

    assert not result.verified

    assert (
        result.reason
        == "post_restart_not_active"
    )


def test_restart_verification_requires_new_invocation():
    before = snapshot(
        invocation="a" * 32
    )

    after = snapshot(
        invocation="a" * 32,
        pid=1001,
    )

    result = (
        SystemdRestartVerifier()
        .verify(
            scope=scope(),
            before=before,
            after=after,
        )
    )

    assert not result.verified

    assert (
        result.reason
        == "systemd_invocation_not_changed"
    )


def test_restart_verification_success():
    before = snapshot(
        invocation="a" * 32,
        pid=1000,
    )

    after = snapshot(
        invocation="b" * 32,
        pid=1001,
        started=20000,
    )

    result = (
        SystemdRestartVerifier()
        .verify(
            scope=scope(),
            before=before,
            after=after,
        )
    )

    assert result.verified
    assert result.same_target_identity
    assert result.active_after
    assert result.new_invocation
    assert result.reason == "verified"


def test_scope_fingerprint_binds_operation_and_target():
    value = scope()

    assert len(
        value.fingerprint
    ) == 64

    assert (
        value.canonical_dict[
            "target_fingerprint"
        ]
        == value.target.fingerprint
    )

    assert (
        value.canonical_dict[
            "operation"
        ]
        == "restart"
    )


def test_no_subprocess_during_scope_construction(
    monkeypatch,
):
    def forbidden(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "scope construction must not execute"
        )

    monkeypatch.setattr(
        "subprocess.run",
        forbidden,
    )

    value = scope()

    assert (
        value.argv[2]
        == "restart"
    )
