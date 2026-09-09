import json
import os
from pathlib import Path

import pytest

from sentinel.commander_delivery import CommanderDeliveryProjector
from sentinel.commander_delivery_dry_run import FileCommanderDeliveryTransport
from sentinel.commander_delivery_transport import (
    CommanderDeliveryIdentityLedger,
    CommanderDeliveryOrchestrator,
    CommanderDeliveryState,
)
from sentinel.unattended_reporting import UnattendedIncidentRollupBuilder


REPORT_SCHEMA = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"


def _projection():
    started_at = "2026-09-09T00:00:00+00:00"
    report = {
        "schema_version": REPORT_SCHEMA,
        "incident_id": "INC-DRY-RUN",
        "component_id": "%dry-run",
        "agent_identity": "AIRIV_SYSTEM",
        "anomaly_type": "FAILED",
        "started_at": started_at,
        "updated_at": started_at,
        "lifecycle_state": "TERMINAL",
        "final_outcome": "ESCALATED",
        "final_status": "ESCALATED",
        "commander_attention_required": True,
        "evidence_count": 1,
        "detection_and_understanding": [],
        "diagnostic_actions": [],
        "remediation_actions": [],
        "verification_results": [],
        "commander_decisions": [],
        "timeline": [
            {
                "sequence": 1,
                "timestamp": started_at,
                "signal_type": "ANOMALY",
                "reason": "Synthetic dry-run evidence",
                "observation_snapshot": {
                    "output_sha256": "raw-internal-hash",
                },
                "signal_snapshot": {
                    "credential": "must-not-leak",
                },
            }
        ],
    }
    rollup = UnattendedIncidentRollupBuilder().build(
        [report],
        generated_at="2026-09-09T00:01:00+00:00",
    )
    return CommanderDeliveryProjector().project(rollup)


def test_dry_run_transport_is_disabled_by_default(tmp_path):
    transport = FileCommanderDeliveryTransport(tmp_path)

    assert transport.enabled is False
    with pytest.raises(RuntimeError, match="disabled"):
        transport.deliver(
            delivery_id="DRY-001",
            destination_id="COMMANDER_PRIMARY",
            subject="Brief",
            body_markdown="# Brief",
        )
    assert list(tmp_path.iterdir()) == []


def test_enabled_dry_run_writes_one_atomic_local_artifact(tmp_path):
    transport = FileCommanderDeliveryTransport(tmp_path, enabled=True)
    result = transport.deliver(
        delivery_id="DRY-002",
        destination_id="COMMANDER_PRIMARY",
        subject="AIRIV Sentinel brief",
        body_markdown="# AIRIV Sentinel Commander Brief\n",
    )

    artifact = tmp_path / "DRY-002.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert result.state == CommanderDeliveryState.SUCCEEDED
    assert result.receipt_id.startswith("dryrun:")
    assert result.detail_code == "LOCAL_DRY_RUN_WRITTEN"
    assert payload["delivery_id"] == "DRY-002"
    assert payload["destination_id"] == "COMMANDER_PRIMARY"
    assert payload["body_markdown"] == "# AIRIV Sentinel Commander Brief\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_direct_duplicate_dry_run_never_overwrites(tmp_path):
    transport = FileCommanderDeliveryTransport(tmp_path, enabled=True)
    transport.deliver(
        delivery_id="DRY-003",
        destination_id="COMMANDER_PRIMARY",
        subject="First",
        body_markdown="# First",
    )
    original = (tmp_path / "DRY-003.json").read_bytes()

    with pytest.raises(FileExistsError, match="already exists"):
        transport.deliver(
            delivery_id="DRY-003",
            destination_id="COMMANDER_PRIMARY",
            subject="Second",
            body_markdown="# Second",
        )

    assert (tmp_path / "DRY-003.json").read_bytes() == original


def test_orchestrated_dry_run_is_replay_safe(tmp_path):
    transport_root = tmp_path / "outbox"
    ledger_root = tmp_path / "ledger"
    transport = FileCommanderDeliveryTransport(transport_root, enabled=True)
    orchestrator = CommanderDeliveryOrchestrator(
        CommanderDeliveryIdentityLedger(ledger_root),
        transport,
    )
    projection = _projection()

    first = orchestrator.deliver(
        projection=projection,
        delivery_id="DRY-004",
        destination_id="COMMANDER_PRIMARY",
    )
    replay = orchestrator.deliver(
        projection=projection,
        delivery_id="DRY-004",
        destination_id="COMMANDER_PRIMARY",
    )

    assert first.state == CommanderDeliveryState.SUCCEEDED
    assert first.attempted is True
    assert replay.state == CommanderDeliveryState.SUCCEEDED
    assert replay.attempted is False
    assert replay.replayed is True
    assert len(list(transport_root.glob("*.json"))) == 1


def test_dry_run_artifact_contains_only_projected_brief_not_raw_evidence(tmp_path):
    transport = FileCommanderDeliveryTransport(tmp_path / "outbox", enabled=True)
    orchestrator = CommanderDeliveryOrchestrator(
        CommanderDeliveryIdentityLedger(tmp_path / "ledger"),
        transport,
    )

    orchestrator.deliver(
        projection=_projection(),
        delivery_id="DRY-005",
        destination_id="COMMANDER_PRIMARY",
    )
    raw = (tmp_path / "outbox" / "DRY-005.json").read_text(
        encoding="utf-8"
    )

    assert "INC-DRY-RUN" in raw
    assert "raw-internal-hash" not in raw
    assert "must-not-leak" not in raw
    assert "observation_snapshot" not in raw
    assert "signal_snapshot" not in raw


def test_dry_run_rejects_delivery_id_path_traversal(tmp_path):
    transport = FileCommanderDeliveryTransport(tmp_path, enabled=True)

    with pytest.raises(ValueError, match="invalid characters"):
        transport.deliver(
            delivery_id="../../escape",
            destination_id="COMMANDER_PRIMARY",
            subject="Brief",
            body_markdown="# Brief",
        )

    assert not (tmp_path.parent / "escape.json").exists()


def test_dry_run_default_directory_is_test_isolated():
    transport = FileCommanderDeliveryTransport()

    assert transport.root == Path(
        os.environ["AIRIV_SENTINEL_DELIVERY_DRY_RUN_DIR"]
    )
    assert transport.root.name == "delivery_dry_run"
