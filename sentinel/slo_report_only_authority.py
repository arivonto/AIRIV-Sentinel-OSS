"""Pure validation for the bounded, non-executable SLO report-only decision."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final


REPORT_ONLY: Final = "REPORT_ONLY"
REPORT_PROJECTION: Final = "report_projection"


@dataclass(frozen=True)
class SloReportOnlyAuthorityDecision:
    decision_id: str
    decided_at: datetime
    commander_identity: str
    approved_scope_id: str
    slo_definition_ids: tuple[str, ...]
    measurement_source_ids: tuple[str, ...]
    trust_requirements: str
    evaluation_window: str
    enforcement_mode: str
    allowed_consequences: tuple[str, ...]
    blast_radius: str
    cooldown: str
    retry_budget: str
    verification_requirements: str
    rollback_position: str
    production_activation_gate: str
    expiration: datetime


def validate_report_only_decision(
    decision: SloReportOnlyAuthorityDecision,
    *,
    now: datetime | None = None,
) -> None:
    """Raise ``ValueError`` unless *decision* is complete and still valid."""
    if type(decision) is not SloReportOnlyAuthorityDecision:
        raise ValueError("canonical report-only decision required")
    if decision.enforcement_mode != REPORT_ONLY:
        raise ValueError("report-only authority requires REPORT_ONLY mode")
    if decision.allowed_consequences != (REPORT_PROJECTION,):
        raise ValueError("report-only authority permits report_projection only")
    for field_name in (
        "decision_id", "commander_identity", "approved_scope_id",
        "trust_requirements", "evaluation_window", "blast_radius",
        "cooldown", "retry_budget", "verification_requirements",
        "rollback_position", "production_activation_gate",
    ):
        if not isinstance(getattr(decision, field_name), str) or not getattr(decision, field_name).strip():
            raise ValueError(f"{field_name} must be a non-blank string")
    if not isinstance(decision.decided_at, datetime) or not isinstance(decision.expiration, datetime):
        raise ValueError("decision timestamps must be datetime values")
    if decision.decided_at.tzinfo is None or decision.expiration.tzinfo is None:
        raise ValueError("decision timestamps must be timezone-aware")
    if decision.expiration <= decision.decided_at:
        raise ValueError("expiration must be after decided_at")
    if any(not isinstance(value, str) or not value.strip() for value in (*decision.slo_definition_ids, *decision.measurement_source_ids)):
        raise ValueError("definition and source IDs must be non-blank strings")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if decision.expiration <= reference:
        raise ValueError("decision is expired")
