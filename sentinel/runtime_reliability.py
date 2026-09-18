"""Bounded, read-only runtime reliability evidence for AIRIV Sentinel.

This module owns no incident, diagnostic, remediation, execution, or lifecycle
authority. It records only process-local runtime cycle facts so reliability can
be inspected without polling production components or causing effects.
"""

from collections import deque
from dataclasses import dataclass
from threading import RLock


class RuntimeReliabilityError(RuntimeError):
    """Base error for invalid reliability-ledger operations."""


class RuntimeCycleInputError(RuntimeReliabilityError, ValueError):
    """Canonical runtime cycle received malformed component output."""


class RuntimeCycleOverlapError(RuntimeReliabilityError):
    """A second runtime cycle was rejected while one was already active."""


class RuntimeShutdownInProgressError(RuntimeReliabilityError):
    """Runtime teardown was rejected while a canonical cycle was active."""


class RuntimeDiagnosticShutdownInProgressError(RuntimeReliabilityError):
    """Diagnostic worker teardown did not reach a quiescent boundary."""


@dataclass(frozen=True, slots=True)
class RuntimeFailureEvidence:
    sequence: int
    cycle: int
    component: str
    error_type: str
    bounded: bool


@dataclass(frozen=True, slots=True)
class RuntimeHealthSnapshot:
    running: bool
    cycle_in_progress: bool
    diagnostic_shutdown_pending: bool
    cycles_started: int
    cycles_completed: int
    rejected_overlapping_cycles: int
    degraded_cycles: int
    consecutive_degraded_cycles: int
    total_bounded_failures: int
    total_unbounded_failures: int
    retained_failure_count: int
    failure_evidence_capacity: int
    last_failure: RuntimeFailureEvidence | None


class RuntimeReliabilityLedger:
    """Thread-safe bounded evidence ledger for canonical runtime cycles."""

    def __init__(self, evidence_capacity: int = 64) -> None:
        if type(evidence_capacity) is not int or evidence_capacity < 1:
            raise ValueError("evidence_capacity must be a positive integer")
        self._capacity = evidence_capacity
        self._lock = RLock()
        self._cycles_started = 0
        self._cycles_completed = 0
        self._rejected_overlapping_cycles = 0
        self._degraded_cycles = 0
        self._consecutive_degraded_cycles = 0
        self._total_bounded_failures = 0
        self._total_unbounded_failures = 0
        self._failure_sequence = 0
        self._current_cycle: int | None = None
        self._failures: deque[RuntimeFailureEvidence] = deque(
            maxlen=evidence_capacity
        )

    def begin_cycle(self) -> int:
        with self._lock:
            if self._current_cycle is not None:
                self._rejected_overlapping_cycles += 1
                raise RuntimeCycleOverlapError(
                    "runtime cycle already in progress"
                )
            self._cycles_started += 1
            self._current_cycle = self._cycles_started
            return self._current_cycle

    def record_failure(
        self,
        *,
        cycle: int,
        component: str,
        error: BaseException,
        bounded: bool,
    ) -> RuntimeFailureEvidence:
        if type(cycle) is not int or cycle < 1:
            raise ValueError("cycle must be a positive integer")
        if not isinstance(component, str) or not component.strip():
            raise ValueError("component must be non-empty text")
        if not isinstance(error, BaseException):
            raise TypeError("error must be an exception")
        if not isinstance(bounded, bool):
            raise TypeError("bounded must be bool")

        with self._lock:
            if cycle != self._current_cycle:
                raise RuntimeReliabilityError(
                    "failure must belong to the active runtime cycle"
                )
            self._failure_sequence += 1
            evidence = RuntimeFailureEvidence(
                sequence=self._failure_sequence,
                cycle=cycle,
                component=component,
                error_type=type(error).__name__,
                bounded=bounded,
            )
            self._failures.append(evidence)
            if bounded:
                self._total_bounded_failures += 1
            else:
                self._total_unbounded_failures += 1
            return evidence

    def complete_cycle(self, cycle: int, *, degraded: bool) -> None:
        if not isinstance(degraded, bool):
            raise TypeError("degraded must be bool")
        with self._lock:
            if cycle != self._current_cycle:
                raise RuntimeReliabilityError(
                    "only the active runtime cycle can be completed"
                )
            self._cycles_completed += 1
            if degraded:
                self._degraded_cycles += 1
                self._consecutive_degraded_cycles += 1
            else:
                self._consecutive_degraded_cycles = 0
            self._current_cycle = None

    def failures(self) -> tuple[RuntimeFailureEvidence, ...]:
        with self._lock:
            return tuple(self._failures)

    def snapshot(
        self,
        *,
        running: bool,
        diagnostic_shutdown_pending: bool = False,
    ) -> RuntimeHealthSnapshot:
        if not isinstance(running, bool):
            raise TypeError("running must be bool")
        if not isinstance(diagnostic_shutdown_pending, bool):
            raise TypeError("diagnostic_shutdown_pending must be bool")
        with self._lock:
            last_failure = self._failures[-1] if self._failures else None
            return RuntimeHealthSnapshot(
                running=running,
                cycle_in_progress=self._current_cycle is not None,
                diagnostic_shutdown_pending=diagnostic_shutdown_pending,
                cycles_started=self._cycles_started,
                cycles_completed=self._cycles_completed,
                rejected_overlapping_cycles=self._rejected_overlapping_cycles,
                degraded_cycles=self._degraded_cycles,
                consecutive_degraded_cycles=self._consecutive_degraded_cycles,
                total_bounded_failures=self._total_bounded_failures,
                total_unbounded_failures=self._total_unbounded_failures,
                retained_failure_count=len(self._failures),
                failure_evidence_capacity=self._capacity,
                last_failure=last_failure,
            )