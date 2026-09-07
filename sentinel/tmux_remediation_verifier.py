"""Independent TMUX remediation verification."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Any

from sentinel.remediation_verifier import VerificationResult
from sentinel.live_remediation_safety import TmuxTargetIdentity


@dataclass(frozen=True)
class TmuxVerificationTarget:
    pane_id: str
    expected_alive: bool = True
    identity: TmuxTargetIdentity | None = None
    timeout: float = 5.0
    strong_identity: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.pane_id, str) or not self.pane_id.strip():
            raise ValueError("pane_id is required")

        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or self.timeout <= 0
        ):
            raise ValueError("timeout must be positive")

        if self.identity is not None and self.identity.pane_id != self.pane_id:
            raise ValueError("pane_identity_mismatch")

        if self.strong_identity:
            if self.identity is None:
                raise ValueError("strong identity requires target identity")

            if not self.identity.live_eligible:
                raise ValueError(
                    "strong identity requires server generation"
                )


class TmuxRemediationVerifier:
    def __init__(self, target: TmuxVerificationTarget) -> None:
        self.target = target

    def _legacy_command(self) -> list[str]:
        return [
            "tmux",
            "display-message",
            "-p",
            "-t",
            self.target.pane_id,
            "#{pane_dead}",
        ]

    def _identity_command(self) -> list[str]:
        identity = self.target.identity
        assert identity is not None

        return [
            "tmux",
            "-S",
            identity.server_socket,
            "display-message",
            "-p",
            "-t",
            identity.pane_id,
            "#{session_id}\t#{session_name}\t"
            "#{window_id}\t#{pane_id}\t#{pane_dead}",
        ]

    def verify(self) -> VerificationResult:
        if self.target.strong_identity:
            return self._verify_identity()

        return self._verify_legacy()

    def _run(self, command: list[str]):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=float(self.target.timeout),
            check=False,
        )

    def _verify_legacy(self) -> VerificationResult:
        command = self._legacy_command()

        try:
            completed = self._run(command)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return self._error(
                type(exc).__name__,
                {
                    "capture_ok": False,
                    "pane_id": self.target.pane_id,
                },
            )

        if completed.returncode != 0:
            return self._error(
                "tmux_command_failed",
                {
                    "capture_ok": False,
                    "pane_id": self.target.pane_id,
                },
            )

        value = completed.stdout.strip()

        if value not in {"0", "1"}:
            return self._error(
                "invalid_tmux_state",
                {
                    "capture_ok": False,
                    "pane_id": self.target.pane_id,
                },
            )

        pane_dead = value == "1"
        verified = (
            (not pane_dead)
            if self.target.expected_alive
            else pane_dead
        )

        return VerificationResult(
            verified=verified,
            reason=(
                "post_remediation_tmux_state_verified"
                if verified
                else "post_remediation_tmux_state_not_verified"
            ),
            observation={
                "capture_ok": True,
                "pane_id": self.target.pane_id,
                "pane_dead": pane_dead,
            },
        )

    def _verify_identity(self) -> VerificationResult:
        identity = self.target.identity
        assert identity is not None

        command = self._identity_command()

        try:
            completed = self._run(command)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return self._error(
                type(exc).__name__,
                {
                    "capture_ok": False,
                    "target_fingerprint": identity.fingerprint,
                },
            )

        if completed.returncode != 0:
            return self._error(
                "tmux_command_failed",
                {
                    "capture_ok": False,
                    "target_fingerprint": identity.fingerprint,
                },
            )

        fields = completed.stdout.rstrip("\n").split("\t")

        if len(fields) != 5:
            return self._error(
                "malformed_tmux_identity",
                {
                    "capture_ok": False,
                    "target_fingerprint": identity.fingerprint,
                },
            )

        session_id, session_name, window_id, pane_id, dead_text = fields

        if dead_text not in {"0", "1"}:
            return self._error(
                "invalid_tmux_state",
                {
                    "capture_ok": False,
                    "target_fingerprint": identity.fingerprint,
                },
            )

        observed_identity_match = (
            session_id == identity.session_id
            and session_name == identity.session_name
            and window_id == identity.window_id
            and pane_id == identity.pane_id
        )

        pane_dead = dead_text == "1"

        liveness_match = (
            (not pane_dead)
            if self.target.expected_alive
            else pane_dead
        )

        verified = observed_identity_match and liveness_match

        return VerificationResult(
            verified=verified,
            reason=(
                "post_remediation_tmux_state_verified"
                if verified
                else "post_remediation_tmux_state_not_verified"
            ),
            observation={
                "capture_ok": True,
                "server_socket": identity.server_socket,
                "server_generation": identity.server_generation,
                "session_id": session_id,
                "session_name": session_name,
                "window_id": window_id,
                "pane_id": pane_id,
                "pane_dead": pane_dead,
                "target_fingerprint": identity.fingerprint,
                "identity_match": observed_identity_match,
            },
        )

    @staticmethod
    def _error(
        reason: str,
        observation: dict[str, Any],
    ) -> VerificationResult:
        return VerificationResult(
            verified=False,
            reason=f"verification_error:{reason}",
            observation=observation,
        )
