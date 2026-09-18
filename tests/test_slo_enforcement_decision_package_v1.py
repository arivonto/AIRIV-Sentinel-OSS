from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "AIRIV_SENTINEL_SLO_ENFORCEMENT_DECISION_PACKAGE_V1.md"
ROADMAP = ROOT / "AIRIV_SENTINEL_ROADMAP.md"
STATUS_REGISTRY = ROOT / "docs" / "AIRIV_SENTINEL_STATUS_CONTRACT_REGISTRY.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_slo_enforcement_decision_package_is_non_executable():
    text = _text(CONTRACT)

    assert "Status: **DECISION PACKAGE / NON-EXECUTABLE**" in text
    assert "SLO enforcement is **NOT AUTHORIZED**." in text
    assert "This package alone does not authorize autonomous enforcement." in text


def test_slo_enforcement_decision_package_requires_exact_commander_decision_record():
    text = _text(CONTRACT)
    required_fields = {
        "decision_id",
        "decided_at",
        "commander_identity",
        "approved_scope_id",
        "slo_definition_ids",
        "measurement_source_ids",
        "trust_requirements",
        "evaluation_window",
        "enforcement_mode",
        "allowed_consequences",
        "blast_radius",
        "cooldown",
        "retry_budget",
        "verification_requirements",
        "rollback_position",
        "production_activation_gate",
        "expiration",
    }

    for field in required_fields:
        assert field in text


def test_slo_enforcement_decision_modes_do_not_grant_effect_authority():
    text = _text(CONTRACT)

    for mode in ("REPORT_ONLY", "COMMANDER_CONFIRM", "AUTONOMOUS_BOUNDED"):
        assert f"### `{mode}`" in text

    assert "does not authorize alerts outside existing non-authoritative delivery surfaces" in text
    assert "does not execute the consequence" in text
    assert "Requires a separate effect-capable contract before implementation" in text


def test_slo_enforcement_decision_package_explicitly_excludes_production_effects():
    text = _text(CONTRACT)
    non_authorized = (
        "reading live host metrics",
        "evaluating current production health",
        "detecting or declaring SLO breaches in production",
        "creating external alerts",
        "throttling work",
        "executing remediation",
        "restarting services",
        "deploying or upgrading software",
        "executing rollback",
        "calling live AI providers",
        "mutating Incident lifecycle state",
        "configuring GitHub branch protection",
        "bypassing CI or repository governance",
    )

    for phrase in non_authorized:
        assert phrase in text


def test_roadmap_marks_next_step_as_commander_authority_review_not_enforcement():
    text = _text(ROADMAP)

    assert "### SLO Enforcement Decision Package — IMPLEMENTED / NON-EXECUTABLE" in text
    assert "### ACTIVE SAFE NEXT — SLO Enforcement Authority Review" in text
    assert "**SLO Enforcement Authority Review** — ACTIVE SAFE NEXT / Commander decision required" in text
    assert "**SLO Enforcement Design** — starts only after explicit Commander authority decision" in text


def test_status_registry_records_package_without_promoting_slo_enforcement():
    text = _text(STATUS_REGISTRY)

    assert "| SLO Enforcement Decision Package | **IMPLEMENTED / NON-EXECUTABLE** |" in text
    assert "Commander decision requirements only; no SLO enforcement" in text
    assert "Live AI Provider Adapter | **DECISION-GATED / DISABLED**" in text
    assert "Upgrade / Rollback Execution | **NOT AUTHORIZED**" in text
