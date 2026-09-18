from pathlib import Path

from sentinel.product_identity import SENTINEL_IDENTITY


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "BLUEPRINT.md"
BLUEPRINT_V2 = ROOT / "docs" / "constitution" / "AIRIV_SENTINEL_BLUEPRINT_V2.md"
MASTER_PROMPT = ROOT / "docs" / "constitution" / "MASTER_PROMPT.md"


def test_blueprint_v2_is_canonical_root_blueprint():
    assert BLUEPRINT.read_text(encoding="utf-8") == BLUEPRINT_V2.read_text(
        encoding="utf-8"
    )


def test_blueprint_v2_declares_phase1_definition_of_success():
    text = BLUEPRINT_V2.read_text(encoding="utf-8")

    assert "This document is the highest governing document" in text
    assert "sentinel mission \"Fix this repository until all tests pass.\"" in text
    assert "Windows is outside the scope of Blueprint v2." in text
    assert "macOS is outside the scope of Blueprint v2." in text
    assert "proprietary APIs" in text
    assert "proprietary models" in text
    assert "proprietary subscriptions" in text
    assert "proprietary workflows" in text


def test_master_prompt_points_to_blueprint_v2_as_highest_authority():
    text = MASTER_PROMPT.read_text(encoding="utf-8")

    assert "AIRIV_SENTINEL_BLUEPRINT_V2.md" in text
    assert "This document defines WHAT Sentinel is." in text
    assert "Routine engineering proceeds autonomously." in text
    assert "Build AIRIV Sentinel Core until Phase 1 Definition of Success" in text


def test_runtime_identity_matches_blueprint_v2_ownership():
    assert "Operational Knowledge" in SENTINEL_IDENTITY.owns
    assert "Skill Registry" in SENTINEL_IDENTITY.owns
    assert "Code suggestions" in SENTINEL_IDENTITY.provider_owns
    assert SENTINEL_IDENTITY.excluded_platforms == ("Windows", "macOS")
