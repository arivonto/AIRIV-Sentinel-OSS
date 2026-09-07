"""Strong systemd remediation identity and immutable action scope.

Phase 2.13D.D2.

No mutating systemd command is executed by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


_UNIT_RE = re.compile(
    r"^[A-Za-z0-9_.@:-]+\.service$"
)

_HEX_32_RE = re.compile(
    r"^[0-9a-fA-F]{32}$"
)

_BOOT_ID_RE = re.compile(
    r"^[0-9a-fA-F-]{36}$"
)


def _required(
    value: str,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field} must be str"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field} is required"
        )

    return value


def _canonical_hash(
    payload: dict,
) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _process_start_ticks(
    proc_stat: str,
) -> int:
    if not isinstance(
        proc_stat,
        str,
    ):
        raise TypeError(
            "proc_stat must be str"
        )

    try:
        remainder = (
            proc_stat
            .rsplit(")", 1)[1]
            .strip()
            .split()
        )
    except (
        IndexError,
        AttributeError,
    ) as exc:
        raise ValueError(
            "invalid_proc_stat"
        ) from exc

    # field 22 = process starttime.
    # remainder begins at field 3.
    if len(remainder) <= 19:
        raise ValueError(
            "invalid_proc_stat"
        )

    value = remainder[19]

    if not value.isdigit():
        raise ValueError(
            "invalid_process_start_ticks"
        )

    return int(value)


class SystemdOperation(
    str,
    Enum,
):
    RESTART = "restart"


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdManagerIdentity:
    boot_id: str
    manager_pid: int
    manager_start_ticks: int

    def __post_init__(self) -> None:
        boot_id = _required(
            self.boot_id,
            "boot_id",
        )

        if not _BOOT_ID_RE.fullmatch(
            boot_id
        ):
            raise ValueError(
                "invalid_boot_id"
            )

        if self.manager_pid <= 0:
            raise ValueError(
                "manager_pid must be positive"
            )

        if self.manager_start_ticks <= 0:
            raise ValueError(
                "manager_start_ticks must be positive"
            )

    @property
    def canonical_dict(
        self,
    ) -> dict:
        return {
            "boot_id":
                self.boot_id.lower(),

            "manager_pid":
                self.manager_pid,

            "manager_start_ticks":
                self.manager_start_ticks,
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdUnitIdentity:
    manager: SystemdManagerIdentity

    unit_name: str

    fragment_path: str
    fragment_sha256: str

    fragment_device: int
    fragment_inode: int
    fragment_uid: int
    fragment_gid: int

    def __post_init__(self) -> None:
        unit_name = _required(
            self.unit_name,
            "unit_name",
        )

        if not _UNIT_RE.fullmatch(
            unit_name
        ):
            raise ValueError(
                "invalid_systemd_service_unit_name"
            )

        fragment = Path(
            _required(
                self.fragment_path,
                "fragment_path",
            )
        )

        if not fragment.is_absolute():
            raise ValueError(
                "fragment_path must be absolute"
            )

        digest = _required(
            self.fragment_sha256,
            "fragment_sha256",
        )

        if (
            len(digest) != 64
            or any(
                char not in "0123456789abcdefABCDEF"
                for char in digest
            )
        ):
            raise ValueError(
                "invalid_fragment_sha256"
            )

        for field, value in (
            (
                "fragment_device",
                self.fragment_device,
            ),
            (
                "fragment_inode",
                self.fragment_inode,
            ),
        ):
            if (
                not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{field} must be positive"
                )

        for field, value in (
            (
                "fragment_uid",
                self.fragment_uid,
            ),
            (
                "fragment_gid",
                self.fragment_gid,
            ),
        ):
            if (
                not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{field} must be non-negative"
                )

    @property
    def component_id(
        self,
    ) -> str:
        return (
            "systemd:"
            + self.unit_name
        )

    @property
    def canonical_dict(
        self,
    ) -> dict:
        return {
            "manager":
                self.manager.canonical_dict,

            "unit_name":
                self.unit_name,

            "fragment_path":
                self.fragment_path,

            "fragment_sha256":
                self.fragment_sha256.lower(),

            "fragment_device":
                self.fragment_device,

            "fragment_inode":
                self.fragment_inode,

            "fragment_uid":
                self.fragment_uid,

            "fragment_gid":
                self.fragment_gid,
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict
        )

    @property
    def live_eligible(
        self,
    ) -> bool:
        return bool(
            self.manager.boot_id
            and self.manager.manager_pid > 0
            and self.manager.manager_start_ticks > 0
            and self.unit_name
            and self.fragment_path
            and self.fragment_sha256
            and self.fragment_device > 0
            and self.fragment_inode > 0
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdUnitSnapshot:
    identity: SystemdUnitIdentity

    load_state: str
    active_state: str
    sub_state: str
    unit_file_state: str

    main_pid: int
    invocation_id: str

    exec_main_start_timestamp_monotonic: int

    def __post_init__(self) -> None:
        for field in (
            "load_state",
            "active_state",
            "sub_state",
            "unit_file_state",
        ):
            _required(
                getattr(
                    self,
                    field,
                ),
                field,
            )

        if self.main_pid < 0:
            raise ValueError(
                "main_pid must be non-negative"
            )

        if self.invocation_id:
            if not _HEX_32_RE.fullmatch(
                self.invocation_id
            ):
                raise ValueError(
                    "invalid_invocation_id"
                )

        if (
            self.exec_main_start_timestamp_monotonic
            < 0
        ):
            raise ValueError(
                "invalid_exec_main_start_timestamp_monotonic"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdPrivilegeBoundary:
    systemctl_binary: str
    no_ask_password: bool = True
    allow_sudo: bool = False
    allow_pkexec: bool = False
    allow_shell: bool = False

    def __post_init__(self) -> None:
        binary = Path(
            _required(
                self.systemctl_binary,
                "systemctl_binary",
            )
        )

        if not binary.is_absolute():
            raise ValueError(
                "systemctl_binary must be absolute"
            )

        if self.no_ask_password is not True:
            raise ValueError(
                "systemctl must be non-interactive"
            )

        if self.allow_sudo:
            raise ValueError(
                "sudo escalation prohibited"
            )

        if self.allow_pkexec:
            raise ValueError(
                "pkexec escalation prohibited"
            )

        if self.allow_shell:
            raise ValueError(
                "shell execution prohibited"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class BoundSystemdActionScope:
    target: SystemdUnitIdentity
    operation: SystemdOperation
    privilege: SystemdPrivilegeBoundary

    expected_pre_active_state: str = "active"
    expected_post_active_state: str = "active"

    require_new_invocation: bool = True

    def __post_init__(self) -> None:
        if not isinstance(
            self.target,
            SystemdUnitIdentity,
        ):
            raise TypeError(
                "target must be SystemdUnitIdentity"
            )

        if not self.target.live_eligible:
            raise ValueError(
                "target_not_live_eligible"
            )

        if (
            self.operation
            is not SystemdOperation.RESTART
        ):
            raise ValueError(
                "unsupported_systemd_operation"
            )

        _required(
            self.expected_pre_active_state,
            "expected_pre_active_state",
        )

        _required(
            self.expected_post_active_state,
            "expected_post_active_state",
        )

    @property
    def component_id(
        self,
    ) -> str:
        return self.target.component_id

    @property
    def argv(
        self,
    ) -> tuple[str, ...]:
        return (
            self.privilege.systemctl_binary,
            "--no-ask-password",
            self.operation.value,
            self.target.unit_name,
        )

    @property
    def canonical_dict(
        self,
    ) -> dict:
        return {
            "target_fingerprint":
                self.target.fingerprint,

            "component_id":
                self.component_id,

            "operation":
                self.operation.value,

            "argv":
                list(
                    self.argv
                ),

            "expected_pre_active_state":
                self.expected_pre_active_state,

            "expected_post_active_state":
                self.expected_post_active_state,

            "require_new_invocation":
                self.require_new_invocation,

            "privilege": {
                "systemctl_binary":
                    self.privilege.systemctl_binary,

                "no_ask_password":
                    self.privilege.no_ask_password,

                "allow_sudo":
                    self.privilege.allow_sudo,

                "allow_pkexec":
                    self.privilege.allow_pkexec,

                "allow_shell":
                    self.privilege.allow_shell,
            },
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict
        )


class SystemdReadOnlyInspector:
    """Read-only exact systemd identity inspector."""

    PROPERTIES = (
        "Id",
        "LoadState",
        "ActiveState",
        "SubState",
        "UnitFileState",
        "FragmentPath",
        "MainPID",
        "InvocationID",
        "ExecMainStartTimestampMonotonic",
    )

    def __init__(
        self,
        *,
        systemctl_binary: str = "/usr/bin/systemctl",
        runner: Callable = subprocess.run,
        timeout: float = 5.0,
        read_text: Callable | None = None,
        lstat_fn: Callable = os.lstat,
        stat_fn: Callable = os.stat,
    ) -> None:
        binary = Path(
            systemctl_binary
        )

        if not binary.is_absolute():
            raise ValueError(
                "systemctl_binary must be absolute"
            )

        if (
            not isinstance(
                timeout,
                (int, float),
            )
            or isinstance(
                timeout,
                bool,
            )
            or timeout <= 0
        ):
            raise ValueError(
                "timeout must be positive"
            )

        self.systemctl_binary = (
            str(binary)
        )

        self.runner = runner
        self.timeout = float(
            timeout
        )

        self.read_text = (
            read_text
            or self._default_read_text
        )

        self.lstat_fn = lstat_fn
        self.stat_fn = stat_fn

    @staticmethod
    def _default_read_text(
        path: str,
    ) -> str:
        return Path(
            path
        ).read_text(
            encoding="utf-8"
        )

    def _manager_identity(
        self,
    ) -> SystemdManagerIdentity:
        boot_id = (
            self.read_text(
                "/proc/sys/kernel/random/boot_id"
            )
            .strip()
        )

        proc_stat = self.read_text(
            "/proc/1/stat"
        )

        return SystemdManagerIdentity(
            boot_id=boot_id,
            manager_pid=1,
            manager_start_ticks=(
                _process_start_ticks(
                    proc_stat
                )
            ),
        )

    @staticmethod
    def _parse_show(
        stdout: str,
    ) -> dict[str, str]:
        result: dict[
            str,
            str,
        ] = {}

        for line in stdout.splitlines():
            if "=" not in line:
                continue

            key, value = line.split(
                "=",
                1,
            )

            result[
                key.strip()
            ] = value.strip()

        return result

    def inspect(
        self,
        unit_name: str,
    ) -> SystemdUnitSnapshot:
        unit_name = _required(
            unit_name,
            "unit_name",
        )

        if not _UNIT_RE.fullmatch(
            unit_name
        ):
            raise ValueError(
                "invalid_systemd_service_unit_name"
            )

        command = [
            self.systemctl_binary,
            "show",
            "--no-pager",
            "--property="
            + ",".join(
                self.PROPERTIES
            ),
            unit_name,
        ]

        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            OSError,
        ) as exc:
            raise RuntimeError(
                "systemd_read_only_probe_failed"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                "systemd_read_only_probe_nonzero"
            )

        values = self._parse_show(
            result.stdout
        )

        for required in (
            "Id",
            "LoadState",
            "ActiveState",
            "SubState",
            "FragmentPath",
            "MainPID",
            "ExecMainStartTimestampMonotonic",
        ):
            if required not in values:
                raise RuntimeError(
                    "systemd_property_missing:"
                    + required
                )

        if values["Id"] != unit_name:
            raise RuntimeError(
                "systemd_unit_identity_mismatch"
            )

        if values["LoadState"] != "loaded":
            raise RuntimeError(
                "systemd_unit_not_loaded"
            )

        fragment = Path(
            values["FragmentPath"]
        )

        if not fragment.is_absolute():
            raise RuntimeError(
                "systemd_fragment_not_absolute"
            )

        try:
            lst = self.lstat_fn(
                fragment
            )
        except OSError as exc:
            raise RuntimeError(
                "systemd_fragment_lstat_failed"
            ) from exc

        if stat.S_ISLNK(
            lst.st_mode
        ):
            raise RuntimeError(
                "systemd_fragment_symlink_rejected"
            )

        if not stat.S_ISREG(
            lst.st_mode
        ):
            raise RuntimeError(
                "systemd_fragment_not_regular"
            )

        st = self.stat_fn(
            fragment
        )

        content = self.read_text(
            str(fragment)
        ).encode("utf-8")

        digest = hashlib.sha256(
            content
        ).hexdigest()

        identity = SystemdUnitIdentity(
            manager=(
                self._manager_identity()
            ),

            unit_name=unit_name,

            fragment_path=str(
                fragment
            ),

            fragment_sha256=digest,

            fragment_device=int(
                st.st_dev
            ),

            fragment_inode=int(
                st.st_ino
            ),

            fragment_uid=int(
                st.st_uid
            ),

            fragment_gid=int(
                st.st_gid
            ),
        )

        try:
            main_pid = int(
                values["MainPID"]
                or "0"
            )

            start_monotonic = int(
                values[
                    "ExecMainStartTimestampMonotonic"
                ]
                or "0"
            )

        except ValueError as exc:
            raise RuntimeError(
                "invalid_systemd_numeric_property"
            ) from exc

        return SystemdUnitSnapshot(
            identity=identity,

            load_state=(
                values["LoadState"]
            ),

            active_state=(
                values["ActiveState"]
            ),

            sub_state=(
                values["SubState"]
            ),

            unit_file_state=(
                values.get(
                    "UnitFileState",
                    "unknown",
                )
                or "unknown"
            ),

            main_pid=main_pid,

            invocation_id=(
                values.get(
                    "InvocationID",
                    "",
                )
            ),

            exec_main_start_timestamp_monotonic=(
                start_monotonic
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdRestartVerification:
    verified: bool

    same_target_identity: bool
    active_after: bool
    new_invocation: bool

    before_target_fingerprint: str
    after_target_fingerprint: str

    reason: str


class SystemdRestartVerifier:
    """Pure comparison of independently captured snapshots."""

    def verify(
        self,
        *,
        scope: BoundSystemdActionScope,
        before: SystemdUnitSnapshot,
        after: SystemdUnitSnapshot,
    ) -> SystemdRestartVerification:
        if not isinstance(
            scope,
            BoundSystemdActionScope,
        ):
            raise TypeError(
                "scope must be BoundSystemdActionScope"
            )

        same_identity = (
            before.identity.fingerprint
            == scope.target.fingerprint
            == after.identity.fingerprint
        )

        if not same_identity:
            return SystemdRestartVerification(
                verified=False,
                same_target_identity=False,
                active_after=False,
                new_invocation=False,
                before_target_fingerprint=(
                    before.identity.fingerprint
                ),
                after_target_fingerprint=(
                    after.identity.fingerprint
                ),
                reason="systemd_target_identity_changed",
            )

        if (
            before.active_state
            != scope.expected_pre_active_state
        ):
            return SystemdRestartVerification(
                verified=False,
                same_target_identity=True,
                active_after=False,
                new_invocation=False,
                before_target_fingerprint=(
                    before.identity.fingerprint
                ),
                after_target_fingerprint=(
                    after.identity.fingerprint
                ),
                reason="unexpected_pre_active_state",
            )

        active_after = (
            after.load_state == "loaded"
            and after.active_state
            == scope.expected_post_active_state
        )

        if not active_after:
            return SystemdRestartVerification(
                verified=False,
                same_target_identity=True,
                active_after=False,
                new_invocation=False,
                before_target_fingerprint=(
                    before.identity.fingerprint
                ),
                after_target_fingerprint=(
                    after.identity.fingerprint
                ),
                reason="post_restart_not_active",
            )

        new_invocation = (
            bool(
                before.invocation_id
            )
            and bool(
                after.invocation_id
            )
            and before.invocation_id
            != after.invocation_id
        )

        if (
            scope.require_new_invocation
            and not new_invocation
        ):
            return SystemdRestartVerification(
                verified=False,
                same_target_identity=True,
                active_after=True,
                new_invocation=False,
                before_target_fingerprint=(
                    before.identity.fingerprint
                ),
                after_target_fingerprint=(
                    after.identity.fingerprint
                ),
                reason="systemd_invocation_not_changed",
            )

        return SystemdRestartVerification(
            verified=True,
            same_target_identity=True,
            active_after=True,
            new_invocation=(
                new_invocation
            ),
            before_target_fingerprint=(
                before.identity.fingerprint
            ),
            after_target_fingerprint=(
                after.identity.fingerprint
            ),
            reason="verified",
        )
