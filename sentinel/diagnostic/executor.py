from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import DiagnosticAction, DiagnosticActionClassification


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    diagnostic_action_id: str
    command: str
    started_at: datetime
    finished_at: datetime
    stdout: str
    stderr: str
    exit_code: int | None
    success: bool
    state: str
    error: str | None = None


class DiagnosticExecutor:
    """
    Executes only OBSERVE and DIAGNOSTIC actions.

    This boundary has no remediation authority and never executes
    CONSEQUENTIAL or PROHIBITED actions.
    """

    ALLOWED_CLASSIFICATIONS = frozenset(
        {
            DiagnosticActionClassification.OBSERVE,
            DiagnosticActionClassification.DIAGNOSTIC,
        }
    )

    def execute(self, action: DiagnosticAction) -> DiagnosticResult:
        if action.classification not in self.ALLOWED_CLASSIFICATIONS:
            raise ValueError("action_classification_not_executable")

        started_at = datetime.now(timezone.utc)
        monotonic_start = time.monotonic()

        try:
            completed = subprocess.run(
                action.command,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )

            finished_at = datetime.now(timezone.utc)

            return DiagnosticResult(
                diagnostic_action_id=action.diagnostic_action_id,
                command=action.command,
                started_at=started_at,
                finished_at=finished_at,
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                success=completed.returncode == 0,
                state="COMPLETED",
            )

        except Exception as exc:
            finished_at = datetime.now(timezone.utc)

            return DiagnosticResult(
                diagnostic_action_id=action.diagnostic_action_id,
                command=action.command,
                started_at=started_at,
                finished_at=finished_at,
                stdout="",
                stderr="",
                exit_code=None,
                success=False,
                state="UNKNOWN",
                error=str(exc),
            )

        finally:
            _ = monotonic_start


def _require_diagnostic_action(action: DiagnosticAction) -> None:
    if action.classification not in DiagnosticExecutor.ALLOWED_CLASSIFICATIONS:
        raise ValueError("action_classification_not_executable")
