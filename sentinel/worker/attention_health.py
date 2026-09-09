"""Detached read-only observability projections with no runtime authority."""

from dataclasses import dataclass
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class CommanderAttentionProjection:
    total_items: int
    pending_count: int
    resolved_count: int
    unknown_count: int
    pending_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryHealthProjection:
    total_records: int
    pending_count: int
    delivered_count: int
    failed_count: int
    unknown_count: int
    duplicate_identity_count: int
    health: str


@dataclass(frozen=True)
class AIExecutionHealthProjection:
    total_records: int
    healthy_count: int
    identity_missing_count: int
    verification_failed_count: int
    unknown_count: int
    duplicate_execution_id_count: int
    health: str


def _stable_id(record: Mapping[str, Any], field: str) -> str | None:
    value = record.get(field)
    return value if isinstance(value, str) and value.strip() else None


def project_commander_attention(
    records: Iterable[Mapping[str, Any]],
) -> CommanderAttentionProjection:
    """Project explicit attention facts without triggering Commander behavior."""
    total = pending = resolved = unknown = 0
    pending_ids: list[str] = []

    for record in records:
        total += 1
        requires_attention = record.get("requires_attention")
        is_resolved = record.get("resolved")
        attention_id = _stable_id(record, "attention_id")

        if requires_attention is True and is_resolved is False:
            pending += 1
            if attention_id is not None:
                pending_ids.append(attention_id)
            else:
                unknown += 1
        elif requires_attention is True and is_resolved is True:
            resolved += 1
        elif requires_attention is False and isinstance(is_resolved, bool):
            resolved += int(is_resolved)
        else:
            unknown += 1

    return CommanderAttentionProjection(
        total_items=total,
        pending_count=pending,
        resolved_count=resolved,
        unknown_count=unknown,
        pending_ids=tuple(pending_ids),
    )


def project_delivery_health(
    records: Iterable[Mapping[str, Any]],
) -> DeliveryHealthProjection:
    """Project detached delivery facts; never perform delivery."""
    total = pending = delivered = failed = unknown = duplicates = 0
    identities: set[str] = set()

    for record in records:
        total += 1
        delivery_id = _stable_id(record, "delivery_id")
        if delivery_id is None:
            unknown += 1
        elif delivery_id in identities:
            duplicates += 1
        else:
            identities.add(delivery_id)

        status = record.get("status")
        if status == "PENDING":
            pending += 1
        elif status == "DELIVERED":
            delivered += 1
        elif status == "FAILED":
            failed += 1
        else:
            unknown += 1

    health = "DEGRADED" if failed or unknown or duplicates else "HEALTHY"
    return DeliveryHealthProjection(
        total_records=total,
        pending_count=pending,
        delivered_count=delivered,
        failed_count=failed,
        unknown_count=unknown,
        duplicate_identity_count=duplicates,
        health=health,
    )


def project_ai_execution_health(
    records: Iterable[Mapping[str, Any]],
) -> AIExecutionHealthProjection:
    """Project explicit identity/verifier facts without invoking AI boundaries."""
    total = healthy = identity_missing = verification_failed = unknown = duplicates = 0
    identities: set[str] = set()

    for record in records:
        total += 1
        execution_id = _stable_id(record, "execution_id")
        if execution_id is None:
            unknown += 1
        elif execution_id in identities:
            duplicates += 1
        else:
            identities.add(execution_id)

        identity_status = record.get("identity_status")
        verification_status = record.get("verification_status")

        if identity_status == "MISSING":
            identity_missing += 1
        elif identity_status not in {"PRESENT", "UNKNOWN"}:
            unknown += 1

        if verification_status == "FAILED":
            verification_failed += 1
        elif verification_status not in {"VERIFIED", "UNKNOWN"}:
            unknown += 1

        if identity_status == "UNKNOWN" or verification_status == "UNKNOWN":
            unknown += 1

        if identity_status == "PRESENT" and verification_status == "VERIFIED":
            healthy += 1

    health = (
        "DEGRADED"
        if identity_missing or verification_failed or unknown or duplicates
        else "HEALTHY"
    )
    return AIExecutionHealthProjection(
        total_records=total,
        healthy_count=healthy,
        identity_missing_count=identity_missing,
        verification_failed_count=verification_failed,
        unknown_count=unknown,
        duplicate_execution_id_count=duplicates,
        health=health,
    )
