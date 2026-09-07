"""Independent TMUX server-generation verification."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sentinel.live_remediation_safety import (
    TmuxTargetIdentity,
)


_GENERATION = re.compile(
    r"^uid=(?P<uid>[0-9]+);"
    r"pid=(?P<pid>[0-9]+);"
    r"start=(?P<start>[0-9]+)$"
)


@dataclass(
    frozen=True,
    slots=True,
)
class TmuxServerGenerationVerification:
    verified: bool
    server_socket: str
    expected_generation: str
    observed_generation: str | None
    reason: str


class TmuxServerGenerationVerifier:
    """Independently verify the TMUX server generation."""

    def __init__(
        self,
        *,
        runner: Callable = subprocess.run,
        stat_fn: Callable = os.stat,
        proc_stat_reader: Callable[[int], str] | None = None,
    ) -> None:
        self._runner = runner
        self._stat = stat_fn
        self._proc_stat_reader = (
            proc_stat_reader
            or self._default_proc_stat_reader
        )

    @staticmethod
    def _default_proc_stat_reader(
        pid: int,
    ) -> str:
        return Path(
            f"/proc/{pid}/stat"
        ).read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _start_ticks(
        text: str,
    ) -> str | None:
        try:
            remainder = (
                text.rsplit(
                    ")",
                    1,
                )[1]
                .strip()
                .split()
            )
        except (
            IndexError,
            AttributeError,
        ):
            return None

        if len(remainder) <= 19:
            return None

        value = remainder[19]

        if not value.isdigit():
            return None

        return value

    @staticmethod
    def _expected(
        generation: str,
    ) -> tuple[int, int, str] | None:
        if not isinstance(
            generation,
            str,
        ):
            return None

        match = _GENERATION.fullmatch(
            generation
        )

        if match is None:
            return None

        return (
            int(match.group("uid")),
            int(match.group("pid")),
            match.group("start"),
        )

    def verify(
        self,
        identity: TmuxTargetIdentity,
        *,
        timeout: float = 5.0,
    ) -> TmuxServerGenerationVerification:
        if not isinstance(
            identity,
            TmuxTargetIdentity,
        ):
            raise TypeError(
                "identity must be TmuxTargetIdentity"
            )

        if not identity.live_eligible:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=(
                    identity.server_generation
                    or ""
                ),
                observed_generation=None,
                reason="target_not_live_eligible",
            )

        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or timeout <= 0
        ):
            raise ValueError(
                "timeout must be positive"
            )

        parsed = self._expected(
            identity.server_generation
        )

        if parsed is None:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=(
                    identity.server_generation
                    or ""
                ),
                observed_generation=None,
                reason="invalid_expected_generation",
            )

        (
            expected_uid,
            expected_pid,
            expected_start,
        ) = parsed

        command = [
            "tmux",
            "-S",
            identity.server_socket,
            "display-message",
            "-p",
            "#{pid}",
        ]

        try:
            result = self._runner(
                command,
                capture_output=True,
                text=True,
                timeout=float(timeout),
                check=False,
            )
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            OSError,
        ):
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=None,
                reason="server_probe_failed",
            )

        if result.returncode != 0:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=None,
                reason="server_probe_nonzero",
            )

        pid_text = result.stdout.strip()

        if not pid_text.isdigit():
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=None,
                reason="invalid_server_pid",
            )

        observed_pid = int(pid_text)

        if observed_pid != expected_pid:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=(
                    f"pid={observed_pid}"
                ),
                reason="server_pid_mismatch",
            )

        try:
            socket_uid = self._stat(
                identity.server_socket
            ).st_uid

            process_uid = self._stat(
                f"/proc/{observed_pid}"
            ).st_uid

            process_stat = (
                self._proc_stat_reader(
                    observed_pid
                )
            )

        except (
            FileNotFoundError,
            PermissionError,
            OSError,
        ):
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=None,
                reason="server_generation_probe_failed",
            )

        start_ticks = self._start_ticks(
            process_stat
        )

        if start_ticks is None:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=None,
                reason="invalid_process_start_identity",
            )

        observed_generation = (
            f"uid={process_uid};"
            f"pid={observed_pid};"
            f"start={start_ticks}"
        )

        if socket_uid != process_uid:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=observed_generation,
                reason="socket_process_uid_mismatch",
            )

        if process_uid != expected_uid:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=observed_generation,
                reason="server_uid_mismatch",
            )

        if start_ticks != expected_start:
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=observed_generation,
                reason="server_start_identity_mismatch",
            )

        if (
            observed_generation
            != identity.server_generation
        ):
            return TmuxServerGenerationVerification(
                verified=False,
                server_socket=identity.server_socket,
                expected_generation=identity.server_generation,
                observed_generation=observed_generation,
                reason="server_generation_mismatch",
            )

        return TmuxServerGenerationVerification(
            verified=True,
            server_socket=identity.server_socket,
            expected_generation=identity.server_generation,
            observed_generation=observed_generation,
            reason="verified",
        )
