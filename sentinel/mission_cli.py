"""Text-based Phase 1 mission command surface."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Sequence
from typing import TextIO

from sentinel.mission_core import (
    MISSION_LIFECYCLE,
    MissionRequest,
    MissionStage,
    MissionStageInput,
    MissionStageOutput,
    SentinelMissionEngine,
)
from sentinel.mission_workspace import observe_workspace


def _default_handler(context: MissionStageInput) -> MissionStageOutput:
    mission_id = context.request.mission_id
    objective = context.request.objective
    provider = context.request.provider
    stage_name = context.stage.value
    prior_event_count = len(context.prior_events)
    evidence = {
        "mission_id": mission_id,
        "objective": objective,
        "provider": provider,
        "stage": stage_name,
        "prior_event_count": prior_event_count,
        "effect": "none",
    }
    summary = f"{stage_name} verified without side effects"
    return MissionStageOutput(
        summary=summary,
        evidence=evidence,
        verified=True,
    )


def build_default_handlers():
    return {stage: _default_handler for stage in MISSION_LIFECYCLE}


def build_workspace_handlers(workspace_root: str = "."):
    observation = observe_workspace(workspace_root)

    def observe_handler(context: MissionStageInput) -> MissionStageOutput:
        output = _default_handler(context)
        evidence = dict(output.evidence)
        evidence.update(observation.to_evidence())
        return MissionStageOutput(
            summary="workspace observed without side effects",
            evidence=evidence,
            verified=observation.git_available,
        )

    handlers = build_default_handlers()
    handlers[MissionStage.OBSERVE] = observe_handler
    return handlers


def run_mission_command(argv: Sequence[str], stdout: TextIO) -> int:
    if not argv:
        print(
            "usage: sentinel mission \"Fix this repository until all tests pass.\"",
            file=stdout,
        )
        return 2

    objective = " ".join(argv).strip()
    if not objective:
        print("MISSION_STATUS=REJECTED", file=stdout)
        print("MISSION_REASON=objective must not be empty", file=stdout)
        return 2

    request = MissionRequest(
        mission_id=f"mission-{uuid.uuid4().hex[:12]}",
        objective=objective,
        provider="local-sentinel-core",
    )
    result = SentinelMissionEngine().run(request, build_workspace_handlers())

    print(f"MISSION_ID={result.mission_id}", file=stdout)
    print(f"MISSION_STATUS={result.status.upper()}", file=stdout)
    print(f"MISSION_ACCEPTED={'YES' if result.accepted else 'NO'}", file=stdout)
    for event in result.events:
        print(f"MISSION_STAGE={event.stage.value}", file=stdout)
        if event.stage is MissionStage.OBSERVE:
            git_available = "YES" if event.evidence.get("git_available") else "NO"
            print(f"MISSION_WORKSPACE_GIT={git_available}", file=stdout)
            print(
                f"MISSION_WORKSPACE_BRANCH={event.evidence.get('branch', 'UNKNOWN')}",
                file=stdout,
            )
            print(
                f"MISSION_WORKSPACE_HEAD={event.evidence.get('head_sha', 'UNKNOWN')}",
                file=stdout,
            )
    if result.reasons:
        print(
            "MISSION_REASONS="
            + json.dumps(list(result.reasons), ensure_ascii=False),
            file=stdout,
        )
    print(f"MISSION_EVENT_COUNT={len(result.events)}", file=stdout)
    print("MISSION_EFFECT=NONE", file=stdout)
    return 0 if result.status == "complete" else 1


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    output = sys.stdout if stdout is None else stdout
    if args[:1] == ("mission",):
        return run_mission_command(args[1:], output)
    print("usage: sentinel mission <objective>", file=output)
    return 2
