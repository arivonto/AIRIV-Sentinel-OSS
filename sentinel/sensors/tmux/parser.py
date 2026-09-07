"""Deterministic TMUX telemetry collector.

Boundary:
    TMUX -> raw observation

Phase 2.13C.1C:
    Production observations preserve strong TMUX endpoint identity.

Important:
    ``run_id`` is intentionally NOT created here. A run ID belongs to
    one controlled remediation run, not to a monitoring/sensor cycle.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


class TmuxStateParserV11:
    """
    Deterministic tmux telemetry collector.

    This module does not:
        - resolve AIRIV agent identity
        - classify jobs
        - determine STUCK
        - determine WAITING
        - determine FAILED
        - determine COMPLETED
        - authorize remediation
        - generate remediation run IDs
    """

    # PHASE_213C1C_STRONG_TMUX_SENSOR

    def __init__(
        self,
        target_session: str = "airiv",
        capture_lines: int = 50,
        server_socket: str | None = None,
    ):
        self.target_session = target_session
        self.capture_lines = capture_lines

        configured_socket = (
            server_socket
            or os.environ.get(
                "AIRIV_SENTINEL_TMUX_SOCKET"
            )
        )

        self.server_socket = (
            configured_socket.strip()
            if isinstance(configured_socket, str)
            and configured_socket.strip()
            else None
        )

        self._pane_history: Dict[str, Dict] = {}

    def _run_tmux_cmd(
        self,
        args: List[str],
        timeout: int = 10,
        *,
        server_socket: str | None = None,
    ) -> Optional[str]:
        command = ["tmux"]

        socket = (
            server_socket
            if server_socket is not None
            else self.server_socket
        )

        if socket:
            command.extend(
                [
                    "-S",
                    socket,
                ]
            )

        command.extend(args)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )
            return result.stdout

        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
            OSError,
        ):
            return None

    @staticmethod
    def _process_start_ticks(
        pid: int,
    ) -> Optional[str]:
        """
        Return Linux /proc process start ticks.

        The value is stable for one process generation and prevents PID
        reuse from being mistaken for the same TMUX server.
        """

        try:
            text = Path(
                f"/proc/{pid}/stat"
            ).read_text(
                encoding="utf-8"
            )

            # comm may contain whitespace. Everything after the final ')'
            # begins with field 3 (state). starttime is field 22,
            # therefore index 19 in this remainder.
            remainder = text.rsplit(
                ")",
                1,
            )[1].strip().split()

            if len(remainder) <= 19:
                return None

            value = remainder[19]

            if not value.isdigit():
                return None

            return value

        except (
            FileNotFoundError,
            PermissionError,
            OSError,
            IndexError,
        ):
            return None

    @classmethod
    def _server_generation(
        cls,
        socket_path: str,
        pid: int,
    ) -> Optional[str]:
        """
        Build validated TMUX server generation identity.

        Canonical representation:
            uid=<uid>;pid=<pid>;start=<linux_start_ticks>
        """

        if (
            not isinstance(socket_path, str)
            or not socket_path.strip()
        ):
            return None

        if not isinstance(pid, int) or pid <= 0:
            return None

        try:
            socket_stat = os.stat(
                socket_path
            )

            if not stat.S_ISSOCK(
                socket_stat.st_mode
            ):
                return None

            process_stat = os.stat(
                f"/proc/{pid}"
            )

            # Socket owner and server process owner must match.
            if (
                socket_stat.st_uid
                != process_stat.st_uid
            ):
                return None

            start_ticks = (
                cls._process_start_ticks(pid)
            )

            if start_ticks is None:
                return None

            return (
                f"uid={process_stat.st_uid};"
                f"pid={pid};"
                f"start={start_ticks}"
            )

        except (
            FileNotFoundError,
            PermissionError,
            OSError,
        ):
            return None

    def _resolve_server_identity(
        self,
    ) -> Optional[tuple[str, str]]:
        """
        Resolve the currently selected TMUX server.

        Discovery may use the configured socket or TMUX default server.
        After discovery all collection calls use the explicit returned
        socket path.
        """

        output = self._run_tmux_cmd(
            [
                "display-message",
                "-p",
                "#{socket_path}\t#{pid}",
            ],
            timeout=5,
            server_socket=self.server_socket,
        )

        if output is None:
            return None

        fields = output.strip().split(
            "\t"
        )

        if len(fields) != 2:
            return None

        socket_path = fields[0].strip()
        pid_text = fields[1].strip()

        if (
            not socket_path
            or not pid_text.isdigit()
        ):
            return None

        pid = int(pid_text)

        # If an explicit socket was configured, discovery must resolve
        # to that exact endpoint.
        if self.server_socket is not None:
            try:
                configured = os.path.realpath(
                    self.server_socket
                )
                resolved = os.path.realpath(
                    socket_path
                )
            except OSError:
                return None

            if configured != resolved:
                return None

        generation = self._server_generation(
            socket_path,
            pid,
        )

        if generation is None:
            return None

        return (
            socket_path,
            generation,
        )

    def _server_generation_matches(
        self,
        socket_path: str,
        expected_generation: str,
    ) -> bool:
        """
        Revalidate server generation after collection.

        If the TMUX server restarts while data is being collected,
        observations fail closed as non-live-eligible.
        """

        output = self._run_tmux_cmd(
            [
                "display-message",
                "-p",
                "#{pid}",
            ],
            timeout=5,
            server_socket=socket_path,
        )

        if output is None:
            return False

        pid_text = output.strip()

        if not pid_text.isdigit():
            return False

        generation = self._server_generation(
            socket_path,
            int(pid_text),
        )

        return generation == expected_generation

    def capture_pane_content(
        self,
        pane_id: str,
        *,
        server_socket: str | None = None,
    ) -> Optional[str]:
        return self._run_tmux_cmd(
            [
                "capture-pane",
                "-p",
                "-t",
                pane_id,
                "-S",
                f"-{self.capture_lines}",
            ],
            timeout=5,
            server_socket=server_socket,
        )

    @staticmethod
    def compute_output_hash(
        content: str,
    ) -> str:
        return hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

    def _list_panes(
        self,
        *,
        server_socket: str | None = None,
    ) -> Optional[str]:
        # Native session/window IDs are deliberately collected in
        # addition to human-readable names.
        format_str = (
            "#{session_id}\t"
            "#{session_name}\t"
            "#{window_id}\t"
            "#{window_index}\t"
            "#{window_name}\t"
            "#{pane_index}\t"
            "#{pane_id}\t"
            "#{pane_active}\t"
            "#{pane_dead}\t"
            "#{pane_current_command}\t"
            "#{pane_pid}"
        )

        return self._run_tmux_cmd(
            [
                "list-panes",
                "-a",
                "-t",
                self.target_session,
                "-F",
                format_str,
            ],
            server_socket=server_socket,
        )

    def inspect_panes(
        self,
    ) -> List[Dict]:
        # PHASE_213C1C_HEADLESS_COMPAT
        #
        # Preserve the established sensor contract:
        # an unavailable TMUX endpoint is detected by the canonical
        # list-panes probe and safely produces no observations.
        #
        # Strong identity resolution happens only after reachability
        # is established. If identity is resolved, panes are listed
        # again through that exact socket so pre-resolution telemetry
        # can never be associated with a different server generation.
        raw_output = self._list_panes(
            server_socket=self.server_socket,
        )

        if raw_output is None:
            return []

        resolved = (
            self._resolve_server_identity()
        )

        if resolved is None:
            server_socket = self.server_socket
            server_generation = None
        else:
            (
                server_socket,
                server_generation,
            ) = resolved

            raw_output = self._list_panes(
                server_socket=server_socket,
            )

            if raw_output is None:
                return []

        captured_at = datetime.now(
            timezone.utc
        ).isoformat()

        observations: List[Dict] = []

        for line in raw_output.splitlines():
            if not line.strip():
                continue

            parts = line.split("\t")

            # Backward-compatible parsing for old test fixtures.
            # Legacy records remain observable but can never be strong
            # live-remediation targets because session_id/window_id are
            # absent.
            if len(parts) == 11:
                (
                    session_id,
                    session_name,
                    window_id,
                    window_index,
                    window_name,
                    pane_index,
                    pane_id,
                    pane_active,
                    pane_dead,
                    current_command,
                    pane_pid,
                ) = parts

            elif len(parts) == 9:
                (
                    session_name,
                    window_index,
                    window_name,
                    pane_index,
                    pane_id,
                    pane_active,
                    pane_dead,
                    current_command,
                    pane_pid,
                ) = parts

                session_id = None
                window_id = None

            else:
                continue

            content = self.capture_pane_content(
                pane_id,
                server_socket=server_socket,
            )

            capture_ok = content is not None

            if content is None:
                content = ""

            current_hash = (
                self.compute_output_hash(
                    content
                )
            )

            previous_record = (
                self._pane_history.get(
                    pane_id
                )
            )

            first_observation = (
                previous_record is None
            )

            previous_hash = (
                previous_record.get(
                    "output_sha256"
                )
                if previous_record
                else None
            )

            previous_command = (
                previous_record.get(
                    "current_command"
                )
                if previous_record
                else None
            )

            output_changed = (
                not first_observation
                and previous_hash
                != current_hash
            )

            self._pane_history[
                pane_id
            ] = {
                "output_sha256":
                    current_hash,
                "current_command":
                    current_command,
                "captured_at":
                    captured_at,
            }

            identity_valid = all(
                (
                    server_socket,
                    server_generation,
                    session_id,
                    session_name,
                    window_id,
                    pane_id,
                )
            )

            identity = {
                "server_socket":
                    server_socket,
                "server_generation":
                    server_generation,
                "session_id":
                    session_id,
                "session_name":
                    session_name,
                "window_id":
                    window_id,
                "pane_id":
                    pane_id,
            }

            observations.append(
                {
                    "source": "TMUX",
                    "captured_at":
                        captured_at,

                    "server_socket":
                        server_socket,
                    "server_generation":
                        server_generation,

                    "session_id":
                        session_id,
                    "session_name":
                        session_name,

                    "window_id":
                        window_id,
                    "window_index": (
                        int(window_index)
                        if window_index.isdigit()
                        else None
                    ),
                    "window_name":
                        window_name,

                    "pane_index": (
                        int(pane_index)
                        if pane_index.isdigit()
                        else None
                    ),
                    "pane_id":
                        pane_id,
                    "pane_active":
                        pane_active == "1",
                    "pane_dead":
                        pane_dead == "1",

                    "current_command":
                        current_command,
                    "previous_command":
                        previous_command,

                    "pane_pid": (
                        int(pane_pid)
                        if pane_pid.isdigit()
                        else None
                    ),

                    "capture_ok":
                        capture_ok,
                    "output_length":
                        len(content),
                    "output_sha256":
                        current_hash,
                    "output_changed":
                        output_changed,
                    "first_observation":
                        first_observation,

                    "tmux_identity":
                        identity,
                    "tmux_identity_valid":
                        bool(identity_valid),

                    "agent_identity":
                        None,
                }
            )

        # Race-safe generation revalidation.
        #
        # A restart between initial endpoint resolution and the final
        # capture invalidates the whole collection batch for live use.
        generation_stable = (
            server_socket is not None
            and server_generation is not None
            and self._server_generation_matches(
                server_socket,
                server_generation,
            )
        )

        if not generation_stable:
            for observation in observations:
                observation[
                    "server_generation"
                ] = None

                observation[
                    "tmux_identity_valid"
                ] = False

                identity = dict(
                    observation.get(
                        "tmux_identity"
                    )
                    or {}
                )

                identity[
                    "server_generation"
                ] = None

                observation[
                    "tmux_identity"
                ] = identity

        return observations
