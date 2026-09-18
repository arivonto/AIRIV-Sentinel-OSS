"""Opt-in durable storage for deterministic incident workflow lifecycle replay."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Iterator

from sentinel.workflow.lifecycle import IncidentWorkflowLifecycle


class IncidentWorkflowLifecycleStorageError(RuntimeError):
    """Raised when durable lifecycle state cannot be trusted."""


class IncidentWorkflowLifecycleStorageConflict(
    IncidentWorkflowLifecycleStorageError
):
    """Raised when a durable lifecycle create/replace precondition fails."""


@dataclass(frozen=True)
class StoredIncidentWorkflowLifecycle:
    """Validated lifecycle plus digest required for the next atomic replace."""

    lifecycle: IncidentWorkflowLifecycle
    digest: str


class IncidentWorkflowLifecycleFileStore:
    """Explicit fail-closed persistence boundary for Lane-4 lifecycle replay.

    The store is intentionally not wired into SentinelRuntime. Callers must
    explicitly create/load/replace lifecycle state. Integrity is verified before
    reconstruction, replacements are atomic, and compare-and-swap prevents stale
    writers from silently erasing newer lifecycle events. A store path is pinned
    to one workflow/incident/component identity for its lifetime, and accepted
    replacement histories must be append-only extensions of durable history.
    """

    STORE_VERSION = 1

    def __init__(self, path: str | os.PathLike[str]) -> None:
        if isinstance(path, str) and not path:
            raise ValueError("lifecycle store path is required")

        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

        parent = self.path.parent
        if not parent.exists():
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store parent directory does not exist"
            )
        if not parent.is_dir():
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store parent is not a directory"
            )

    @staticmethod
    def _canonical_payload(snapshot: dict) -> bytes:
        payload = {
            "store_version": IncidentWorkflowLifecycleFileStore.STORE_VERSION,
            "lifecycle": snapshot,
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _serialize(
        cls,
        lifecycle: IncidentWorkflowLifecycle,
    ) -> tuple[bytes, str]:
        if not isinstance(lifecycle, IncidentWorkflowLifecycle):
            raise TypeError("lifecycle must be an IncidentWorkflowLifecycle")

        snapshot = lifecycle.to_replay_snapshot()
        try:
            IncidentWorkflowLifecycle.from_replay_snapshot(snapshot)
        except Exception as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "candidate lifecycle failed replay validation"
            ) from exc

        payload = cls._canonical_payload(snapshot)
        digest = hashlib.sha256(payload).hexdigest()
        envelope = {
            "store_version": cls.STORE_VERSION,
            "digest": digest,
            "lifecycle": snapshot,
        }
        encoded = (
            json.dumps(
                envelope,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        return encoded, digest

    @classmethod
    def _deserialize(cls, raw: bytes) -> StoredIncidentWorkflowLifecycle:
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store is not valid UTF-8 JSON"
            ) from exc

        if not isinstance(envelope, dict):
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store envelope must be an object"
            )

        expected_keys = {"store_version", "digest", "lifecycle"}
        if set(envelope) != expected_keys:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store envelope fields are invalid"
            )
        if envelope.get("store_version") != cls.STORE_VERSION:
            raise IncidentWorkflowLifecycleStorageError(
                "unsupported lifecycle store version"
            )

        digest = envelope.get("digest")
        snapshot = envelope.get("lifecycle")
        if not isinstance(digest, str) or len(digest) != 64:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store digest is invalid"
            )
        try:
            int(digest, 16)
        except ValueError as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store digest is invalid"
            ) from exc

        if not isinstance(snapshot, dict):
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle replay snapshot must be an object"
            )

        actual_digest = hashlib.sha256(
            cls._canonical_payload(snapshot)
        ).hexdigest()
        if not hmac.compare_digest(digest, actual_digest):
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store integrity check failed"
            )

        try:
            lifecycle = IncidentWorkflowLifecycle.from_replay_snapshot(snapshot)
        except Exception as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle replay snapshot failed validation"
            ) from exc

        return StoredIncidentWorkflowLifecycle(
            lifecycle=lifecycle,
            digest=digest,
        )

    @staticmethod
    def _identity(lifecycle: IncidentWorkflowLifecycle) -> tuple[str, str, str]:
        return (
            lifecycle.workflow_id,
            lifecycle.incident_id,
            lifecycle.component_id,
        )

    @staticmethod
    def _assert_append_only(
        current: IncidentWorkflowLifecycle,
        candidate: IncidentWorkflowLifecycle,
    ) -> None:
        current_events = current.to_replay_snapshot()["events"]
        candidate_events = candidate.to_replay_snapshot()["events"]
        if (
            len(candidate_events) < len(current_events)
            or candidate_events[: len(current_events)] != current_events
        ):
            raise IncidentWorkflowLifecycleStorageConflict(
                "lifecycle store history must be an append-only extension"
            )

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        fd = os.open(
            self.lock_path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        try:
            with os.fdopen(fd, "a+b", closefd=True) as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

    def _load_unlocked(self) -> StoredIncidentWorkflowLifecycle:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store does not exist"
            ) from exc
        except OSError as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store could not be read"
            ) from exc

        return self._deserialize(raw)

    def load(self) -> StoredIncidentWorkflowLifecycle:
        """Load only validated lifecycle state; never synthesize OPEN state."""
        with self._exclusive_lock():
            return self._load_unlocked()

    def create(
        self,
        lifecycle: IncidentWorkflowLifecycle,
    ) -> StoredIncidentWorkflowLifecycle:
        """Create initial durable lifecycle state only when no store exists."""
        encoded, digest = self._serialize(lifecycle)

        with self._exclusive_lock():
            if self.path.exists():
                raise IncidentWorkflowLifecycleStorageConflict(
                    "lifecycle store already exists"
                )

            try:
                fd = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(fd, "wb", closefd=True) as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as exc:
                raise IncidentWorkflowLifecycleStorageConflict(
                    "lifecycle store already exists"
                ) from exc
            except OSError as exc:
                raise IncidentWorkflowLifecycleStorageError(
                    "lifecycle store could not be created"
                ) from exc

            self._fsync_parent()

        return StoredIncidentWorkflowLifecycle(lifecycle, digest)

    def replace(
        self,
        lifecycle: IncidentWorkflowLifecycle,
        *,
        expected_digest: str,
    ) -> StoredIncidentWorkflowLifecycle:
        """Atomically append lifecycle state when digest and identity still match."""
        if not isinstance(expected_digest, str) or not expected_digest:
            raise ValueError("expected_digest is required")

        encoded, digest = self._serialize(lifecycle)

        with self._exclusive_lock():
            current = self._load_unlocked()
            if not hmac.compare_digest(current.digest, expected_digest):
                raise IncidentWorkflowLifecycleStorageConflict(
                    "lifecycle store changed since it was loaded"
                )
            if self._identity(current.lifecycle) != self._identity(lifecycle):
                raise IncidentWorkflowLifecycleStorageConflict(
                    "lifecycle store identity cannot be changed"
                )
            self._assert_append_only(current.lifecycle, lifecycle)

            temp_path: Path | None = None
            try:
                fd, temp_name = tempfile.mkstemp(
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    dir=self.path.parent,
                )
                temp_path = Path(temp_name)
                os.chmod(temp_path, 0o600)
                with os.fdopen(fd, "wb", closefd=True) as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
                temp_path = None
                self._fsync_parent()
            except OSError as exc:
                raise IncidentWorkflowLifecycleStorageError(
                    "lifecycle store could not be replaced"
                ) from exc
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink()
                    except FileNotFoundError:
                        pass

        return StoredIncidentWorkflowLifecycle(lifecycle, digest)

    def _fsync_parent(self) -> None:
        try:
            parent_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError as exc:
            raise IncidentWorkflowLifecycleStorageError(
                "lifecycle store parent directory could not be synchronized"
            ) from exc
