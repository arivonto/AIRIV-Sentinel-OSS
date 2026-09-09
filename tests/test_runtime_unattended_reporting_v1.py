import os
from pathlib import Path

from sentinel.runtime import SentinelRuntime


def _observation(component_id: str = "%runtime-unattended"):
    return {
        "pane_id": component_id,
        "window_name": "runtime-unattended-test",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "d" * 64,
        "agent_identity": "AIRIV_SYSTEM",
    }


def _incident(runtime: SentinelRuntime, *, attention: bool = False):
    return runtime.incident_manager.evaluate_anomaly(
        observation=_observation(),
        anomaly_type="FAILED",
        reason="Runtime unattended synthetic failure",
        signal={"commander_required": attention},
    )


class _ForbiddenBoundary:
    def __getattr__(self, name):
        raise AssertionError(f"reporting touched forbidden boundary: {name}")


class _IdleCycle:
    def cycle(self):
        return None


class _EmptySensor:
    def process_tick(self):
        return []


class _DiagnosticSink:
    def submit(self, incidents):
        assert incidents == []


def _isolate_live_cycle_boundaries(runtime: SentinelRuntime):
    runtime.canary_live_execution = _IdleCycle()
    runtime.production_probe_live_execution = _IdleCycle()
    runtime.gate3_live_validation = _IdleCycle()
    runtime.gate4_autonomous_remediation = _IdleCycle()
    runtime.sensor_adapter = _EmptySensor()
    runtime.diagnostic = _DiagnosticSink()


def test_runtime_report_store_uses_isolated_test_directory():
    runtime = SentinelRuntime()

    assert runtime.incident_report_store.root == Path(
        os.environ["AIRIV_SENTINEL_INCIDENT_REPORT_DIR"]
    )
    assert runtime.incident_report_store.root.name == "incident_reports"


def test_bounded_sync_runs_immediately_then_waits_sixty_seconds():
    runtime = SentinelRuntime()
    incident = _incident(runtime)

    first = runtime._sync_incident_reports_if_due(monotonic_now=10.0)
    early = runtime._sync_incident_reports_if_due(monotonic_now=69.999)
    due = runtime._sync_incident_reports_if_due(monotonic_now=70.0)

    assert first.written_incident_ids == (incident.incident_id,)
    assert early is None
    assert due.written_incident_ids == ()
    assert due.unchanged_incident_ids == (incident.incident_id,)
    assert runtime._next_incident_report_sync_at == 130.0


def test_runtime_rollup_reads_durable_reports_and_attention_queue():
    runtime = SentinelRuntime()
    incident = _incident(runtime, attention=True)
    runtime.sync_incident_reports()

    rollup = runtime.get_unattended_rollup(
        generated_at="2026-09-09T00:00:00+00:00"
    )

    assert rollup.payload["incident_count"] == 1
    assert rollup.payload["commander_attention_count"] == 1
    assert (
        rollup.commander_attention_queue.items[0]["incident_id"]
        == incident.incident_id
    )


def test_terminal_transition_is_reconciled_on_next_due_sync():
    runtime = SentinelRuntime()
    incident = _incident(runtime)
    runtime._sync_incident_reports_if_due(monotonic_now=0.0)

    runtime.incident_manager.investigate(incident.component_id)
    runtime.incident_manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={"verified": True, "source": "runtime-report-test"},
        observation=_observation(),
        final_outcome="RECOVERED",
    )

    runtime._sync_incident_reports_if_due(monotonic_now=60.0)
    persisted = runtime.incident_report_store.get(incident.incident_id)

    assert persisted is not None
    assert persisted["lifecycle_state"] == "TERMINAL"
    assert persisted["final_status"] == "RECOVERED"


def test_reporting_sync_does_not_touch_authority_or_execution_boundaries():
    runtime = SentinelRuntime()
    incident = _incident(runtime)

    runtime.policy = _ForbiddenBoundary()
    runtime.commander = _ForbiddenBoundary()
    runtime.execution = _ForbiddenBoundary()
    runtime.gate = _ForbiddenBoundary()
    runtime.orchestrator = _ForbiddenBoundary()

    result = runtime.sync_incident_reports()

    assert result.written_incident_ids == (incident.incident_id,)
    assert runtime.incident_manager.get_active_incident(incident.component_id) is incident


def test_reporting_failure_is_visible_bounded_and_nonfatal(capsys):
    class FailingRecorder:
        def sync(self, manager):
            assert manager is not None
            raise ValueError("synthetic corrupt report")

    runtime = SentinelRuntime()
    runtime.incident_report_recorder = FailingRecorder()

    result = runtime._sync_incident_reports_if_due(monotonic_now=5.0)
    captured = capsys.readouterr()

    assert result is None
    assert runtime.last_incident_report_sync_result is None
    assert runtime.last_incident_report_sync_error == (
        "ValueError: synthetic corrupt report"
    )
    assert runtime._next_incident_report_sync_at == 65.0
    assert "[SENTINEL][REPORTING] incident report sync failed" in captured.err


def test_run_once_invokes_due_reporting_without_changing_return_contract():
    class SpyRecorder:
        def __init__(self):
            self.calls = 0

        def sync(self, manager):
            self.calls += 1
            assert manager is runtime.incident_manager
            return "SYNCED"

    runtime = SentinelRuntime()
    _isolate_live_cycle_boundaries(runtime)
    spy = SpyRecorder()
    runtime.incident_report_recorder = spy
    runtime.running = True
    runtime._next_incident_report_sync_at = 0.0

    incidents = runtime.run_once()

    assert incidents == []
    assert spy.calls == 1
    assert runtime.last_incident_report_sync_result == "SYNCED"
    assert runtime.last_incident_report_sync_error is None
