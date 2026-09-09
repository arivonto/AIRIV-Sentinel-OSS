from copy import deepcopy

import pytest

from sentinel.unattended_reporting import UnattendedIncidentRollupBuilder


REPORT_SCHEMA = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"


def _report(
    incident_id: str,
    started_at: str,
    *,
    final_status: str = "RECOVERED",
    attention: bool = False,
    evidence_count: int = 1,
):
    timeline = [
        {
            "sequence": index + 1,
            "timestamp": started_at,
            "signal_type": "OBSERVATION",
            "reason": "Synthetic unattended evidence",
            "observation_snapshot": {},
            "signal_snapshot": {},
        }
        for index in range(evidence_count)
    ]
    return {
        "schema_version": REPORT_SCHEMA,
        "incident_id": incident_id,
        "component_id": f"%{incident_id[-1]}",
        "agent_identity": "AIRIV_SYSTEM",
        "anomaly_type": "FAILED",
        "started_at": started_at,
        "updated_at": started_at,
        "lifecycle_state": "TERMINAL",
        "final_outcome": final_status,
        "final_status": final_status,
        "commander_attention_required": attention,
        "evidence_count": evidence_count,
        "detection_and_understanding": timeline[:1],
        "diagnostic_actions": [],
        "remediation_actions": [],
        "verification_results": [],
        "commander_decisions": [],
        "timeline": timeline,
    }


def test_rollup_counts_incidents_statuses_and_evidence():
    builder = UnattendedIncidentRollupBuilder()
    reports = [
        _report("INC-001", "2026-09-08T20:00:00+00:00", evidence_count=2),
        _report(
            "INC-002",
            "2026-09-08T21:00:00+00:00",
            final_status="ESCALATED",
            attention=True,
            evidence_count=3,
        ),
    ]

    rollup = builder.build(
        reports,
        generated_at="2026-09-09T00:00:00+00:00",
    )

    assert rollup.payload["incident_count"] == 2
    assert rollup.payload["evidence_count"] == 5
    assert rollup.payload["final_status_counts"]["RECOVERED"] == 1
    assert rollup.payload["final_status_counts"]["ESCALATED"] == 1
    assert rollup.payload["commander_attention_count"] == 1


def test_attention_queue_contains_only_explicit_attention_reports():
    builder = UnattendedIncidentRollupBuilder()
    rollup = builder.build(
        [
            _report("INC-001", "2026-09-08T20:00:00+00:00"),
            _report(
                "INC-002",
                "2026-09-08T21:00:00+00:00",
                final_status="UNRESOLVED",
                attention=False,
            ),
            _report(
                "INC-003",
                "2026-09-08T22:00:00+00:00",
                final_status="ESCALATED",
                attention=True,
            ),
        ],
        generated_at="2026-09-09T00:00:00+00:00",
    )

    queue = rollup.commander_attention_queue

    assert len(queue) == 1
    assert queue.items[0]["incident_id"] == "INC-003"
    assert queue.to_list()[0]["final_status"] == "ESCALATED"


def test_rollup_is_chronological_not_input_order():
    builder = UnattendedIncidentRollupBuilder()
    rollup = builder.build(
        [
            _report("INC-LATE", "2026-09-08T23:00:00+00:00"),
            _report("INC-EARLY", "2026-09-08T19:00:00+00:00"),
        ],
        generated_at="2026-09-09T00:00:00+00:00",
    )

    assert [
        item["incident_id"] for item in rollup.payload["incidents"]
    ] == ["INC-EARLY", "INC-LATE"]


def test_window_is_start_inclusive_and_end_exclusive():
    builder = UnattendedIncidentRollupBuilder()
    rollup = builder.build(
        [
            _report("INC-BEFORE", "2026-09-08T17:59:59+00:00"),
            _report("INC-START", "2026-09-08T18:00:00+00:00"),
            _report("INC-IN", "2026-09-08T23:59:59+00:00"),
            _report("INC-END", "2026-09-09T00:00:00+00:00"),
        ],
        window_start="2026-09-08T18:00:00+00:00",
        window_end="2026-09-09T00:00:00+00:00",
        generated_at="2026-09-09T00:01:00+00:00",
    )

    assert [
        item["incident_id"] for item in rollup.payload["incidents"]
    ] == ["INC-START", "INC-IN"]


def test_naive_timestamps_fail_closed():
    builder = UnattendedIncidentRollupBuilder()
    report = _report("INC-NAIVE", "2026-09-08T20:00:00")

    with pytest.raises(ValueError, match="timezone"):
        builder.build(
            [report],
            generated_at="2026-09-09T00:00:00+00:00",
        )


def test_unsupported_report_schema_fails_closed():
    builder = UnattendedIncidentRollupBuilder()
    report = _report("INC-SCHEMA", "2026-09-08T20:00:00+00:00")
    report["schema_version"] = "UNKNOWN_SCHEMA"

    with pytest.raises(ValueError, match="unsupported incident report schema"):
        builder.build(
            [report],
            generated_at="2026-09-09T00:00:00+00:00",
        )


def test_rollup_is_defensive_and_immutable():
    builder = UnattendedIncidentRollupBuilder()
    source = _report(
        "INC-IMMUTABLE",
        "2026-09-08T20:00:00+00:00",
        attention=True,
    )
    before = deepcopy(source)

    rollup = builder.build(
        [source],
        generated_at="2026-09-09T00:00:00+00:00",
    )
    source["final_status"] = "MUTATED"

    assert before["final_status"] == "RECOVERED"
    assert rollup.payload["incidents"][0]["final_status"] == "RECOVERED"
    with pytest.raises(TypeError):
        rollup.payload["incident_count"] = 99
    with pytest.raises(TypeError):
        rollup.commander_attention_queue.items[0]["final_status"] = "MUTATED"


def test_build_from_store_uses_recovery_read_surface_only():
    class ReadOnlyStore:
        def __init__(self):
            self.recover_calls = 0

        def recover(self):
            self.recover_calls += 1
            return [_report("INC-STORE", "2026-09-08T20:00:00+00:00")]

        def save(self, _report):
            raise AssertionError("rollup must not write to report store")

    store = ReadOnlyStore()
    rollup = UnattendedIncidentRollupBuilder().build_from_store(
        store,
        generated_at="2026-09-09T00:00:00+00:00",
    )

    assert store.recover_calls == 1
    assert rollup.payload["incident_count"] == 1


def test_markdown_exposes_summary_and_attention_queue():
    rollup = UnattendedIncidentRollupBuilder().build(
        [
            _report(
                "INC-ATTN",
                "2026-09-08T20:00:00+00:00",
                final_status="ESCALATED",
                attention=True,
            )
        ],
        generated_at="2026-09-09T00:00:00+00:00",
    )

    markdown = rollup.to_markdown()

    assert "# AIRIV Sentinel Unattended Incident Rollup" in markdown
    assert "## Commander Attention Queue" in markdown
    assert "INC-ATTN" in markdown
    assert "ESCALATED" in markdown
