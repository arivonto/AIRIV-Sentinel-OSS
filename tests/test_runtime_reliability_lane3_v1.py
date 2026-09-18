"""Lane 3 focused tests for bounded long-running runtime reliability."""

from threading import Event, Thread
from unittest.mock import Mock

import pytest

from sentinel.incidents.manager import Incident
from sentinel.runtime import SentinelRuntime
from sentinel.runtime_reliability import RuntimeCycleOverlapError
from sentinel.worker.capability_worker import SentinelCapabilityWorker
from sentinel.worker.state import WorkerState


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("AIRIV_SENTINEL_DIAGNOSTIC_DIR", str(tmp_path / "diagnostic"))
    candidate = SentinelRuntime()
    candidate.running = True
    for owner in (
        candidate.canary_live_execution,
        candidate.production_probe_live_execution,
        candidate.gate3_live_validation,
        candidate.gate4_autonomous_remediation,
    ):
        monkeypatch.setattr(owner, "cycle", Mock(return_value=None))
    monkeypatch.setattr(
        candidate,
        "_sync_incident_reports_if_due",
        Mock(return_value=None),
    )
    return candidate


def test_sensor_failure_is_bounded_and_skips_diagnostics(runtime, monkeypatch):
    sensor = Mock(side_effect=ValueError("private malformed sensor payload"))
    submit = Mock()
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", sensor)
    monkeypatch.setattr(runtime.diagnostic, "submit", submit)

    assert runtime.run_once() == []
    assert runtime.running
    submit.assert_not_called()

    health = runtime.get_runtime_health()
    assert health.cycles_started == health.cycles_completed == 1
    assert health.degraded_cycles == 1
    assert health.total_bounded_failures == 1
    assert health.total_unbounded_failures == 0
    assert health.last_failure.component == "sensor_adapter"
    assert health.last_failure.error_type == "ValueError"
    assert health.last_failure.bounded
    assert "private malformed sensor payload" not in repr(
        runtime.get_runtime_failure_evidence()
    )


def test_malformed_sensor_result_fails_closed(runtime, monkeypatch):
    submit = Mock()
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", lambda: [object()])
    monkeypatch.setattr(runtime.diagnostic, "submit", submit)

    assert runtime.run_once() == []
    submit.assert_not_called()
    evidence = runtime.get_runtime_failure_evidence()
    assert evidence[-1].component == "sensor_adapter"
    assert evidence[-1].error_type == "RuntimeCycleInputError"
    assert evidence[-1].bounded


def test_diagnostic_failure_is_bounded_after_canonical_detection(runtime, monkeypatch):
    incident = Incident("incident-1", "%1", "agent", "TEST")
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", lambda: [incident])
    submit = Mock(side_effect=RuntimeError("private diagnostic detail"))
    monkeypatch.setattr(runtime.diagnostic, "submit", submit)

    assert runtime.run_once() == [incident]
    submit.assert_called_once_with([incident])
    health = runtime.get_runtime_health()
    assert health.degraded_cycles == 1
    assert health.total_bounded_failures == 1
    assert health.last_failure.component == "diagnostic"
    assert health.last_failure.error_type == "RuntimeError"
    assert "private diagnostic detail" not in repr(
        runtime.get_runtime_failure_evidence()
    )


def test_effect_bearing_gate_failure_remains_unbounded(runtime, monkeypatch):
    sensor = Mock(return_value=[])
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", sensor)
    monkeypatch.setattr(
        runtime.gate4_autonomous_remediation,
        "cycle",
        Mock(side_effect=RuntimeError("gate failure")),
    )

    with pytest.raises(RuntimeError, match="gate failure"):
        runtime.run_once()

    sensor.assert_not_called()
    health = runtime.get_runtime_health()
    assert health.cycles_started == health.cycles_completed == 1
    assert health.degraded_cycles == 1
    assert health.total_bounded_failures == 0
    assert health.total_unbounded_failures == 1
    assert health.last_failure.component == "gate4_autonomous_remediation"
    assert not health.last_failure.bounded
    assert not health.cycle_in_progress


def test_health_projection_is_read_only(runtime, monkeypatch):
    sensor = Mock(return_value=[])
    submit = Mock()
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", sensor)
    monkeypatch.setattr(runtime.diagnostic, "submit", submit)

    runtime.run_once()
    before_sensor = sensor.call_count
    before_submit = submit.call_count
    first = runtime.get_runtime_health()
    second = runtime.get_runtime_health()
    evidence_first = runtime.get_runtime_failure_evidence()
    evidence_second = runtime.get_runtime_failure_evidence()

    assert first == second
    assert evidence_first == evidence_second == ()
    assert sensor.call_count == before_sensor
    assert submit.call_count == before_submit


