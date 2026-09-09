import json
from pathlib import Path

import pytest

from sentinel.commander_delivery import CommanderDeliveryProjector
from sentinel.commander_delivery_transport import (
    CommanderDeliveryIdentityLedger,
    CommanderDeliveryOrchestrator,
    CommanderDeliveryState,
    CommanderTransportResult,
    DisabledCommanderDeliveryTransport,
    commander_delivery_projection_sha256,
)
from sentinel.unattended_reporting import UnattendedIncidentRollupBuilder


REPORT_SCHEMA = "AIRIV_SENTINEL_INCIDENT_REPORT_V1"


def _projection():
    started_at = "2026-09-09T00:00:00+00:00"
    report = {
        "schema_version": REPORT_SCHEMA,
        "incident_id": "INC-DELIVERY-IDENTITY",
        "component_id": "%delivery-identity",
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
                "reason": "Synthetic delivery identity evidence",
                "observation_snapshot": {},
                "signal_snapshot": {},
            }
        ],
    }
    rollup = UnattendedIncidentRollupBuilder().build(
        [report],
        generated_at="2026-09-09T00:01:00+00:00",
    )
    return CommanderDeliveryProjector().project(rollup)


class _SuccessTransport:
    name = "TEST_SUCCESS"
    enabled = True

    def __init__(self):
        self.calls = []

    def deliver(self, **kwargs):
        self.calls.append(kwargs)
        return CommanderTransportResult(
            state=CommanderDeliveryState.SUCCEEDED,
            receipt_id="receipt-001",
            detail_code="ACCEPTED",
        )


class _FailedTransport:
    name = "TEST_FAILED"
    enabled = True

    def deliver(self, **kwargs):
        return CommanderTransportResult(
            state=CommanderDeliveryState.FAILED,
            detail_code="REJECTED",
        )


class _UnknownTransport:
    name = "TEST_UNKNOWN"
    enabled = True

    def deliver(self, **kwargs):
        return CommanderTransportResult(
            state=CommanderDeliveryState.UNKNOWN,
            detail_code="OUTCOME_UNCERTAIN",
        )


class _ExplodingTransport:
    name = "TEST_EXCEPTION"
    enabled = True

    def __init__(self):
        self.calls = 0

    def deliver(self, **kwargs):
        self.calls += 1
        raise RuntimeError("secret-token-that-must-not-be-persisted")


def test_default_transport_is_disabled_and_creates_no_ledger_record(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    orchestrator = CommanderDeliveryOrchestrator(ledger=ledger)

    result = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-001",
        destination_id="COMMANDER_PRIMARY",
    )

    assert isinstance(orchestrator.transport, DisabledCommanderDeliveryTransport)
    assert result.state == CommanderDeliveryState.DISABLED
    assert result.attempted is False
    assert result.delivered is False
    assert result.detail_code == "TRANSPORT_DISABLED"
    assert ledger.get("DELIVERY-001") is None


def test_successful_delivery_is_durable_and_replay_safe(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    transport = _SuccessTransport()
    orchestrator = CommanderDeliveryOrchestrator(
        ledger=ledger,
        transport=transport,
    )

    first = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-002",
        destination_id="COMMANDER_PRIMARY",
    )
    replay = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-002",
        destination_id="COMMANDER_PRIMARY",
    )

    assert first.state == CommanderDeliveryState.SUCCEEDED
    assert first.attempted is True
    assert first.delivered is True
    assert first.replayed is False
    assert first.receipt_id == "receipt-001"
    assert replay.state == CommanderDeliveryState.SUCCEEDED
    assert replay.attempted is False
    assert replay.delivered is True
    assert replay.replayed is True
    assert len(transport.calls) == 1


def test_replay_with_different_destination_fails_closed(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    transport = _SuccessTransport()
    orchestrator = CommanderDeliveryOrchestrator(ledger, transport)

    orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-003",
        destination_id="COMMANDER_PRIMARY",
    )

    with pytest.raises(RuntimeError, match="does not match original bound effect"):
        orchestrator.deliver(
            projection=projection,
            delivery_id="DELIVERY-003",
            destination_id="COMMANDER_SECONDARY",
        )

    assert len(transport.calls) == 1


