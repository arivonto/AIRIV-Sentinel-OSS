"""Detached read-only projection shared by Sentinel Web and Desktop surfaces.

The projection accepts already-observed facts only. It does not read the host,
open a network listener, execute commands, mutate incidents, or authorize an
effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class SurfaceStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class CommanderSurfaceFacts:
    snapshot_id: str
    observed_at: str
    service_unit: str
    service_state: str
    runtime_identity: str
    readiness_state: str
    active_incidents: int
    evidence_complete: bool
    production_effect: str = "NONE"

    def __post_init__(self) -> None:
        values = (
            self.snapshot_id,
            self.observed_at,
            self.service_unit,
            self.service_state,
            self.runtime_identity,
        )
        if any(type(value) is not str or not value.strip() for value in values):
            raise ValueError("surface identity facts must be non-empty text")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", self.snapshot_id):
            raise ValueError("invalid snapshot_id")
        if self.service_unit != "airiv-sentinel.service":
            raise ValueError("unexpected service unit")
        if self.service_state not in {"active/running", "inactive", "unknown"}:
            raise ValueError("invalid service_state")
        if self.readiness_state not in {"READY", "ACTIVATION_BLOCKED", "UNKNOWN"}:
            raise ValueError("invalid readiness_state")
        if type(self.active_incidents) is not int or self.active_incidents < 0:
            raise ValueError("active_incidents must be a non-negative integer")
        if type(self.evidence_complete) is not bool:
            raise ValueError("evidence_complete must be boolean")
        if self.production_effect != "NONE":
            raise ValueError("surface projection must remain PRODUCTION_EFFECT=NONE")


@dataclass(frozen=True, slots=True)
class CommanderSurfaceProjection:
    status: SurfaceStatus
    reason: str
    headline: str
    read_only: bool
    production_effect: str
    facts: CommanderSurfaceFacts

    def to_payload(self) -> dict[str, object]:
        """Return the stable, non-authoritative Web/Desktop payload shape."""

        return {
            "schema": "airiv.sentinel.commander_surface.v1",
            "status": self.status.value,
            "reason": self.reason,
            "headline": self.headline,
            "read_only": self.read_only,
            "production_effect": self.production_effect,
            "facts": {
                "snapshot_id": self.facts.snapshot_id,
                "observed_at": self.facts.observed_at,
                "service_unit": self.facts.service_unit,
                "service_state": self.facts.service_state,
                "runtime_identity": self.facts.runtime_identity,
                "readiness_state": self.facts.readiness_state,
                "active_incidents": self.facts.active_incidents,
                "evidence_complete": self.facts.evidence_complete,
                "production_effect": self.facts.production_effect,
            },
        }


def load_commander_surface_payload(
    payload: dict[str, object],
) -> CommanderSurfaceProjection:
    """Validate and load one detached v1 payload for a surface consumer."""

    if type(payload) is not dict:
        raise TypeError("surface payload must be a dict")
    required = {
        "schema", "status", "reason", "headline", "read_only",
        "production_effect", "facts",
    }
    if set(payload) != required or payload["schema"] != "airiv.sentinel.commander_surface.v1":
        raise ValueError("unsupported surface payload schema")
    if payload["read_only"] is not True or payload["production_effect"] != "NONE":
        raise ValueError("surface payload authority boundary violated")
    raw_facts = payload["facts"]
    if type(raw_facts) is not dict:
        raise ValueError("surface facts must be an object")
    fact_keys = {
        "snapshot_id", "observed_at", "service_unit", "service_state",
        "runtime_identity", "readiness_state", "active_incidents",
        "evidence_complete", "production_effect",
    }
    if set(raw_facts) != fact_keys:
        raise ValueError("surface facts shape mismatch")
    facts = CommanderSurfaceFacts(**raw_facts)
    projection = project_commander_surface(facts)
    if (
        payload["status"] != projection.status.value
        or payload["reason"] != projection.reason
        or payload["headline"] != projection.headline
    ):
        raise ValueError("surface payload projection mismatch")
    return projection


def project_commander_surface(
    facts: CommanderSurfaceFacts,
) -> CommanderSurfaceProjection:
    """Project detached facts into a safe Web/Desktop status view."""

    if type(facts) is not CommanderSurfaceFacts:
        raise TypeError("CommanderSurfaceFacts required")

    if facts.readiness_state == "UNKNOWN" or facts.service_state == "unknown":
        status = SurfaceStatus.UNKNOWN
        reason = "surface_facts_incomplete"
        headline = "Evidence incomplete"
    elif facts.readiness_state == "ACTIVATION_BLOCKED":
        status = SurfaceStatus.BLOCKED
        reason = "activation_remains_blocked"
        headline = "Activation blocked"
    elif facts.service_state != "active/running" or not facts.evidence_complete:
        status = SurfaceStatus.BLOCKED
        reason = "runtime_or_evidence_not_ready"
        headline = "Attention required"
    else:
        status = SurfaceStatus.READY
        reason = "read_only_surface_ready"
        headline = "Evidence surface ready"

    return CommanderSurfaceProjection(
        status=status,
        reason=reason,
        headline=headline,
        read_only=True,
        production_effect=facts.production_effect,
        facts=facts,
    )
