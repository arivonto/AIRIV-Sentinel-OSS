"""Passive incident/remediation metrics and reconciliation projections."""

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Any


class ReconciliationHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class IncidentMetricsProjection:
    active_total: int
    active_lifecycle_counts: tuple[tuple[str, int], ...]
    history_terminal_total: int
    history_outcome_counts: tuple[tuple[str, int], ...]
    unknown_active_lifecycle_counts: tuple[tuple[str, int], ...]
    unknown_history_outcome_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RemediationMetricsProjection:
    total: int
    status_counts: tuple[tuple[str, int], ...]
    missing_status: int


@dataclass(frozen=True)
class ReconciliationProjection:
    health: ReconciliationHealth
    active_terminal_incidents: tuple[str, ...]
    nonterminal_history_incidents: tuple[str, ...]
    missing_history_outcomes: tuple[str, ...]
    duplicate_incident_ids: tuple[str, ...]


_KNOWN_LIFECYCLES = ("OPEN", "INVESTIGATING", "TERMINAL")
_KNOWN_OUTCOMES = (
    "RECOVERED", "UNRESOLVED", "ESCALATED", "INSUFFICIENT_EVIDENCE",
)


def _pairs(counter: Counter[str], keys: Iterable[str] | None = None) -> tuple[tuple[str, int], ...]:
    if keys is None:
        keys = sorted(counter)
    return tuple((key, int(counter.get(key, 0))) for key in keys)


def project_incidents(manager: Any) -> IncidentMetricsProjection:
    """Read IncidentManager-compatible state without mutating it."""
    active = tuple(getattr(manager, "active_incidents", {}).values())
    history = tuple(getattr(manager, "incident_history", ()))

    active_counts = Counter(str(getattr(item, "lifecycle_state", getattr(item, "status", "UNKNOWN"))).upper()
                            for item in active)
    outcome_counts = Counter(str(item.get("final_outcome")).upper()
                             for item in history if item.get("final_outcome") is not None)
    unknown_active = Counter({k: v for k, v in active_counts.items() if k not in _KNOWN_LIFECYCLES})
    unknown_outcomes = Counter({k: v for k, v in outcome_counts.items() if k not in _KNOWN_OUTCOMES})
    terminal_history = sum(1 for item in history
                           if str(item.get("lifecycle_state", item.get("status", ""))).upper() == "TERMINAL")

    return IncidentMetricsProjection(
        active_total=len(active),
        active_lifecycle_counts=_pairs(active_counts, _KNOWN_LIFECYCLES),
        history_terminal_total=terminal_history,
        history_outcome_counts=_pairs(outcome_counts, _KNOWN_OUTCOMES),
        unknown_active_lifecycle_counts=_pairs(unknown_active),
        unknown_history_outcome_counts=_pairs(unknown_outcomes),
    )


def project_remediation(records: Iterable[Mapping[str, Any]]) -> RemediationMetricsProjection:
    """Count explicit caller-supplied status/outcome labels only."""
    materialized = tuple(dict(record) for record in records)
    labels: list[str] = []
    missing = 0
    for record in materialized:
        value = record.get("status", record.get("outcome"))
        if value is None:
            missing += 1
            continue
        labels.append(str(value).upper())
    return RemediationMetricsProjection(
        total=len(materialized),
        status_counts=_pairs(Counter(labels)),
        missing_status=missing,
    )


def reconcile_incidents(manager: Any) -> ReconciliationProjection:
    """Report consistency defects without triggering recovery or mutation."""
    active = tuple(getattr(manager, "active_incidents", {}).values())
    history = tuple(getattr(manager, "incident_history", ()))

    active_terminal = sorted(
        str(getattr(item, "incident_id", "UNKNOWN")) for item in active
        if str(getattr(item, "lifecycle_state", getattr(item, "status", ""))).upper() == "TERMINAL"
    )
    nonterminal_history = sorted(
        str(item.get("incident_id", "UNKNOWN")) for item in history
        if str(item.get("lifecycle_state", item.get("status", ""))).upper() != "TERMINAL"
    )
    missing_outcomes = sorted(
        str(item.get("incident_id", "UNKNOWN")) for item in history
        if item.get("final_outcome") is None
    )
    active_ids = [str(getattr(item, "incident_id", "UNKNOWN")) for item in active]
    history_ids = [str(item.get("incident_id", "UNKNOWN")) for item in history]
    duplicate_ids = sorted(set(active_ids).intersection(history_ids))

    degraded = bool(active_terminal or nonterminal_history or missing_outcomes or duplicate_ids)
    return ReconciliationProjection(
        health=ReconciliationHealth.DEGRADED if degraded else ReconciliationHealth.HEALTHY,
        active_terminal_incidents=tuple(active_terminal),
        nonterminal_history_incidents=tuple(nonterminal_history),
        missing_history_outcomes=tuple(missing_outcomes),
        duplicate_incident_ids=tuple(duplicate_ids),
    )
