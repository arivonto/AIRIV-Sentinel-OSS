"""AIRIV Sentinel canonical system execution boundary."""

from dataclasses import dataclass
import subprocess
import time


@dataclass(frozen=True)
class ExecutionResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    started_at: float
    finished_at: float

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ExecutionBoundary:
    """Canonical boundary for explicit system command execution."""

    def execute(self, command: str) -> ExecutionResult:
        if not command or not command.strip():
            raise ValueError("command must not be empty")

        started_at = time.time()

        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )

        finished_at = time.time()

        return ExecutionResult(
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            started_at=started_at,
            finished_at=finished_at,
        )

    # PHASE_213C1B2_TYPED_ARGV_EXECUTION
    def execute_argv(
        self,
        argv,
        *,
        timeout: float = 5.0,
    ):
        """Execute an exact argv effect without shell interpretation."""

        import json
        import subprocess
        from datetime import datetime, timezone

        if isinstance(argv, (str, bytes)):
            raise TypeError("argv must be an iterable of strings, not str")

        argv = tuple(argv)

        if not argv:
            raise ValueError("argv must not be empty")

        if any(
            not isinstance(item, str) or not item
            for item in argv
        ):
            raise ValueError(
                "argv entries must be non-empty strings"
            )

        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or timeout <= 0
        ):
            raise ValueError("timeout must be positive")

        started_at = datetime.now(timezone.utc).isoformat()

        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=float(timeout),
            check=False,
        )

        finished_at = datetime.now(timezone.utc).isoformat()

        canonical_command = json.dumps(
            list(argv),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return ExecutionResult(
            command=canonical_command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            started_at=started_at,
            finished_at=finished_at,
        )
