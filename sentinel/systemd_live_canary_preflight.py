"""Systemd live-canary read-only preflight.

Phase 2.13D.D7A.

This module performs no systemd lifecycle mutation.
"""

from __future__ import annotations

from sentinel.polkit_noninteractive import (
    build_pkcheck_process_argv,
    classify_pkcheck_noninteractive,
    current_process_subject,
)


from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable


CANARY_UNIT = (
    "airiv-sentinel-remediation-canary.service"
)

SENTINEL_UNIT = (
    "airiv-sentinel.service"
)

CANARY_COMPONENT_ID = (
    "systemd:"
    + CANARY_UNIT
)

CANARY_FRAGMENT_PATH = (
    "/etc/systemd/system/"
    + CANARY_UNIT
)

CANARY_EXECUTABLE = (
    "/usr/bin/sleep"
)

POLKIT_MANAGE_UNITS = (
    "org.freedesktop.systemd1.manage-units"
)


CANARY_UNIT_TEXT = """\
[Unit]
Description=AIRIV Sentinel Remediation Canary

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=no
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes

[Install]
WantedBy=multi-user.target
"""


def _canonical_hash(
    payload: dict,
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return sha256(
        encoded
    ).hexdigest()


@dataclass(
    frozen=True,
    slots=True,
)
class CommandProbe:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    status: str

    def __post_init__(
        self,
    ) -> None:
        if self.status not in {
            "PASS",
            "AUTHORIZED",
            "DENIED",
            "UNKNOWN",
            "UNAVAILABLE",
        }:
            raise ValueError(
                "invalid command probe status"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdCanaryDesign:
    unit_name: str
    component_id: str
    fragment_path: str
    executable: str
    unit_text: str

    def __post_init__(
        self,
    ) -> None:
        if (
            self.unit_name
            != CANARY_UNIT
        ):
            raise ValueError(
                "non-canonical canary unit"
            )

        if (
            self.component_id
            != CANARY_COMPONENT_ID
        ):
            raise ValueError(
                "non-canonical canary component"
            )

        if (
            self.fragment_path
            != CANARY_FRAGMENT_PATH
        ):
            raise ValueError(
                "non-canonical canary fragment"
            )

        if (
            self.executable
            != CANARY_EXECUTABLE
        ):
            raise ValueError(
                "non-canonical canary executable"
            )

        if (
            self.unit_name
            == SENTINEL_UNIT
        ):
            raise ValueError(
                "canary must not be Sentinel service"
            )

        forbidden = (
            "-m sentinel",
            "sentinel.__main__",
            "sudo ",
            "pkexec ",
            "/bin/sh",
            "/bin/bash",
            "curl ",
            "wget ",
            "nc ",
            "socat ",
        )

        lowered = (
            self.unit_text.lower()
        )

        for token in forbidden:
            if token.lower() in lowered:
                raise ValueError(
                    "unsafe canary unit token: "
                    + token
                )

        if (
            "ExecStart=/usr/bin/sleep infinity"
            not in self.unit_text
        ):
            raise ValueError(
                "canonical inert workload missing"
            )

        if (
            "Restart=no"
            not in self.unit_text
        ):
            raise ValueError(
                "canary restart loop must be disabled"
            )

    @property
    def unit_sha256(
        self,
    ) -> str:
        return sha256(
            self.unit_text.encode(
                "utf-8"
            )
        ).hexdigest()

    @property
    def candidate_restart_argv(
        self,
    ) -> tuple[str, ...]:
        return (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "restart",
            self.unit_name,
        )

    def canonical_dict(
        self,
    ) -> dict:
        return {
            "unit_name":
                self.unit_name,

            "component_id":
                self.component_id,

            "fragment_path":
                self.fragment_path,

            "executable":
                self.executable,

            "unit_sha256":
                self.unit_sha256,

            "candidate_restart_argv":
                list(
                    self.candidate_restart_argv
                ),
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict()
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdCanaryPreflight:
    design: SystemdCanaryDesign

    executable_ok: bool

    fragment_collision: bool

    loaded_unit_collision: bool

    sentinel_distinct: bool

    offline_verify: CommandProbe

    sudo_probe: CommandProbe

    polkit_probe: CommandProbe

    privilege_result: str

    @property
    def host_collision_free(
        self,
    ) -> bool:
        return (
            not self.fragment_collision
            and not self.loaded_unit_collision
        )

    @property
    def design_ready(
        self,
    ) -> bool:
        return (
            self.executable_ok
            and self.sentinel_distinct
            and self.host_collision_free
            and self.offline_verify.status
            == "PASS"
        )

    @property
    def live_effect_authorized(
        self,
    ) -> bool:
        return (
            self.design_ready
            and self.privilege_result
            == "AUTHORIZED"
        )

    @property
    def fail_closed(
        self,
    ) -> bool:
        return (
            not self.live_effect_authorized
        )

    def canonical_dict(
        self,
    ) -> dict:
        return {
            "design":
                self.design.canonical_dict(),

            "design_fingerprint":
                self.design.fingerprint,

            "executable_ok":
                self.executable_ok,

            "fragment_collision":
                self.fragment_collision,

            "loaded_unit_collision":
                self.loaded_unit_collision,

            "sentinel_distinct":
                self.sentinel_distinct,

            "offline_verify_status":
                self.offline_verify.status,

            "sudo_status":
                self.sudo_probe.status,

            "polkit_status":
                self.polkit_probe.status,

            "privilege_result":
                self.privilege_result,

            "design_ready":
                self.design_ready,

            "live_effect_authorized":
                self.live_effect_authorized,

            "fail_closed":
                self.fail_closed,
        }


def canonical_canary_design(
) -> SystemdCanaryDesign:
    return SystemdCanaryDesign(
        unit_name=CANARY_UNIT,

        component_id=(
            CANARY_COMPONENT_ID
        ),

        fragment_path=(
            CANARY_FRAGMENT_PATH
        ),

        executable=(
            CANARY_EXECUTABLE
        ),

        unit_text=(
            CANARY_UNIT_TEXT
        ),
    )


def _run_probe(
    runner: Callable,
    argv: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess:
    return runner(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _offline_verify(
    *,
    design: SystemdCanaryDesign,

    runner: Callable,

    timeout: float,
) -> CommandProbe:
    binary = shutil.which(
        "systemd-analyze"
    )

    if binary is None:
        return CommandProbe(
            argv=(),
            returncode=None,
            stdout="",
            stderr="",
            status="UNAVAILABLE",
        )

    with tempfile.TemporaryDirectory(
        prefix="airiv-d7a-unit-"
    ) as root:
        unit_path = (
            Path(root)
            / design.unit_name
        )

        unit_path.write_text(
            design.unit_text,
            encoding="utf-8",
        )

        try:
            result = _run_probe(
                runner,
                [
                    binary,
                    "verify",
                    str(unit_path),
                ],
                timeout=timeout,
            )

        except (
            OSError,
            subprocess.TimeoutExpired,
        ) as exc:
            return CommandProbe(
                argv=(
                    binary,
                    "verify",
                    str(unit_path),
                ),
                returncode=None,
                stdout="",
                stderr=str(exc),
                status="UNKNOWN",
            )

        return CommandProbe(
            argv=(
                binary,
                "verify",
                str(unit_path),
            ),

            returncode=(
                result.returncode
            ),

            stdout=(
                result.stdout
            ),

            stderr=(
                result.stderr
            ),

            status=(
                "PASS"
                if result.returncode == 0
                else "UNKNOWN"
            ),
        )


def _loaded_collision(
    *,
    design: SystemdCanaryDesign,

    runner: Callable,

    timeout: float,
) -> bool:
    binary = shutil.which(
        "systemctl"
    )

    if binary is None:
        # Fail closed: if systemctl itself is unavailable,
        # collision state cannot be proven absent.
        return True

    try:
        result = _run_probe(
            runner,
            [
                binary,
                "show",
                "--no-pager",
                "--property=LoadState",
                "--value",
                design.unit_name,
            ],
            timeout=timeout,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ):
        return True

    value = (
        result.stdout
        .strip()
        .lower()
    )

    if value in {
        "",
        "not-found",
    }:
        return False

    return True


def _sudo_probe(
    *,
    runner: Callable,

    timeout: float,
) -> CommandProbe:
    binary = shutil.which(
        "sudo"
    )

    if binary is None:
        return CommandProbe(
            argv=(),
            returncode=None,
            stdout="",
            stderr="",
            status="UNAVAILABLE",
        )

    argv = [
        binary,
        "-n",
        "true",
    ]

    try:
        result = _run_probe(
            runner,
            argv,
            timeout=timeout,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        return CommandProbe(
            argv=tuple(argv),
            returncode=None,
            stdout="",
            stderr=str(exc),
            status="UNKNOWN",
        )

    return CommandProbe(
        argv=tuple(argv),

        returncode=(
            result.returncode
        ),

        stdout=(
            result.stdout
        ),

        stderr=(
            result.stderr
        ),

        status=(
            "AUTHORIZED"
            if result.returncode == 0
            else "DENIED"
        ),
    )


def _polkit_probe(
    *,
    runner: Callable,

    timeout: float,
) -> CommandProbe:
    binary = shutil.which(
        "pkcheck"
    )

    if binary is None:
        return CommandProbe(
            argv=(),
            returncode=None,
            stdout="",
            stderr="",
            status="UNAVAILABLE",
        )

    # No --allow-user-interaction flag:
    # this is intentionally non-interactive.
    argv = list(
        build_pkcheck_process_argv(
            pkcheck_binary=binary,
            action_id=POLKIT_MANAGE_UNITS,
            subject=current_process_subject(),
        )
    )

    try:
        result = _run_probe(
            runner,
            argv,
            timeout=timeout,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        return CommandProbe(
            argv=tuple(argv),
            returncode=None,
            stdout="",
            stderr=str(exc),
            status="UNKNOWN",
        )

    status = (
        classify_pkcheck_noninteractive(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    )

    return CommandProbe(
        argv=tuple(argv),

        returncode=(
            result.returncode
        ),

        stdout=(
            result.stdout
        ),

        stderr=(
            result.stderr
        ),

        status=status,
    )


def inspect_canary_preflight(
    *,
    runner:
        Callable = subprocess.run,

    timeout:
        float = 5.0,
) -> SystemdCanaryPreflight:
    if timeout <= 0:
        raise ValueError(
            "timeout must be positive"
        )

    design = (
        canonical_canary_design()
    )

    executable = Path(
        design.executable
    )

    executable_ok = (
        executable.is_absolute()
        and executable.is_file()
        and os.access(
            executable,
            os.X_OK,
        )
    )

    fragment_collision = (
        Path(
            design.fragment_path
        ).exists()
    )

    loaded_unit_collision = (
        _loaded_collision(
            design=design,
            runner=runner,
            timeout=timeout,
        )
    )

    sentinel_distinct = (
        design.unit_name
        != SENTINEL_UNIT

        and design.component_id
        != "systemd:"
        + SENTINEL_UNIT

        and design.fragment_path
        != (
            "/etc/systemd/system/"
            + SENTINEL_UNIT
        )
    )

    offline_verify = (
        _offline_verify(
            design=design,
            runner=runner,
            timeout=timeout,
        )
    )

    sudo_probe = (
        _sudo_probe(
            runner=runner,
            timeout=timeout,
        )
    )

    polkit_probe = (
        _polkit_probe(
            runner=runner,
            timeout=timeout,
        )
    )

    # Future effect argv contains neither sudo nor pkexec.
    # Therefore sudo authorization alone cannot authorize it.
    if (
        polkit_probe.status
        == "AUTHORIZED"
    ):
        privilege_result = (
            "AUTHORIZED"
        )

    elif (
        polkit_probe.status
        in {
            "DENIED",
            "UNAVAILABLE",
        }
    ):
        privilege_result = (
            "DENIED"
        )

    else:
        privilege_result = (
            "UNKNOWN"
        )

    return SystemdCanaryPreflight(
        design=design,

        executable_ok=(
            executable_ok
        ),

        fragment_collision=(
            fragment_collision
        ),

        loaded_unit_collision=(
            loaded_unit_collision
        ),

        sentinel_distinct=(
            sentinel_distinct
        ),

        offline_verify=(
            offline_verify
        ),

        sudo_probe=(
            sudo_probe
        ),

        polkit_probe=(
            polkit_probe
        ),

        privilege_result=(
            privilege_result
        ),
    )