def test_replay_with_different_projection_fails_closed(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    transport = _SuccessTransport()
    orchestrator = CommanderDeliveryOrchestrator(ledger, transport)

    orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-004",
        destination_id="COMMANDER_PRIMARY",
    )

    changed = projection.to_dict()
    changed["generated_at"] = "2026-09-09T00:02:00+00:00"
    from sentinel.commander_delivery import CommanderDeliveryProjection
    from types import MappingProxyType

    changed_projection = CommanderDeliveryProjection(MappingProxyType(changed))

    with pytest.raises(RuntimeError, match="does not match original bound effect"):
        orchestrator.deliver(
            projection=changed_projection,
            delivery_id="DELIVERY-004",
            destination_id="COMMANDER_PRIMARY",
        )

    assert len(transport.calls) == 1


def test_definitive_transport_failure_is_terminal_and_not_retried(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    orchestrator = CommanderDeliveryOrchestrator(
        ledger,
        _FailedTransport(),
    )

    first = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-005",
        destination_id="COMMANDER_PRIMARY",
    )
    replay = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-005",
        destination_id="COMMANDER_PRIMARY",
    )

    assert first.state == CommanderDeliveryState.FAILED
    assert first.delivered is False
    assert first.detail_code == "REJECTED"
    assert replay.state == CommanderDeliveryState.FAILED
    assert replay.replayed is True


def test_transport_reported_unknown_is_terminal_and_not_retried(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    orchestrator = CommanderDeliveryOrchestrator(
        ledger,
        _UnknownTransport(),
    )

    first = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-006",
        destination_id="COMMANDER_PRIMARY",
    )
    replay = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-006",
        destination_id="COMMANDER_PRIMARY",
    )

    assert first.state == CommanderDeliveryState.UNKNOWN
    assert first.unknown_reason == "transport_reported_unknown"
    assert replay.state == CommanderDeliveryState.UNKNOWN
    assert replay.replayed is True


def test_transport_exception_becomes_unknown_without_persisting_message(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    transport = _ExplodingTransport()
    orchestrator = CommanderDeliveryOrchestrator(ledger, transport)

    result = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-007",
        destination_id="COMMANDER_PRIMARY",
    )
    replay = orchestrator.deliver(
        projection=projection,
        delivery_id="DELIVERY-007",
        destination_id="COMMANDER_PRIMARY",
    )

    record_path = tmp_path / "DELIVERY-007" / "record.json"
    raw = record_path.read_text(encoding="utf-8")

    assert result.state == CommanderDeliveryState.UNKNOWN
    assert result.unknown_reason == "transport_exception:RuntimeError"
    assert "secret-token-that-must-not-be-persisted" not in raw
    assert replay.replayed is True
    assert transport.calls == 1


def test_ledger_never_persists_subject_body_or_raw_projection(tmp_path):
    projection = _projection()
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    transport = _SuccessTransport()
    CommanderDeliveryOrchestrator(ledger, transport).deliver(
        projection=projection,
        delivery_id="DELIVERY-008",
        destination_id="COMMANDER_PRIMARY",
    )

    raw = (tmp_path / "DELIVERY-008" / "record.json").read_text(
        encoding="utf-8"
    )

    assert projection.subject() not in raw
    assert "AIRIV Sentinel Commander Brief" not in raw
    assert "INC-DELIVERY-IDENTITY" not in raw
    assert commander_delivery_projection_sha256(projection) in raw


def test_delivery_id_path_traversal_is_rejected(tmp_path):
    ledger = CommanderDeliveryIdentityLedger(tmp_path)

    with pytest.raises(ValueError, match="invalid characters"):
        ledger.get("../../outside")

    assert not (tmp_path.parent / "outside").exists()


def test_malformed_durable_record_fails_closed(tmp_path):
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    directory = tmp_path / "DELIVERY-009"
    directory.mkdir()
    (directory / "record.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="malformed"):
        ledger.get("DELIVERY-009")


def test_transport_result_rejects_control_characters():
    with pytest.raises(ValueError, match="control characters"):
        CommanderTransportResult(
            state=CommanderDeliveryState.SUCCEEDED,
            receipt_id="receipt\nsecret",
        )


def test_nonterminal_existing_identity_blocks_duplicate_send(tmp_path):
    projection = _projection()
    digest = commander_delivery_projection_sha256(projection)
    ledger = CommanderDeliveryIdentityLedger(tmp_path)
    ledger.claim(
        delivery_id="DELIVERY-010",
        projection_sha256=digest,
        destination_id="COMMANDER_PRIMARY",
        transport_name="TEST_SUCCESS",
    )
    transport = _SuccessTransport()

    with pytest.raises(RuntimeError, match="non-terminal state"):
        CommanderDeliveryOrchestrator(ledger, transport).deliver(
            projection=projection,
            delivery_id="DELIVERY-010",
            destination_id="COMMANDER_PRIMARY",
        )

    assert transport.calls == []
