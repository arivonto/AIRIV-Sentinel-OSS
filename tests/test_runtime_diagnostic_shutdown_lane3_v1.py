"""Lane 3 fault-injection for diagnostic shutdown containment and reuse."""

from unittest.mock import Mock

import pytest

from sentinel.runtime import SentinelRuntime
from sentinel.runtime_reliability import (
    RuntimeDiagnosticShutdownInProgressError,
)


class _ControlledThread:
    """Minimal non-production thread double for deterministic shutdown tests."""

    def __init__(self, *, alive: bool = True) -> None:
        self.alive = alive
        self.join_timeouts: list[float | None] = []

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)


def test_diagnostic_join_timeout_is_visible_and_retains_pending_handle():
    runtime = SentinelRuntime()
    stalled = _ControlledThread()
    runtime.diagnostic._thread = stalled
    runtime.running = True

    with pytest.raises(
        RuntimeDiagnosticShutdownInProgressError,
        match="did not quiesce",
    ):
        runtime.stop()

    # RuntimeDiagnosticCoordinator.stop() deliberately drops its own thread
    # reference before joining. Lane 3 must retain the exact in-flight handle
    # when the bounded join returns without quiescence.
    assert runtime.diagnostic._thread is None
    assert runtime._pending_diagnostic_thread is stalled
    assert stalled.join_timeouts == [2.0]

    health = runtime.get_runtime_health()
    assert not health.running
    assert not health.cycle_in_progress
    assert health.diagnostic_shutdown_pending
    assert health.cycles_started == health.cycles_completed == 0
    assert health.total_bounded_failures == 0
    assert health.total_unbounded_failures == 0
    assert runtime.get_runtime_failure_evidence() == ()


def test_restart_is_fail_closed_while_diagnostic_shutdown_is_pending(monkeypatch):
    runtime = SentinelRuntime()
    stalled = _ControlledThread()
    runtime._pending_diagnostic_thread = stalled
    diagnostic_start = Mock()
    monkeypatch.setattr(runtime.diagnostic, "start", diagnostic_start)

    with pytest.raises(
        RuntimeDiagnosticShutdownInProgressError,
        match="start requires diagnostic shutdown quiescence",
    ):
        runtime.start()

    diagnostic_start.assert_not_called()
    health = runtime.get_runtime_health()
    assert not health.running
    assert health.diagnostic_shutdown_pending

    # Once the retained worker is genuinely quiescent, the same canonical
    # runtime can restart without accumulating stale lifecycle state.
    stalled.alive = False
    runtime.start()
    diagnostic_start.assert_called_once_with()
    assert runtime.running
    health = runtime.get_runtime_health()
    assert not health.diagnostic_shutdown_pending
    assert runtime._pending_diagnostic_thread is None

    runtime.stop()
    assert not runtime.running


def test_repeated_shutdown_timeout_recovery_has_no_state_or_handle_leak(monkeypatch):
    runtime = SentinelRuntime()
    diagnostic_start = Mock()
    monkeypatch.setattr(runtime.diagnostic, "start", diagnostic_start)
    runtime.running = True

    stalled_threads = []
    repetitions = 256

    for _ in range(repetitions):
        stalled = _ControlledThread()
        stalled_threads.append(stalled)
        runtime.diagnostic._thread = stalled

        with pytest.raises(RuntimeDiagnosticShutdownInProgressError):
            runtime.stop()

        health = runtime.get_runtime_health()
        assert not health.running
        assert health.diagnostic_shutdown_pending
        assert runtime._pending_diagnostic_thread is stalled
        assert runtime.diagnostic._thread is None

        stalled.alive = False
        runtime.start()

        health = runtime.get_runtime_health()
        assert health.running
        assert not health.diagnostic_shutdown_pending
        assert runtime._pending_diagnostic_thread is None
        assert runtime.diagnostic._thread is None

    assert diagnostic_start.call_count == repetitions
    assert all(not thread.is_alive() for thread in stalled_threads)
    assert all(thread.join_timeouts == [2.0] for thread in stalled_threads)

    # Lifecycle-only fault injection must not fabricate canonical cycle failure
    # evidence or corrupt cycle accounting across repeated retries.
    health = runtime.get_runtime_health()
    assert health.cycles_started == health.cycles_completed == 0
    assert health.degraded_cycles == 0
    assert health.total_bounded_failures == 0
    assert health.total_unbounded_failures == 0
    assert health.retained_failure_count == 0
    assert runtime.get_runtime_failure_evidence() == ()

    runtime.stop()
    final = runtime.get_runtime_health()
    assert not final.running
    assert not final.diagnostic_shutdown_pending
    assert runtime._pending_diagnostic_thread is None
