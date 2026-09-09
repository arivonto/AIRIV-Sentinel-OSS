import json

import pytest

from sentinel.commander_delivery import CommanderDeliveryProjector
from sentinel.unattended_reporting import UnattendedIncidentRollupBuilder


REPORT_SCHEMA = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"


def _report(
    incident_id: str,
    *,
    attention: bool = False,
    final_status: str = "RECOVERED",
):
    started_at = "2026-09-08T20:00:00+00:00"
    timeline = [
        {
            "sequence": 1,
            "timestamp": started_at,
            "signal_type": "OBSERVATION",
            "reason": "Synthetic delivery evidence",
            "observation_snapshot": {
                "output_sha256": "secret-internal-hash",
            },
            "signal_snapshot": {
                "token": "must-never-reach-delivery",
            },
        }
    ]
    return {
        "schema_version": REPORT_SCHEMA,
        "incident_id": incident_id,
        "component_id": "%delivery",
        "agent_identity": "AIRIV_SYSTEM",
        "anomaly_type": "FAILED",
        "started_at": started_at,
        "updated_at": started_at,
        "lifecycle_state": "TERMINAL",
        "final_outcome": final_status,
        "final_status": final_status,
        "commander_attention_required": attention,
        "evidence_count": 1,
        "detection_and_understanding": timeline,
        "diagnostic_actions": [],
        "remediation_actions": [],
        "verification_results": [],
        "commander_decisions": [],
        "timeline": timeline,
    }


def _rollup(*reports):
    return UnattendedIncidentRollupBuilder().build(
        reports,
        generated_at="2026-09-09T00:00:00+00:00",
    )


def test_projection_contains_only_compact_allowlisted_operational_fields():
    delivery = CommanderDeliveryProjector().project(
        _rollup(
            _report(
                "INC-DELIVERY",
                attention=True,
                final_status="ESCALATED",
            )
        )
    )
    payload = delivery.to_dict()
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema_version"] == "AIRIV_SENTINEL_COMMANDER_DELIVERY_V1"
    assert payload["commander_attention_count"] == 1
    assert payload["incidents"][0]["incident_id"] == "INC-DELIVERY"
    assert "observation_snapshot" not in serialized
    assert "signal_snapshot" not in serialized
    assert "secret-internal-hash" not in serialized
    assert "must-never-reach-delivery" not in serialized


def test_unknown_rollup_field_fails_closed():
    source = _rollup(_report("INC-EXTRA")).to_dict()
    source["future_sensitive_field"] = {"raw": "secret"}

    with pytest.raises(ValueError, match="rollup schema mismatch"):
        CommanderDeliveryProjector().project(source)


def test_unknown_incident_summary_field_fails_closed():
    source = _rollup(_report("INC-INCIDENT-EXTRA")).to_dict()
    source["incidents"][0]["command"] = "rm -rf /"

    with pytest.raises(ValueError, match="schema mismatch"):
        CommanderDeliveryProjector().project(source)


def test_attention_queue_must_match_explicit_attention_flags():
    source = _rollup(
        _report(
            "INC-ATTENTION-MISMATCH",
            attention=True,
            final_status="ESCALATED",
        )
    ).to_dict()
    source["commander_attention_queue"] = []
    source["commander_attention_count"] = 0

    with pytest.raises(ValueError, match="does not match explicit attention flags"):
        CommanderDeliveryProjector().project(source)


def test_attention_queue_item_must_match_incident_summary_exactly():
    source = _rollup(
        _report(
            "INC-QUEUE-MISMATCH",
            attention=True,
            final_status="ESCALATED",
        )
    ).to_dict()
    source["commander_attention_queue"][0]["final_status"] = "RECOVERED"

    with pytest.raises(ValueError, match="does not match incident summary"):
        CommanderDeliveryProjector().project(source)


def test_projection_is_defensive_and_immutable():
    source = _rollup(_report("INC-IMMUTABLE")).to_dict()
    delivery = CommanderDeliveryProjector().project(source)
    source["incidents"][0]["final_status"] = "MUTATED"

    assert delivery.payload["incidents"][0]["final_status"] == "RECOVERED"
    with pytest.raises(TypeError):
        delivery.payload["incident_count"] = 99
    with pytest.raises(TypeError):
        delivery.payload["incidents"][0]["final_status"] = "MUTATED"


def test_subject_and_markdown_are_transport_ready_but_non_executing():
    delivery = CommanderDeliveryProjector().project(
        _rollup(
            _report(
                "INC-BRIEF",
                attention=True,
                final_status="ESCALATED",
            )
        )
    )

    assert delivery.subject() == "AIRIV Sentinel — 1 attention / 1 incidents"
    markdown = delivery.to_markdown()
    assert "# AIRIV Sentinel Commander Brief" in markdown
    assert "## Commander Attention Queue" in markdown
    assert "INC-BRIEF" in markdown
    assert "ESCALATED" in markdown
    assert "must-never-reach-delivery" not in markdown
