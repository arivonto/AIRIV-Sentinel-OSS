from datetime import datetime, timedelta, timezone

import pytest

from sentinel.slo_report_only_authority import (
    REPORT_ONLY,
    REPORT_PROJECTION,
    SloReportOnlyAuthorityDecision,
    validate_report_only_decision,
)


NOW = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)


def _decision(**overrides):
    values = dict(
        decision_id="commander-slo-report-only-20260912",
        decided_at=NOW,
        commander_identity="commander-ariv",
        approved_scope_id="sentinel-passive-observability-v1",
        slo_definition_ids=(),
        measurement_source_ids=(),
        trust_requirements="detached-source-and-window-identity",
        evaluation_window="caller-supplied-detached-window-only",
        enforcement_mode=REPORT_ONLY,
        allowed_consequences=(REPORT_PROJECTION,),
        blast_radius="none",
        cooldown="not-applicable-report-only",
        retry_budget="zero-effect-retries",
        verification_requirements="projection-integrity-only",
        rollback_position="not-authorized",
        production_activation_gate="not-authorized",
        expiration=NOW + timedelta(days=7),
    )
    values.update(overrides)
    return SloReportOnlyAuthorityDecision(**values)


def test_valid_report_only_decision_is_accepted():
    validate_report_only_decision(_decision(), now=NOW)


@pytest.mark.parametrize(
    "override",
    [
        {"enforcement_mode": "COMMANDER_CONFIRM"},
        {"allowed_consequences": ("external_alert",)},
        {"approved_scope_id": ""},
        {"expiration": NOW},
    ],
)
def test_report_only_decision_fails_closed(override):
    with pytest.raises(ValueError):
        validate_report_only_decision(_decision(**override), now=NOW)
