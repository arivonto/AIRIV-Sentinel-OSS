"""Local-only dry-run transport for AIRIV Sentinel Commander briefs.

This transport exists to prove the delivery lifecycle without contacting a
network or external recipient. It is disabled by default, consumes only the
already allowlisted Commander brief, writes atomically to a configured local
directory, and never overwrites an existing delivery artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from sentinel.commander_delivery_transport import (
    CommanderDeliveryIdentityLedger,
    CommanderDeliveryState,
    CommanderTransportResult,
)


_DRY_RUN_SCHEMA_VERSION = "AIRIV_SENTINEL_COMMANDER_DRY_RUN_V1"


class FileCommanderDeliveryTransport:
    """Explicit local file transport used only for controlled dry-run proof."""

    name = "DRY_RUN_FILE"

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        enabled: bool = False,
    ) -> None:
        configured = os.environ.get("AIRIV_SENTINEL_DELIVERY_DRY_RUN_DIR")
        self.root = Path(
            root if root is not None else configured or "var/delivery_dry_run"
        )
        self.enabled = enabled
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_delivery_id(delivery_id: str) -> str:
        return CommanderDeliveryIdentityLedger._validate_delivery_id(delivery_id)

    @staticmethod
    def _validate_text(value: str, field: str) -> str:
        return CommanderDeliveryIdentityLedger._validate_identity_text(
            value,
            field,
        )

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _path(self, delivery_id: str) -> Path:
        return self.root / f"{self._validate_delivery_id(delivery_id)}.json"

    def deliver(
        self,
        *,
        delivery_id: str,
        destination_id: str,
        subject: str,
        body_markdown: str,
    ) -> CommanderTransportResult:
        if self.enabled is not True:
            raise RuntimeError("dry-run delivery transport is disabled")

        delivery_id = self._validate_delivery_id(delivery_id)
        destination_id = self._validate_text(destination_id, "destination_id")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("subject is required")
        if not isinstance(body_markdown, str) or not body_markdown.strip():
            raise ValueError("body_markdown is required")

        payload = {
            "schema_version": _DRY_RUN_SCHEMA_VERSION,
            "delivery_id": delivery_id,
            "destination_id": destination_id,
            "subject": subject,
            "body_markdown": body_markdown,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()

        final_path = self._path(delivery_id)
        if final_path.exists():
            raise FileExistsError(
                f"dry-run delivery already exists: {delivery_id}"
            )

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{delivery_id}.",
            suffix=".tmp",
            dir=self.root,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                os.link(temporary, final_path)
            except FileExistsError:
                raise FileExistsError(
                    f"dry-run delivery already exists: {delivery_id}"
                )

            self._fsync_directory(self.root)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

        return CommanderTransportResult(
            state=CommanderDeliveryState.SUCCEEDED,
            receipt_id=f"dryrun:{digest}",
            detail_code="LOCAL_DRY_RUN_WRITTEN",
        )

    def read(self, delivery_id: str) -> dict:
        path = self._path(delivery_id)
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise RuntimeError("dry-run delivery artifact must be an object")
        if data.get("schema_version") != _DRY_RUN_SCHEMA_VERSION:
            raise RuntimeError("unsupported dry-run delivery artifact schema")
        return data
