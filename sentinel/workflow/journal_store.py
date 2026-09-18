"""Explicit durable storage boundary for workflow replay journals."""

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

from sentinel.workflow.executor import WorkflowExecutionJournal


class WorkflowJournalStorageError(RuntimeError):
    """Raised when durable workflow journal state cannot be trusted."""


class WorkflowJournalStorageConflict(WorkflowJournalStorageError):
    """Raised when a create/replace precondition no longer holds."""


@dataclass(frozen=True)
class StoredWorkflowExecutionJournal:
    """Validated journal plus the digest required for the next replace."""

    journal: WorkflowExecutionJournal
    digest: str


class WorkflowExecutionJournalFileStore:
    """Durable, explicit, fail-closed workflow replay journal storage.

    This boundary is intentionally not wired into SentinelRuntime. Callers must
    explicitly create, load, and replace journal state. Replacements use a
    compare-and-swap digest while holding an advisory file lock so a stale
    writer cannot silently erase a newer replay identity.
    """

    STORE_VERSION = 1

    def __init__(self, path: str | os.PathLike[str]) -> None:
        if isinstance(path, str) and not path:
            raise ValueError("workflow journal path is required")

        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

        parent = self.path.parent
        if not parent.exists():
            raise WorkflowJournalStorageError(
                "workflow journal parent directory does not exist"
            )
        if not parent.is_dir():
            raise WorkflowJournalStorageError(
                "workflow journal parent is not a directory"
            )

    @staticmethod
    def _canonical_payload(snapshot: dict) -> bytes:
        payload = {
            "store_version": WorkflowExecutionJournalFileStore.STORE_VERSION,
            "journal": snapshot,
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _serialize(cls, journal: WorkflowExecutionJournal) -> tuple[bytes, str]:
        if not isinstance(journal, WorkflowExecutionJournal):
            raise TypeError("journal must be a WorkflowExecutionJournal")

        snapshot = journal.to_snapshot()
        payload = cls._canonical_payload(snapshot)
        digest = hashlib.sha256(payload).hexdigest()
        envelope = {
            "store_version": cls.STORE_VERSION,
            "digest": digest,
            "journal": snapshot,
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
    def _deserialize(cls, raw: bytes) -> StoredWorkflowExecutionJournal:
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkflowJournalStorageError(
                "workflow journal store is not valid UTF-8 JSON"
            ) from exc

        if not isinstance(envelope, dict):
            raise WorkflowJournalStorageError(
                "workflow journal store envelope must be an object"
            )

        expected_keys = {"store_version", "digest", "journal"}
        if set(envelope) != expected_keys:
            raise WorkflowJournalStorageError(
                "workflow journal store envelope fields are invalid"
            )

        if envelope.get("store_version") != cls.STORE_VERSION:
            raise WorkflowJournalStorageError(
                "unsupported workflow journal store version"
            )

        digest = envelope.get("digest")
        snapshot = envelope.get("journal")
        if not isinstance(digest, str) or len(digest) != 64:
            raise WorkflowJournalStorageError(
                "workflow journal store digest is invalid"
            )
        try:
            int(digest, 16)
        except ValueError as exc:
            raise WorkflowJournalStorageError(
                "workflow journal store digest is invalid"
            ) from exc

        if not isinstance(snapshot, dict):
            raise WorkflowJournalStorageError(
                "workflow journal snapshot must be an object"
            )

        actual_digest = hashlib.sha256(
            cls._canonical_payload(snapshot)
        ).hexdigest()
        if not hmac.compare_digest(digest, actual_digest):
            raise WorkflowJournalStorageError(
                "workflow journal store integrity check failed"
            )

        try:
            journal = WorkflowExecutionJournal.from_snapshot(snapshot)
        except Exception as exc:
            raise WorkflowJournalStorageError(
                "workflow journal snapshot failed validation"
            ) from exc

        return StoredWorkflowExecutionJournal(
            journal=journal,
            digest=digest,
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
            # fdopen owns fd after construction. If construction itself fails,
            # close the raw descriptor without masking the original failure.
            try:
                os.close(fd)
            except OSError:
                pass
            raise

    def _load_unlocked(self) -> StoredWorkflowExecutionJournal:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError as exc:
            raise WorkflowJournalStorageError(
                "workflow journal store does not exist"
            ) from exc
        except OSError as exc:
            raise WorkflowJournalStorageError(
                "workflow journal store could not be read"
            ) from exc

        return self._deserialize(raw)

    def load(self) -> StoredWorkflowExecutionJournal:
        """Load only validated durable state; never synthesize an empty journal."""
        with self._exclusive_lock():
            return self._load_unlocked()

    def create(
        self,
        journal: WorkflowExecutionJournal | None = None,
    ) -> StoredWorkflowExecutionJournal:
        """Create initial durable state only when no journal file exists."""
        candidate = journal or WorkflowExecutionJournal()
        encoded, digest = self._serialize(candidate)

        with self._exclusive_lock():
            if self.path.exists():
                raise WorkflowJournalStorageConflict(
                    "workflow journal store already exists"
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
                raise WorkflowJournalStorageConflict(
                    "workflow journal store already exists"
                ) from exc
            except OSError as exc:
                raise WorkflowJournalStorageError(
                    "workflow journal store could not be created"
                ) from exc

            self._fsync_parent()

        return StoredWorkflowExecutionJournal(candidate, digest)

    def replace(
        self,
        journal: WorkflowExecutionJournal,
        *,
        expected_digest: str,
    ) -> StoredWorkflowExecutionJournal:
        """Atomically replace state only if the durable digest still matches."""
        if not isinstance(expected_digest, str) or not expected_digest:
            raise ValueError("expected_digest is required")

        encoded, digest = self._serialize(journal)

        with self._exclusive_lock():
            current = self._load_unlocked()
            if not hmac.compare_digest(current.digest, expected_digest):
                raise WorkflowJournalStorageConflict(
                    "workflow journal store changed since it was loaded"
                )

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
                raise WorkflowJournalStorageError(
                    "workflow journal store could not be replaced"
                ) from exc
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink()
                    except FileNotFoundError:
                        pass

        return StoredWorkflowExecutionJournal(journal, digest)

    def _fsync_parent(self) -> None:
        try:
            parent_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError as exc:
            raise WorkflowJournalStorageError(
                "workflow journal parent directory could not be synchronized"
            ) from exc
