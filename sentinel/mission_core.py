"""Phase 1 Sentinel-owned mission lifecycle engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from sentinel.product_identity import SentinelPhase, evaluate_identity_alignment


class MissionStage(str, Enum):
    OBSERVE = "observe"
    UNDERSTAND = "understand"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    RETRY = "retry"
    COMPLETE = "complete"
    LEARN = "learn"


MISSION_LIFECYCLE: tuple[MissionStage, ...] = (
    MissionStage.OBSERVE,
    MissionStage.UNDERSTAND,
    MissionStage.PLAN,
    MissionStage.EXECUTE,
    MissionStage.VERIFY,
    MissionStage.RETRY,
    MissionStage.COMPLETE,
    MissionStage.LEARN,
)


@dataclass(frozen=True)
class MissionRequest:
    mission_id: str
    objective: str
    provider: str
    target_phase: SentinelPhase = SentinelPhase.CORE
    linux_first: bool = True
    preserves_ai_independence: bool = True
    preserves_mission_ownership: bool = True
    preserves_engineering_brain_ownership: bool = True
    avoids_vendor_lock_in: bool = True


@dataclass(frozen=True)
class MissionStageInput:
    request: MissionRequest
    stage: MissionStage
    prior_events: tuple["MissionEvent", ...]


@dataclass(frozen=True)
class MissionStageOutput:
    summary: str
    evidence: Mapping[str, Any]
    verified: bool = True
    retry_recommended: bool = False


@dataclass(frozen=True)
class MissionEvent:
    mission_id: str
    stage: MissionStage
    summary: str
    evidence: Mapping[str, Any]
    verified: bool


@dataclass(frozen=True)
class MissionResult:
    mission_id: str
    accepted: bool
    status: str
    events: tuple[MissionEvent, ...]
    reasons: tuple[str, ...]


MissionStageHandler = Callable[[MissionStageInput], MissionStageOutput]


class SentinelMissionEngine:
    """Run Sentinel-owned mission lifecycle steps without provider authority."""

    def run(
        self,
        request: MissionRequest,
        handlers: Mapping[MissionStage, MissionStageHandler],
    ) -> MissionResult:
        self._validate_request(request)
        identity_decision = evaluate_identity_alignment(
            target_phase=request.target_phase,
            linux_first=request.linux_first,
            preserves_ai_independence=request.preserves_ai_independence,
            preserves_mission_ownership=request.preserves_mission_ownership,
            preserves_engineering_brain_ownership=(
                request.preserves_engineering_brain_ownership
            ),
            avoids_vendor_lock_in=request.avoids_vendor_lock_in,
        )
        if not identity_decision.accepted:
            return MissionResult(
                mission_id=request.mission_id,
                accepted=False,
                status="rejected",
                events=(),
                reasons=identity_decision.reasons,
            )

        missing_handlers = tuple(
            stage.value
            for stage in MISSION_LIFECYCLE
            if stage not in handlers
        )
        if missing_handlers:
            return MissionResult(
                mission_id=request.mission_id,
                accepted=False,
                status="blocked",
                events=(),
                reasons=(
                    "missing mission lifecycle handler(s): "
                    + ", ".join(missing_handlers),
                ),
            )

        events: list[MissionEvent] = []
        for stage in MISSION_LIFECYCLE:
            output = handlers[stage](
                MissionStageInput(
                    request=request,
                    stage=stage,
                    prior_events=tuple(events),
                )
            )
            event = self._event_from_output(request, stage, output)
            events.append(event)
            if not event.verified:
                return MissionResult(
                    mission_id=request.mission_id,
                    accepted=True,
                    status="blocked",
                    events=tuple(events),
                    reasons=(f"{stage.value} evidence is not verified",),
                )

        return MissionResult(
            mission_id=request.mission_id,
            accepted=True,
            status="complete",
            events=tuple(events),
            reasons=(),
        )

    @staticmethod
    def _validate_request(request: MissionRequest) -> None:
        if not isinstance(request, MissionRequest):
            raise TypeError("request must be MissionRequest")
        if not request.mission_id.strip():
            raise ValueError("mission_id must not be empty")
        if not request.objective.strip():
            raise ValueError("objective must not be empty")
        if not request.provider.strip():
            raise ValueError("provider must not be empty")

    @staticmethod
    def _event_from_output(
        request: MissionRequest,
        stage: MissionStage,
        output: MissionStageOutput,
    ) -> MissionEvent:
        if not isinstance(output, MissionStageOutput):
            raise TypeError("mission stage handlers must return MissionStageOutput")
        if not output.summary.strip():
            raise ValueError("mission stage summary must not be empty")
        if not output.evidence:
            raise ValueError("mission stage evidence must not be empty")
        return MissionEvent(
            mission_id=request.mission_id,
            stage=stage,
            summary=output.summary,
            evidence=MappingProxyType(dict(output.evidence)),
            verified=bool(output.verified),
        )