def test_long_running_fault_simulation_has_bounded_evidence(runtime, monkeypatch):
    sensor_calls = 0
    diagnostic_calls = 0

    def sensor():
        nonlocal sensor_calls
        sensor_calls += 1
        if sensor_calls % 3 == 0:
            raise ValueError("synthetic sensor failure")
        return []

    def submit(incidents):
        nonlocal diagnostic_calls
        assert incidents == []
        diagnostic_calls += 1
        if diagnostic_calls % 5 == 0:
            raise RuntimeError("synthetic diagnostic failure")

    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", sensor)
    monkeypatch.setattr(runtime.diagnostic, "submit", submit)

    cycles = 5000
    for _ in range(cycles):
        assert runtime.run_once() == []

    health = runtime.get_runtime_health()
    evidence = runtime.get_runtime_failure_evidence()
    assert runtime.running
    assert health.cycles_started == health.cycles_completed == cycles
    assert health.degraded_cycles > 0
    assert health.total_bounded_failures > health.failure_evidence_capacity
    assert health.total_unbounded_failures == 0
    assert health.retained_failure_count == health.failure_evidence_capacity == 64
    assert len(evidence) == 64
    assert tuple(item.sequence for item in evidence) == tuple(
        range(evidence[0].sequence, evidence[-1].sequence + 1)
    )
    assert evidence[-1].sequence == health.total_bounded_failures
    assert not health.cycle_in_progress


def test_bounded_sensor_failure_does_not_fail_capability_worker(runtime, monkeypatch):
    sensor_calls = 0

    def sensor():
        nonlocal sensor_calls
        sensor_calls += 1
        if sensor_calls == 1:
            raise ValueError("synthetic")
        return []

    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", sensor)
    monkeypatch.setattr(runtime.diagnostic, "submit", Mock())
    worker = SentinelCapabilityWorker(runtime, interval=0.01)
    waits = 0

    def wait(interval):
        nonlocal waits
        assert interval == 0.01
        waits += 1
        return waits >= 3

    monkeypatch.setattr(worker._stop_event, "wait", wait)
    worker.start()
    worker._thread.join(2)
    try:
        assert not worker._thread.is_alive()
        assert worker.state() is WorkerState.RUNNING
        assert worker.health()
        assert worker.last_error is None
        assert worker.last_cycle_status == "OK"
        assert worker.heartbeat().iteration == 2
        assert runtime.get_runtime_health().total_bounded_failures == 1
    finally:
        worker.stop()
    assert worker.state() is WorkerState.STOPPED


def test_start_failure_rolls_back_running_state(runtime, monkeypatch):
    runtime.running = False
    monkeypatch.setattr(
        runtime.diagnostic,
        "start",
        Mock(side_effect=RuntimeError("start failed")),
    )

    with pytest.raises(RuntimeError, match="start failed"):
        runtime.start()
    assert not runtime.running
    assert not runtime.get_runtime_health().running


def test_shutdown_failure_still_fails_closed(runtime, monkeypatch):
    stop = Mock(side_effect=RuntimeError("shutdown failed"))
    monkeypatch.setattr(runtime.diagnostic, "stop", stop)

    with pytest.raises(RuntimeError, match="shutdown failed"):
        runtime.stop()
    stop.assert_called_once_with()
    assert not runtime.running
    assert not runtime.get_runtime_health().running


def test_overlapping_cycle_is_rejected_without_state_corruption(runtime, monkeypatch):
    entered_sensor = Event()
    release_sensor = Event()
    first_result = []
    first_errors = []

    def sensor():
        entered_sensor.set()
        assert release_sensor.wait(2)
        return []

    def run_first_cycle():
        try:
            first_result.append(runtime.run_once())
        except BaseException as exc:
            first_errors.append(exc)

    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", sensor)
    monkeypatch.setattr(runtime.diagnostic, "submit", Mock())

    thread = Thread(target=run_first_cycle, daemon=True)
    thread.start()
    assert entered_sensor.wait(2)

    with pytest.raises(RuntimeCycleOverlapError, match="already in progress"):
        runtime.run_once()

    during = runtime.get_runtime_health()
    assert during.cycle_in_progress
    assert during.cycles_started == 1
    assert during.cycles_completed == 0
    assert during.rejected_overlapping_cycles == 1
    assert during.total_bounded_failures == 0
    assert during.total_unbounded_failures == 0

    release_sensor.set()
    thread.join(2)
    assert not thread.is_alive()
    assert first_errors == []
    assert first_result == [[]]

    after = runtime.get_runtime_health()
    assert after.cycles_started == after.cycles_completed == 1
    assert after.rejected_overlapping_cycles == 1
    assert not after.cycle_in_progress

    assert runtime.run_once() == []
    final = runtime.get_runtime_health()
    assert final.cycles_started == final.cycles_completed == 2
    assert final.rejected_overlapping_cycles == 1
    assert not final.cycle_in_progress
