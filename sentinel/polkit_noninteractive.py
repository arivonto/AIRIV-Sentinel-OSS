"""Canonical non-interactive polkit process identity and classification."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


AUTH_REQUIRED_MARKERS = (
    "authorization requires authentication",
    "authentication is required",
)

POLKIT_RESULT_AUTH_ADMIN = (
    "polkit\\56result=auth_admin"
)


@dataclass(frozen=True, slots=True)
class PolkitProcessSubject:
    pid: int
    start_time: int
    uid: int

    def __post_init__(self) -> None:
        if self.pid <= 0:
            raise ValueError(
                "pid must be positive"
            )

        if self.start_time <= 0:
            raise ValueError(
                "start_time must be positive"
            )

        if self.uid < 0:
            raise ValueError(
                "uid must not be negative"
            )

    @property
    def process_argument(self) -> str:
        return (
            f"{self.pid},"
            f"{self.start_time},"
            f"{self.uid}"
        )


def process_start_time(
    pid: int,
    *,
    proc_root: str | Path = "/proc",
) -> int:
    if pid <= 0:
        raise ValueError(
            "pid must be positive"
        )

    path = (
        Path(proc_root)
        / str(pid)
        / "stat"
    )

    raw = path.read_text(
        encoding="utf-8"
    ).strip()

    # /proc/<pid>/stat field 2 is enclosed in parentheses and may
    # contain spaces. Split only after the final ')'.
    close = raw.rfind(")")

    if close < 0:
        raise RuntimeError(
            "invalid proc stat format"
        )

    remainder = raw[
        close + 1:
    ].strip().split()

    # After removing fields 1 and 2, remainder[0] is field 3.
    # Field 22 therefore maps to remainder index 19.
    if len(remainder) <= 19:
        raise RuntimeError(
            "proc stat missing start time"
        )

    start_time = int(
        remainder[19]
    )

    if start_time <= 0:
        raise RuntimeError(
            "invalid process start time"
        )

    return start_time


def current_process_subject(
) -> PolkitProcessSubject:
    pid = os.getpid()

    return PolkitProcessSubject(
        pid=pid,
        start_time=process_start_time(
            pid
        ),
        uid=os.getuid(),
    )


def build_pkcheck_process_argv(
    *,
    pkcheck_binary: str,
    action_id: str,
    subject: PolkitProcessSubject,
) -> tuple[str, ...]:
    if not isinstance(
        pkcheck_binary,
        str,
    ) or not pkcheck_binary.strip():
        raise ValueError(
            "pkcheck_binary is required"
        )

    if not Path(
        pkcheck_binary
    ).is_absolute():
        raise ValueError(
            "pkcheck_binary must be absolute"
        )

    if not isinstance(
        action_id,
        str,
    ) or not action_id.strip():
        raise ValueError(
            "action_id is required"
        )

    if not isinstance(
        subject,
        PolkitProcessSubject,
    ):
        raise TypeError(
            "subject must be PolkitProcessSubject"
        )

    return (
        pkcheck_binary,
        "--action-id",
        action_id,
        "--process",
        subject.process_argument,
    )


def classify_pkcheck_noninteractive(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
) -> str:
    if not isinstance(
        returncode,
        int,
    ):
        raise TypeError(
            "returncode must be int"
        )

    if returncode == 0:
        return "AUTHORIZED"

    combined = (
        f"{stdout}\n{stderr}"
    ).lower()

    if any(
        marker
        in combined
        for marker
        in AUTH_REQUIRED_MARKERS
    ):
        return "DENIED"

    if (
        POLKIT_RESULT_AUTH_ADMIN.lower()
        in combined
    ):
        return "DENIED"

    if returncode == 1:
        return "DENIED"

    return "UNKNOWN"
