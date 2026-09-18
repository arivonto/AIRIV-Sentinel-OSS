from sentinel.product_identity import (
    SENTINEL_IDENTITY,
    SentinelPhase,
    evaluate_identity_alignment,
)


def test_sentinel_identity_v2_is_linux_first_multi_ai_mission_engine():
    assert SENTINEL_IDENTITY.name == "AIRIV Sentinel"
    assert SENTINEL_IDENTITY.current_phase is SentinelPhase.CORE
    assert SENTINEL_IDENTITY.primary_platform == "Linux"
    assert SENTINEL_IDENTITY.motto == ("One Mission.", "Any AI.", "Linux First.")

    assert "Mission" in SENTINEL_IDENTITY.owns
    assert "Engineering Brain" in SENTINEL_IDENTITY.owns
    assert "Engineering Memory" in SENTINEL_IDENTITY.owns
    assert "Engineering Workflow" in SENTINEL_IDENTITY.owns
    assert "Operational Knowledge" in SENTINEL_IDENTITY.owns
    assert "Skill Registry" in SENTINEL_IDENTITY.owns
    assert SENTINEL_IDENTITY.provider_owns == (
        "Reasoning",
        "Analysis",
        "Explanation",
        "Code suggestions",
    )
    assert SENTINEL_IDENTITY.excluded_platforms == ("Windows", "macOS")
    assert SENTINEL_IDENTITY.phase1_success_command == (
        "sentinel",
        "mission",
        "Fix this repository until all tests pass.",
    )

    assert SENTINEL_IDENTITY.accepts_provider("Ollama")
    assert not SENTINEL_IDENTITY.accepts_provider("ChatGPT")
    assert not SENTINEL_IDENTITY.accepts_provider("Gemini")
    assert not SENTINEL_IDENTITY.accepts_provider("DeepSeek")
    assert not SENTINEL_IDENTITY.accepts_provider("OpenRouter")


def test_identity_gate_accepts_phase_1_provider_independent_work():
    decision = evaluate_identity_alignment(
        target_phase=SentinelPhase.CORE,
        linux_first=True,
        preserves_ai_independence=True,
        preserves_mission_ownership=True,
        preserves_engineering_brain_ownership=True,
        avoids_vendor_lock_in=True,
    )

    assert decision.accepted is True
    assert decision.reasons == ()


def test_identity_gate_rejects_future_phase_and_vendor_lock_in():
    decision = evaluate_identity_alignment(
        target_phase=SentinelPhase.WEB,
        linux_first=False,
        preserves_ai_independence=False,
        preserves_mission_ownership=False,
        preserves_engineering_brain_ownership=False,
        avoids_vendor_lock_in=False,
    )

    assert decision.accepted is False
    assert decision.reasons == (
        "Phase 1 must stay focused on AIRIV Sentinel Core.",
        "Primary platform must remain Linux.",
        "AI providers must remain interchangeable reasoning resources.",
        "Mission ownership must remain inside Sentinel.",
        "Engineering Brain ownership must remain inside Sentinel.",
        "Implementation must avoid vendor lock-in.",
    )
