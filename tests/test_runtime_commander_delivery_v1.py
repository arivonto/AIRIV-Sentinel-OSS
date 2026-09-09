from sentinel.runtime import SentinelRuntime


def test_runtime_exposes_allowlisted_commander_delivery_projection():
    runtime = SentinelRuntime()
    incident = runtime.incident_manager.evaluate_anomaly(
        observation={
            "pane_id": "%runtime-delivery",
            "window_name": "runtime-delivery-test",
            "current_command": "python",
            "activity_state": "FAILED",
            "output_sha256": "e" * 64,
            "agent_identity": "AIRIV_SYSTEM",
        },
        anomaly_type="FAILED",
        reason="Runtime delivery synthetic failure",
        signal={"commander_required": True},
    )
    runtime.sync_incident_reports()

    delivery = runtime.get_commander_delivery_projection(
        generated_at="2026-09-09T00:00:00+00:00"
    )

    assert delivery.payload["incident_count"] == 1
    assert delivery.payload["commander_attention_count"] == 1
    assert delivery.payload["incidents"][0]["incident_id"] == incident.incident_id
    assert "signal_snapshot" not in str(delivery.to_dict())
    assert "output_sha256" not in str(delivery.to_dict())
