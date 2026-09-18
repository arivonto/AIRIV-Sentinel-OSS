"""Toolkit-neutral Desktop view model for the shared Commander payload."""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.commander_surface import (
    CommanderSurfaceProjection,
    SurfaceStatus,
    load_commander_surface_payload,
)


@dataclass(frozen=True, slots=True)
class CommanderDesktopView:
    status: SurfaceStatus
    headline: str
    reason: str
    snapshot_id: str
    service_state: str
    active_incidents: int
    read_only: bool
    production_effect: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "CommanderDesktopView":
        """Build a display-only Desktop view after payload validation."""

        projection = load_commander_surface_payload(payload)
        return cls.from_projection(projection)

    @classmethod
    def from_projection(
        cls,
        projection: CommanderSurfaceProjection,
    ) -> "CommanderDesktopView":
        if type(projection) is not CommanderSurfaceProjection:
            raise TypeError("CommanderSurfaceProjection required")
        return cls(
            status=projection.status,
            headline=projection.headline,
            reason=projection.reason,
            snapshot_id=projection.facts.snapshot_id,
            service_state=projection.facts.service_state,
            active_incidents=projection.facts.active_incidents,
            read_only=projection.read_only,
            production_effect=projection.production_effect,
        )
