"""Passive synthetic recovery-evidence projections with no effect authority."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class RecoveryEvidenceStatus(str, Enum):
    RECOVERED = "RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"
    UNKNOWN = "UNKNOWN"


class RecoveryEvidenceHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RecoveryScenarioProjection:
    scenario_id: str | None
    failure_class: str | None
    injection_scope: str | None
    before_state: str | None
    failure_state: str | None
    after_state: str | None
    expected_recovery_state: str | None
    verification_status: str | None
    status: RecoveryEvidenceStatus
    duplicate_identity: bool
    scope_violation: bool
    effect_attempt_violation: bool


@dataclass(frozen=True)
class RecoveryEvidenceProjection:
    total_records: int
    recovered_count: int
    not_recovered_count: int
    unknown_count: int
    duplicate_scenario_id_count: int
    scope_violation_count: int
    effect_attempt_violation_count: int
    health: RecoveryEvidenceHealth
    scenarios: tuple[RecoveryScenarioProjection, ...]


_ALLOWED_SCOPE = {"SYNTHETIC", "NON_PRODUCTION"}
_ALLOWED_VERIFICATION = {"VERIFIED", "FAILED", "UNKNOWN"}
_ALLOWED_SYMBOL_PUNCTUATION = frozenset("._:-")


def _symbol(record: Mapping[str, Any], field: str, *, max_length: int = 128) -> str | None:
    value = record.get(field)
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_length:
        return None
    if any(not (char.isalnum() or char in _ALLOWED_SYMBOL_PUNCTUATION) for char in value):
        return None
    return value


def _normalized_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": _symbol(record, "scenario_id"),
        "failure_class": _symbol(record, "failure_class"),
        "injection_scope": _symbol(record, "injection_scope"),
        "before_state": _symbol(record, "before_state"),
        "failure_state": _symbol(record, "failure_state"),
        "after_state": _symbol(record, "after_state"),
        "expected_recovery_state": _symbol(record, "expected_recovery_state"),
        "verification_status": _symbol(record, "verification_status"),
        "effect_attempted": record.get("effect_attempted"),
    }


def _classify(
    record: Mapping[str, Any], *, duplicate_identity: bool,
) -> RecoveryScenarioProjection:
    scenario_id = record["scenario_id"]
    failure_class = record["failure_class"]
    injection_scope = record["injection_scope"]
    before_state = record["before_state"]
    failure_state = record["failure_state"]
    after_state = record["after_state"]
    expected_recovery_state = record["expected_recovery_state"]
    verification_status = record["verification_status"]
    effect_attempted = record["effect_attempted"]

    scope_violation = injection_scope is not None and injection_scope not in _ALLOWED_SCOPE
    effect_attempt_violation = effect_attempted is True

    required_symbols = (
        scenario_id,
        failure_class,
        injection_scope,
        before_state,
        failure_state,
        after_state,
        expected_recovery_state,
        verification_status,
    )
    incomplete = any(value is None for value in required_symbols)
    invalid_verification = (
        verification_status is not None and verification_status not in _ALLOWED_VERIFICATION
    )
    ambiguous_effect_fact = not isinstance(effect_attempted, bool)
    failure_not_demonstrated = (
        before_state is not None and failure_state is not None and before_state == failure_state
    )

    if (
        incomplete
        or invalid_verification
        or ambiguous_effect_fact
        or failure_not_demonstrated
        or duplicate_identity
        or scope_violation
        or effect_attempt_violation
        or verification_status == "UNKNOWN"
    ):
        status = RecoveryEvidenceStatus.UNKNOWN
    elif verification_status == "FAILED":
        status = RecoveryEvidenceStatus.NOT_RECOVERED
    elif after_state == expected_recovery_state:
        status = RecoveryEvidenceStatus.RECOVERED
    else:
        status = RecoveryEvidenceStatus.NOT_RECOVERED

    return RecoveryScenarioProjection(
        scenario_id=scenario_id,
        failure_class=failure_class,
        injection_scope=injection_scope,
        before_state=before_state,
        failure_state=failure_state,
        after_state=after_state,
        expected_recovery_state=expected_recovery_state,
        verification_status=verification_status,
        status=status,
        duplicate_identity=duplicate_identity,
        scope_violation=scope_violation,
        effect_attempt_violation=effect_attempt_violation,
    )


def project_recovery_evidence(
    records: Iterable[Mapping[str, Any]],
) -> RecoveryEvidenceProjection:
    """Project detached synthetic recovery facts without causing or recovering faults."""
    normalized = tuple(_normalized_record(record) for record in records)
    id_counts: dict[str, int] = {}
    for record in normalized:
        scenario_id = record["scenario_id"]
        if scenario_id is not None:
            id_counts[scenario_id] = id_counts.get(scenario_id, 0) + 1

    duplicate_ids = {scenario_id for scenario_id, count in id_counts.items() if count > 1}
    scenarios = tuple(
        _classify(
            record,
            duplicate_identity=(record["scenario_id"] in duplicate_ids),
        )
        for record in normalized
    )

    recovered = sum(item.status is RecoveryEvidenceStatus.RECOVERED for item in scenarios)
    not_recovered = sum(item.status is RecoveryEvidenceStatus.NOT_RECOVERED for item in scenarios)
    unknown = sum(item.status is RecoveryEvidenceStatus.UNKNOWN for item in scenarios)
    scope_violations = sum(item.scope_violation for item in scenarios)
    effect_attempt_violations = sum(item.effect_attempt_violation for item in scenarios)

    if not scenarios:
        health = RecoveryEvidenceHealth.UNKNOWN
    elif not_recovered or unknown or duplicate_ids or scope_violations or effect_attempt_violations:
        health = RecoveryEvidenceHealth.DEGRADED
    else:
        health = RecoveryEvidenceHealth.HEALTHY

    return RecoveryEvidenceProjection(
        total_records=len(scenarios),
        recovered_count=recovered,
        not_recovered_count=not_recovered,
        unknown_count=unknown,
        duplicate_scenario_id_count=len(duplicate_ids),
        scope_violation_count=scope_violations,
        effect_attempt_violation_count=effect_attempt_violations,
        health=health,
        scenarios=scenarios,
    )
