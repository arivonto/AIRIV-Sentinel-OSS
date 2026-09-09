"""Fail-closed Commander delivery transport foundation for AIRIV Sentinel.

This module provides delivery identity, replay protection, a transport protocol,
and a disabled-by-default orchestrator. It does not provide any network
transport. The durable ledger stores only bounded delivery metadata and never
stores the Commander brief body, subject, raw Incident evidence, or credentials.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Protocol

from sentinel.commander_delivery import CommanderDeliveryProjection


class CommanderDeliveryState:
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"


_TERMINAL_STATES = {
    CommanderDeliveryState.SUCCEEDED,
    CommanderDeliveryState.FAILED,
    CommanderDeliveryState.UNKNOWN,
}


@dataclass(frozen=True, slots=True)
class CommanderDeliveryRecord:
    delivery_id: str
    state: str
    projection_sha256: str
    destination_id: str
    transport_name: str
    created_at: float
    updated_at: float
    receipt_id: str | None = None
    detail_code: str | None = None
    unknown_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CommanderDeliveryClaim:
    claimed: bool
    replayed: bool
    record: CommanderDeliveryRecord


@dataclass(frozen=True, slots=True)
class CommanderTransportResult:
    """Bounded result returned by an enabled transport adapter."""

    state: str
    receipt_id: str | None = None
    detail_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _TERMINAL_STATES:
            raise ValueError("transport result must be SUCCEEDED, FAILED, or UNKNOWN")
        for field_name, value in (
            ("receipt_id", self.receipt_id),
            ("detail_code", self.detail_code),
        ):
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{field_name} must be a non-empty string")
                if len(value) > 256:
                    raise ValueError(f"{field_name} is too long")
                if any(ord(char) < 32 for char in value):
                    raise ValueError(f"{field_name} contains control characters")


class CommanderDeliveryTransport(Protocol):
    """Transport contract. Implementations must remain outside authority logic."""

    name: str
    enabled: bool

    def deliver(
        self,
        *,
        delivery_id: str,
        destination_id: str,
        subject: str,
        body_markdown: str,
    ) -> CommanderTransportResult:
        ...


class DisabledCommanderDeliveryTransport:
    """Production-safe default transport with no external side effect."""

    name = "DISABLED"
    enabled = False

    def deliver(
        self,
        *,
        delivery_id: str,
        destination_id: str,
        subject: str,
        body_markdown: str,
    ) -> CommanderTransportResult:
        raise RuntimeError("disabled Commander delivery transport cannot send")


class CommanderDeliveryIdentityLedger:
    """Durable replay-safe identity ledger for external delivery attempts."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = os.environ.get("AIRIV_SENTINEL_DELIVERY_IDENTITY_DIR")
        self.root = Path(
            root if root is not None else configured or "var/delivery_identity"
        )
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_delivery_id(delivery_id: str) -> str:
        if not isinstance(delivery_id, str) or not delivery_id.strip():
            raise ValueError("delivery_id is required")
        delivery_id = delivery_id.strip()
        if delivery_id in {".", ".."}:
            raise ValueError("invalid delivery_id")
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", delivery_id):
            raise ValueError("delivery_id contains invalid characters")
        return delivery_id

    @staticmethod
    def _validate_identity_text(value: str, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        value = value.strip()
        if len(value) > 256:
            raise ValueError(f"{field} is too long")
        if any(ord(char) < 32 for char in value):
            raise ValueError(f"{field} contains control characters")
        return value

    @staticmethod
    def _validate_digest(value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value or ""):
            raise ValueError("projection_sha256 must be lowercase SHA-256 hex")
        return value

    def _record_dir(self, delivery_id: str) -> Path:
        return self.root / self._validate_delivery_id(delivery_id)

    def _record_path(self, delivery_id: str) -> Path:
        return self._record_dir(delivery_id) / "record.json"

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _write_atomic(cls, path: Path, record: CommanderDeliveryRecord) -> None:
        payload = json.dumps(
            asdict(record),
            sort_keys=True,
            separators=(",", ":"),
        )
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            cls._fsync_directory(path.parent)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    @staticmethod
    def _load_path(path: Path) -> CommanderDeliveryRecord:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise RuntimeError("delivery identity record must be an object")
        try:
            record = CommanderDeliveryRecord(**data)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("delivery identity record is malformed") from exc
        if record.state not in {
            CommanderDeliveryState.CLAIMED,
            CommanderDeliveryState.RUNNING,
            *_TERMINAL_STATES,
        }:
            raise RuntimeError("delivery identity record has invalid state")
        return record

    @staticmethod
    def _assert_continuity(
        record: CommanderDeliveryRecord,
        *,
        projection_sha256: str,
        destination_id: str,
        transport_name: str,
    ) -> None:
        if (
            record.projection_sha256 != projection_sha256
            or record.destination_id != destination_id
            or record.transport_name != transport_name
        ):
            raise RuntimeError(
                "delivery identity replay does not match original bound effect"
            )

    def claim(
        self,
        *,
        delivery_id: str,
        projection_sha256: str,
        destination_id: str,
        transport_name: str,
    ) -> CommanderDeliveryClaim:
        delivery_id = self._validate_delivery_id(delivery_id)
        projection_sha256 = self._validate_digest(projection_sha256)
        destination_id = self._validate_identity_text(destination_id, "destination_id")
        transport_name = self._validate_identity_text(transport_name, "transport_name")

        record_dir = self._record_dir(delivery_id)
        record_path = record_dir / "record.json"
        now = time.time()
        record = CommanderDeliveryRecord(
            delivery_id=delivery_id,
            state=CommanderDeliveryState.CLAIMED,
            projection_sha256=projection_sha256,
            destination_id=destination_id,
            transport_name=transport_name,
            created_at=now,
            updated_at=now,
        )

        temporary_dir = Path(
            tempfile.mkdtemp(prefix=f".{delivery_id}.", dir=self.root)
        )
        try:
            self._write_atomic(temporary_dir / "record.json", record)
            self._fsync_directory(temporary_dir)
            try:
                os.rename(temporary_dir, record_dir)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                existing = self._load_path(record_path)
                self._assert_continuity(
                    existing,
                    projection_sha256=projection_sha256,
                    destination_id=destination_id,
                    transport_name=transport_name,
                )
                if existing.state not in _TERMINAL_STATES:
                    raise RuntimeError(
                        "delivery identity already exists in non-terminal state"
                    )
                shutil.rmtree(temporary_dir, ignore_errors=False)
                return CommanderDeliveryClaim(
                    claimed=False,
                    replayed=True,
                    record=existing,
                )
            self._fsync_directory(self.root)
        except BaseException:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

        return CommanderDeliveryClaim(
            claimed=True,
            replayed=False,
            record=record,
        )

    def get(self, delivery_id: str) -> CommanderDeliveryRecord | None:
        path = self._record_path(delivery_id)
        if not path.exists():
            return None
        return self._load_path(path)

    def transition(
        self,
        delivery_id: str,
        state: str,
        *,
        receipt_id: str | None = None,
        detail_code: str | None = None,
        unknown_reason: str | None = None,
    ) -> CommanderDeliveryRecord:
        if state not in {
            CommanderDeliveryState.RUNNING,
            *_TERMINAL_STATES,
        }:
            raise ValueError("invalid delivery identity transition state")

        path = self._record_path(delivery_id)
        current = self._load_path(path)
        if current.state in _TERMINAL_STATES:
            if current.state != state:
                raise RuntimeError("terminal delivery identity cannot transition")
            return current

        allowed = (
            current.state == CommanderDeliveryState.CLAIMED
            and state == CommanderDeliveryState.RUNNING
        ) or (
            current.state == CommanderDeliveryState.RUNNING
            and state in _TERMINAL_STATES
        )
        if not allowed:
            raise RuntimeError(
                f"invalid delivery transition: {current.state} -> {state}"
            )

        for field_name, value in (
            ("receipt_id", receipt_id),
            ("detail_code", detail_code),
            ("unknown_reason", unknown_reason),
        ):
            if value is not None:
                self._validate_identity_text(value, field_name)

        updated = CommanderDeliveryRecord(
            delivery_id=current.delivery_id,
            state=state,
            projection_sha256=current.projection_sha256,
            destination_id=current.destination_id,
            transport_name=current.transport_name,
            created_at=current.created_at,
            updated_at=time.time(),
            receipt_id=receipt_id,
            detail_code=detail_code,
            unknown_reason=unknown_reason,
        )
        self._write_atomic(path, updated)
        return updated


def commander_delivery_projection_sha256(
    projection: CommanderDeliveryProjection,
) -> str:
    if not isinstance(projection, CommanderDeliveryProjection):
        raise TypeError("projection must be CommanderDeliveryProjection")
    encoded = json.dumps(
        projection.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CommanderDeliveryAttempt:
    delivery_id: str
    state: str
    attempted: bool
    delivered: bool
    replayed: bool
    receipt_id: str | None = None
    detail_code: str | None = None
    unknown_reason: str | None = None


class CommanderDeliveryOrchestrator:
    """Replay-safe delivery coordinator with a disabled production default."""

    def __init__(
        self,
        ledger: CommanderDeliveryIdentityLedger | None = None,
        transport: CommanderDeliveryTransport | None = None,
    ) -> None:
        self.ledger = ledger or CommanderDeliveryIdentityLedger()
        self.transport = transport or DisabledCommanderDeliveryTransport()

    def deliver(
        self,
        *,
        projection: CommanderDeliveryProjection,
        delivery_id: str,
        destination_id: str,
    ) -> CommanderDeliveryAttempt:
        if not isinstance(projection, CommanderDeliveryProjection):
            raise TypeError("projection must be CommanderDeliveryProjection")
        delivery_id = self.ledger._validate_delivery_id(delivery_id)
        destination_id = self.ledger._validate_identity_text(
            destination_id, "destination_id"
        )

        transport_name = self.ledger._validate_identity_text(
            self.transport.name, "transport_name"
        )
        if self.transport.enabled is not True:
            return CommanderDeliveryAttempt(
                delivery_id=delivery_id,
                state=CommanderDeliveryState.DISABLED,
                attempted=False,
                delivered=False,
                replayed=False,
                detail_code="TRANSPORT_DISABLED",
            )

        projection_sha256 = commander_delivery_projection_sha256(projection)
        claim = self.ledger.claim(
            delivery_id=delivery_id,
            projection_sha256=projection_sha256,
            destination_id=destination_id,
            transport_name=transport_name,
        )
        if claim.replayed:
            record = claim.record
            return CommanderDeliveryAttempt(
                delivery_id=record.delivery_id,
                state=record.state,
                attempted=False,
                delivered=record.state == CommanderDeliveryState.SUCCEEDED,
                replayed=True,
                receipt_id=record.receipt_id,
                detail_code=record.detail_code,
                unknown_reason=record.unknown_reason,
            )

        self.ledger.transition(delivery_id, CommanderDeliveryState.RUNNING)

        try:
            result = self.transport.deliver(
                delivery_id=delivery_id,
                destination_id=destination_id,
                subject=projection.subject(),
                body_markdown=projection.to_markdown(),
            )
        except Exception as exc:
            reason = f"transport_exception:{type(exc).__name__}"
            record = self.ledger.transition(
                delivery_id,
                CommanderDeliveryState.UNKNOWN,
                unknown_reason=reason,
            )
            return CommanderDeliveryAttempt(
                delivery_id=record.delivery_id,
                state=record.state,
                attempted=True,
                delivered=False,
                replayed=False,
                unknown_reason=record.unknown_reason,
            )

        record = self.ledger.transition(
            delivery_id,
            result.state,
            receipt_id=result.receipt_id,
            detail_code=result.detail_code,
            unknown_reason=(
                "transport_reported_unknown"
                if result.state == CommanderDeliveryState.UNKNOWN
                else None
            ),
        )
        return CommanderDeliveryAttempt(
            delivery_id=record.delivery_id,
            state=record.state,
            attempted=True,
            delivered=record.state == CommanderDeliveryState.SUCCEEDED,
            replayed=False,
            receipt_id=record.receipt_id,
            detail_code=record.detail_code,
            unknown_reason=record.unknown_reason,
        )
