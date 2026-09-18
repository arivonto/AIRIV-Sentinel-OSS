import pytest

from sentinel.mission_core import (
    MISSION_LIFECYCLE,
    MissionRequest,
    MissionStage,
    MissionStageOutput,
    SentinelMissionEngine,
)
from sentinel.product_identity import SentinelPhase
from sentinel.runtime import SentinelRuntime


def _handlers(*, verified=True):
    return {
        stage: (
            lambda context, stage=stage: MissionStageOutput(
                summary=f"{stage.value} accepted",
                evidence={
                    "mission_id": context.request.mission_id,
                    "stage": stage.value,
                    "provider": context.request.provider,
                    "prior_event_count": len(context.prior_events),
                },
                verified=verified,
            )
        )
        for stage in MISSION_LIFECYCLE
    }


def test_phase1_mission_core_runs_full_lifecycle_without_provider_authority():
    request = MissionRequest(
        mission_id="mission-001",
        objective="verify Sentinel owns the mission lifecycle",
        provider="Ollama",
    )

    result = SentinelMissionEngine().run(request, _handlers())

    assert result.accepted is True
    assert result.status == "complete"
    assert result.reasons == ()
    assert [event.stage for event in result.events] == list(MISSION_LIFECYCLE)
    assert [event.evidence["prior_event_count"] for event in result.events] == list(
        range(len(MISSION_LIFECYCLE))
    )
    assert all(event.evidence["provider"] == "Ollama" for event in result.events)


def test_mission_core_rejects_future_phase_before_running_handlers():
    called = []
    handlers = _handlers()
    handlers[MissionStage.OBSERVE] = lambda context: called.append(context)  # type: ignore[assignment]

    result = SentinelMissionEngine().run(
        MissionRequest(
            mission_id="mission-002",
            objective="skip Phase 1",
            provider="Ollama",
            target_phase=SentinelPhase.DESKTOP,
        ),
        handlers,
    )

    assert result.accepted is False
    assert result.status == "rejected"
    assert result.events == ()
    assert result.reasons == ("Phase 1 must stay focused on AIRIV Sentinel Core.",)
    assert called == []


def test_mission_core_fails_closed_when_evidence_is_unverified():
    handlers = _handlers()
    handlers[MissionStage.VERIFY] = lambda context: MissionStageOutput(
        summary="verification failed",
        evidence={"source": "unit-test"},
        verified=False,
    )

    result = SentinelMissionEngine().run(
        MissionRequest(
            mission_id="mission-003",
            objective="prove fail closed verification",
            provider="Ollama",
        ),
        handlers,
    )

    assert result.accepted is True
    assert result.status == "blocked"
    assert result.reasons == ("verify evidence is not verified",)
    assert [event.stage for event in result.events] == list(
        MISSION_LIFECYCLE[: MISSION_LIFECYCLE.index(MissionStage.VERIFY) + 1]
    )


def test_mission_core_requires_every_lifecycle_handler():
    handlers = _handlers()
    del handlers[MissionStage.LEARN]

    result = SentinelMissionEngine().run(
        MissionRequest(
            mission_id="mission-004",
            objective="detect incomplete mission lifecycle",
            provider="Ollama",
        ),
        handlers,
    )

    assert result.accepted is False
    assert result.status == "blocked"
    assert result.events == ()
    assert result.reasons == ("missing mission lifecycle handler(s): learn",)


def test_mission_stage_evidence_is_immutable_to_callers():
    result = SentinelMissionEngine().run(
        MissionRequest(
            mission_id="mission-005",
            objective="preserve evidence immutability",
            provider="Ollama",
        ),
        _handlers(),
    )

    with pytest.raises(TypeError):
        result.events[0].evidence["changed"] = True


def test_runtime_exposes_phase1_mission_engine_without_starting_mission():
    runtime = SentinelRuntime()

    assert isinstance(runtime.mission_engine, SentinelMissionEngine)
