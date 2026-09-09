from sentinel.commander_delivery_dry_run import FileCommanderDeliveryTransport
from sentinel.commander_delivery_transport import (
    CommanderDeliveryIdentityLedger,
    CommanderDeliveryOrchestrator,
    CommanderDeliveryState,
    CommanderTransportResult,
)
from sentinel.runtime import SentinelRuntime


def _incident(runtime: SentinelRuntime):
    return runtime.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "%runtime-delivery-effect",
            "window_name": "runtime-delivery-effect-test",
            "current_command": "python",
            "activity_state": "FAILED",
            "output_sha256": "f" * 64,
            "agent_identity": "AIRIV_SYSTEM",
        },
        anomaly_type="FAILED",
        reason="Runtime delivery effect synthetic failure",
        signal={"commander_required": True},
    )


class _IdleCycle:
    def cycle(self):
        return None


class _EmptySensor:
    def process_tick(self):
        return []


class _DiagnosticSink:
    def submit(self, incidents):
        assert incidents == []


class _CountingTransport:
    name = "COUNTING_TRANSPORT"
    enabled = True

    def __init__(self):
        self.calls = 0

    def deliver(self, **kwargs):
        self.calls += 1
        return CommanderTransportResult(
            state=CommanderDeliveryState.SUCCEEDED,
            receipt_id="counting-receipt",
        )


def _isolate_cycle(runtime: SentinelRuntime):
    runtime.canary_live_execution = _IdleCycle()
    runtime.production_probe_live_execution = _IdleCycle()
    runtime.gate3_live_validation = _IdleCycle()
    runtime.gate4_autonomous_remediation = _IdleCycle()
    runtime.sensor_adapter = _EmptySensor()
    runtime.diagnostic = _DiagnosticSink()


def test_runtime_delivery_boundary_is_disabled_by_default():
    runtime = SentinelRuntime()
    incident = _incident(runtime)
    runtime.sync_incident_reports()

    result = runtime.deliver_commander_brief(
        delivery_id="RUNTIME-DELIVERY-001",
        destination_id="COMMANDER_PRIMARY",
        generated_at="2026-09-09T00:01:00+00:00",
    )

    assert result.state == CommanderDeliveryState.DISABLED
    assert result.attempted is False
    assert result.delivered is False
    assert runtime.commander_delivery.ledger.get("RUNTIME-DELIVERY-001") is None
    assert runtime.incident_manager.get_active_incident(incident.component_id) is incident


def test_runtime_can_explicitly_compose_local_dry_run_without_network(tmp_path):
    runtime = SentinelRuntime()
    _incident(runtime)
    runtime.sync_incident_reports()
    transport = FileCommanderDeliveryTransport(
        tmp_path / "outbox",
        enabled=True,
    )
    runtime.commander_delivery = CommanderDeliveryOrchestrator(
        CommanderDeliveryIdentityLedger(tmp_path / "ledger"),
        transport,
    )

    result = runtime.deliver_commander_brief(
        delivery_id="RUNTIME-DELIVERY-002",
        destination_id="COMMANDER_PRIMARY",
        generated_at="2026-09-09T00:01:00+00:00",
    )

    assert result.state == CommanderDeliveryState.SUCCEEDED
    assert result.delivered is True
    assert (tmp_path / "outbox" / "RUNTIME-DELIVERY-002.json").exists()


def test_daemon_run_once_never_invokes_delivery_transport_automatically(tmp_path):
    runtime = SentinelRuntime()
    _isolate_cycle(runtime)
    transport = _CountingTransport()
    runtime.commander_delivery = CommanderDeliveryOrchestrator(
        CommanderDeliveryIdentityLedger(tmp_path / "ledger"),
        transport,
    )
    runtime.running = True

    incidents = runtime.run_once()

    assert incidents == []
    assert transport.calls == 0
