"""Isolated TMUX workload for controlled-live remediation validation.

Phase 2.13C.1F.

This boundary owns only an explicitly isolated TMUX server and its
run-scoped filesystem directory.

It does not:
    - modify production remediation policy
    - register production actions
    - authorize remediation
    - execute remediation
    - mutate Incident lifecycle
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


_SAFE_NAME = re.compile(
    r"^[A-Za-z0-9_.-]+$"
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


@dataclass(
    frozen=True,
    slots=True,
)
class IsolatedTmuxValidationSpec:
    run_id: str
    root_dir: str
    server_socket: str
    session_name: str
    window_name: str = "validation"
    workload_argv: tuple[str, ...] = (
        "/usr/bin/sleep",
        "300",
    )
    timeout: float = 5.0

    def __post_init__(self) -> None:
        run_id = _required(
            self.run_id,
            "run_id",
        )

        root = Path(
            _required(
                self.root_dir,
                "root_dir",
            )
        )

        socket = Path(
            _required(
                self.server_socket,
                "server_socket",
            )
        )

        if not root.is_absolute():
            raise ValueError(
                "root_dir must be absolute"
            )

        if not socket.is_absolute():
            raise ValueError(
                "server_socket must be absolute"
            )

        resolved_root = root.resolve(
            strict=False
        )

        resolved_socket = socket.resolve(
            strict=False
        )

        if not resolved_socket.is_relative_to(
            resolved_root
        ):
            raise ValueError(
                "server_socket must be inside root_dir"
            )

        for field, value in (
            (
                "session_name",
                self.session_name,
            ),
            (
                "window_name",
                self.window_name,
            ),
        ):
            value = _required(
                value,
                field,
            )

            if not _SAFE_NAME.fullmatch(
                value
            ):
                raise ValueError(
                    f"{field} contains unsafe characters"
                )

        if not self.session_name.startswith(
            "airiv-sentinel-liveval-"
        ):
            raise ValueError(
                "session_name must use isolated validation prefix"
            )

        if (
            not isinstance(
                self.workload_argv,
                tuple,
            )
            or not self.workload_argv
        ):
            raise ValueError(
                "workload_argv must be non-empty tuple"
            )

        if any(
            not isinstance(item, str)
            or not item
            for item in self.workload_argv
        ):
            raise ValueError(
                "workload_argv contains invalid item"
            )

        if (
            not isinstance(
                self.timeout,
                (int, float),
            )
            or isinstance(
                self.timeout,
                bool,
            )
            or self.timeout <= 0
        ):
            raise ValueError(
                "timeout must be positive"
            )

        if "/" in run_id or "\x00" in run_id:
            raise ValueError(
                "run_id contains unsafe characters"
            )

    @property
    def marker_path(
        self,
    ) -> str:
        return str(
            Path(
                self.root_dir
            )
            / ".airiv-sentinel-live-validation"
        )

    @classmethod
    def for_root(
        cls,
        *,
        run_id: str,
        root_dir: str,
        workload_argv: tuple[str, ...] = (
            "/usr/bin/sleep",
            "300",
        ),
        timeout: float = 5.0,
    ) -> "IsolatedTmuxValidationSpec":
        safe_run = re.sub(
            r"[^A-Za-z0-9_.-]",
            "-",
            _required(
                run_id,
                "run_id",
            ),
        )

        root = Path(
            root_dir
        ).resolve(
            strict=False
        )

        return cls(
            run_id=run_id,
            root_dir=str(root),
            server_socket=str(
                root / "tmux.sock"
            ),
            session_name=(
                "airiv-sentinel-liveval-"
                + safe_run
            ),
            workload_argv=workload_argv,
            timeout=timeout,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class IsolatedTmuxActivation:
    run_id: str
    server_socket: str
    session_name: str
    window_name: str
    workload_argv: tuple[str, ...]


class IsolatedTmuxValidationController:
    """Lifecycle authority for one isolated validation workload."""

    def __init__(
        self,
        spec: IsolatedTmuxValidationSpec,
        *,
        runner: Callable = subprocess.run,
    ) -> None:
        if not isinstance(
            spec,
            IsolatedTmuxValidationSpec,
        ):
            raise TypeError(
                "spec must be IsolatedTmuxValidationSpec"
            )

        self.spec = spec
        self._runner = runner
        self._active = False

    @property
    def active(
        self,
    ) -> bool:
        return self._active

    @property
    def activation_argv(
        self,
    ) -> tuple[str, ...]:
        return (
            "tmux",
            "-S",
            self.spec.server_socket,
            "new-session",
            "-d",
            "-s",
            self.spec.session_name,
            "-n",
            self.spec.window_name,
            *self.spec.workload_argv,
        )

    @property
    def remain_on_exit_argv(
        self,
    ) -> tuple[str, ...]:
        return (
            "tmux",
            "-S",
            self.spec.server_socket,
            "set-option",
            "-t",
            self.spec.session_name,
            "remain-on-exit",
            "on",
        )

    @property
    def teardown_argv(
        self,
    ) -> tuple[str, ...]:
        return (
            "tmux",
            "-S",
            self.spec.server_socket,
            "kill-server",
        )

    def _run(
        self,
        argv: tuple[str, ...],
    ):
        return self._runner(
            list(argv),
            capture_output=True,
            text=True,
            timeout=float(
                self.spec.timeout
            ),
            check=False,
        )

    def _marker_payload(
        self,
    ) -> dict[str, object]:
        return {
            "kind":
                "AIRIV_SENTINEL_ISOLATED_TMUX_VALIDATION",
            "run_id":
                self.spec.run_id,
            "server_socket":
                self.spec.server_socket,
            "session_name":
                self.spec.session_name,
            "window_name":
                self.spec.window_name,
            "workload_argv":
                list(
                    self.spec.workload_argv
                ),
        }

    def _create_root_and_marker(
        self,
    ) -> None:
        root = Path(
            self.spec.root_dir
        )

        root.mkdir(
            mode=0o700,
            parents=True,
            exist_ok=False,
        )

        os.chmod(
            root,
            0o700,
        )

        marker = Path(
            self.spec.marker_path
        )

        fd = os.open(
            marker,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL,
            0o600,
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    self._marker_payload(),
                    handle,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                handle.flush()
                os.fsync(
                    handle.fileno()
                )

        except Exception:
            try:
                marker.unlink()
            except FileNotFoundError:
                pass

            try:
                root.rmdir()
            except OSError:
                pass

            raise

    def _read_marker(
        self,
    ) -> dict[str, object] | None:
        marker = Path(
            self.spec.marker_path
        )

        try:
            raw = marker.read_text(
                encoding="utf-8"
            )
        except FileNotFoundError:
            return None

        try:
            value = json.loads(
                raw
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "validation_marker_invalid"
            ) from exc

        if not isinstance(
            value,
            dict,
        ):
            raise RuntimeError(
                "validation_marker_invalid"
            )

        return value

    def _validate_ownership(
        self,
    ) -> bool:
        marker = self._read_marker()

        if marker is None:
            return False

        expected = (
            self._marker_payload()
        )

        if marker != expected:
            raise RuntimeError(
                "validation_ownership_mismatch"
            )

        return True

    def activate(
        self,
    ) -> IsolatedTmuxActivation:
        if self._active:
            raise RuntimeError(
                "validation_already_active"
            )

        root = Path(
            self.spec.root_dir
        )

        if root.exists():
            raise RuntimeError(
                "validation_root_already_exists"
            )

        self._create_root_and_marker()

        try:
            result = self._run(
                self.activation_argv
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "validation_tmux_activation_failed"
                )

            self._active = True

            option_result = self._run(
                self.remain_on_exit_argv
            )

            if option_result.returncode != 0:
                raise RuntimeError(
                    "validation_remain_on_exit_failed"
                )

            return IsolatedTmuxActivation(
                run_id=self.spec.run_id,
                server_socket=(
                    self.spec.server_socket
                ),
                session_name=(
                    self.spec.session_name
                ),
                window_name=(
                    self.spec.window_name
                ),
                workload_argv=(
                    self.spec.workload_argv
                ),
            )

        except Exception:
            self._cleanup_after_failed_activation()
            raise

    def _cleanup_after_failed_activation(
        self,
    ) -> None:
        try:
            if self._validate_ownership():
                try:
                    self._run(
                        self.teardown_argv
                    )
                except Exception:
                    pass

        finally:
            self._active = False
            self._remove_owned_files()

    def _remove_owned_files(
        self,
    ) -> None:
        root = Path(
            self.spec.root_dir
        )

        marker = Path(
            self.spec.marker_path
        )

        socket = Path(
            self.spec.server_socket
        )

        try:
            marker.unlink()
        except FileNotFoundError:
            pass

        # Only this exact run-scoped socket path is removable.
        try:
            socket.unlink()
        except FileNotFoundError:
            pass

        try:
            root.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            # Unknown files remain -> fail closed.
            pass

    def teardown(
        self,
    ) -> bool:
        root = Path(
            self.spec.root_dir
        )

        if not root.exists():
            self._active = False
            return False

        if not self._validate_ownership():
            # Existing unowned root must never be touched.
            raise RuntimeError(
                "validation_root_not_owned"
            )

        result = self._run(
            self.teardown_argv
        )

        # kill-server may return nonzero if the isolated server already
        # exited. Ownership still permits cleanup of the run-scoped
        # socket/marker/root.
        self._active = False
        self._remove_owned_files()

        return result.returncode == 0

    def __enter__(
        self,
    ) -> IsolatedTmuxActivation:
        return self.activate()

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        try:
            self.teardown()
        finally:
            self._active = False

        return False
