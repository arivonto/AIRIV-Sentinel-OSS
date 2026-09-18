from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIREWALL = ROOT / "docs" / "constitution" / "BLUEPRINT_FIREWALL.md"


def test_blueprint_firewall_is_locked_phase1_guardrail():
    text = FIREWALL.read_text(encoding="utf-8")

    assert "Status: FINAL LOCKED" in text
    assert "Current Phase" in text
    assert "**Phase 1**" in text
    assert "AIRIV Sentinel Core" in text
    assert "Finish Phase 1." in text


def test_blueprint_firewall_rejects_scope_creep_and_future_phase_work():
    text = FIREWALL.read_text(encoding="utf-8")

    assert "scope creep" in text
    assert "No Feature Expansion" in text
    assert "No Architecture Expansion" in text
    assert "No implementation belonging to a future roadmap phase" in text
    assert "Everything else can wait." in text


def test_blueprint_firewall_preserves_linux_ai_independence_and_evidence():
    text = FIREWALL.read_text(encoding="utf-8")

    assert "No Vendor Lock-in" in text
    assert "Linux First" in text
    assert "Reality First" in text
    assert "Evidence First" in text
    assert "Verification First" in text
