"""Bounded passive resource-measurement projection with no SLO authority."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any


MAX_RESOURCE_SAMPLES = 1024
RESOURCE_MEASUREMENT_UNITS = (
    ("observed_at_unix_seconds", "seconds_unix"),
    ("cycle_duration_seconds", "seconds"),
    ("cpu_time_seconds", "seconds"),
    ("rss_bytes", "bytes"),
    ("open_fd_count", "count"),
    ("queue_depth", "count"),
)


class ResourceMeasurementStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class ResourceMeasurementIntegrity(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class ResourceMeasurementTrustStatus(str, Enum):
    TRUSTED = "TRUSTED"
    UNTRUSTED = "UNTRUSTED"
    UNKNOWN = "UNKNOWN"


class ResourceMeasurementStabilityStatus(str, Enum):
    STABLE = "STABLE"
    UNSTABLE = "UNSTABLE"
    UNKNOWN = "UNKNOWN"


class ResourceSloDefinitionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class ResourceSloObjectiveRelation(str, Enum):
    TARGET_AT_OR_BELOW = "TARGET_AT_OR_BELOW"
    TARGET_AT_OR_ABOVE = "TARGET_AT_OR_ABOVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ResourceMeasurementSampleProjection:
    sample_id: str | None
    observed_at_unix_seconds: float | None
    cycle_duration_seconds: float | None
    cpu_time_seconds: float | None
    rss_bytes: int | None
    open_fd_count: int | None
    queue_depth: int | None
    status: ResourceMeasurementStatus
    duplicate_identity: bool


@dataclass(frozen=True)
class ResourceMeasurementProjection:
    processed_records: int
    complete_count: int
    partial_count: int
    invalid_count: int
    unknown_count: int
    duplicate_sample_id_count: int
    input_truncated: bool
    health: ResourceMeasurementIntegrity
    units: tuple[tuple[str, str], ...]
    samples: tuple[ResourceMeasurementSampleProjection, ...]


@dataclass(frozen=True)
class ResourceMeasurementTrustStabilityRecordProjection:
    sample_id: str | None
    source_id: str | None
    observation_window_id: str | None
    observed_at_unix_seconds: float | None
    trust_status: ResourceMeasurementTrustStatus
    stability_status: ResourceMeasurementStabilityStatus
    duplicate_identity: bool
    unknown_record: bool


@dataclass(frozen=True)
class ResourceMeasurementTrustStabilityProjection:
    total_records: int
    trusted_count: int
    untrusted_count: int
    stable_count: int
    unstable_count: int
    unknown_record_count: int
    duplicate_identity_count: int
    health: ResourceMeasurementIntegrity
    records: tuple[ResourceMeasurementTrustStabilityRecordProjection, ...]


@dataclass(frozen=True)
class ResourceSloDefinitionRecordProjection:
    slo_id: str | None
    metric_name: str | None
    objective_relation: ResourceSloObjectiveRelation
    objective_value: float | int | None
    objective_unit: str | None
    observation_window_id: str | None
    effective_scope_id: str | None
    status: ResourceSloDefinitionStatus
    duplicate_identity: bool


@dataclass(frozen=True)
class ResourceSloDefinitionProjection:
    total_records: int
    complete_count: int
    invalid_count: int
    unknown_count: int
    duplicate_slo_id_count: int
    health: ResourceMeasurementIntegrity
    records: tuple[ResourceSloDefinitionRecordProjection, ...]


_SYMBOL_PUNCTUATION = frozenset("._:-")
_FLOAT_FIELDS = ("cycle_duration_seconds", "cpu_time_seconds")
_INT_FIELDS = ("rss_bytes", "open_fd_count", "queue_depth")
_RESOURCE_METRIC_UNITS = dict(RESOURCE_MEASUREMENT_UNITS)
_SLO_METRIC_NAMES = frozenset(_FLOAT_FIELDS + _INT_FIELDS)
_SLO_OBJECTIVE_RELATIONS = frozenset(
    relation.value
    for relation in ResourceSloObjectiveRelation
    if relation is not ResourceSloObjectiveRelation.UNKNOWN
)


def _symbol(record: Mapping[str, Any], field: str) -> tuple[str | None, bool, bool]:
    if field not in record:
        return None, False, False
    value = record.get(field)
    if not isinstance(value, str):
        return None, True, True
    value = value.strip()
    invalid = (
        not value
        or len(value) > 128
        or any(not (char.isalnum() or char in _SYMBOL_PUNCTUATION) for char in value)
    )
    return (None if invalid else value), True, invalid


def _number(record: Mapping[str, Any], field: str) -> tuple[float | None, bool, bool]:
    if field not in record:
        return None, False, False
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, True, True
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        return None, True, True
    return normalized, True, False


def _integer(record: Mapping[str, Any], field: str) -> tuple[int | None, bool, bool]:
    if field not in record:
        return None, False, False
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None, True, True
    return value, True, False


def _normalize(record: object) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        return {"record_invalid": True}

    sample_id, sample_id_present, sample_id_invalid = _symbol(record, "sample_id")
    observed_at, observed_present, observed_invalid = _number(
        record, "observed_at_unix_seconds"
    )
    normalized: dict[str, Any] = {
        "record_invalid": False,
        "sample_id": sample_id,
        "sample_id_present": sample_id_present,
        "sample_id_invalid": sample_id_invalid,
        "observed_at_unix_seconds": observed_at,
        "observed_present": observed_present,
        "observed_invalid": observed_invalid,
    }
    for field in _FLOAT_FIELDS:
        value, present, invalid = _number(record, field)
        normalized[field] = value
        normalized[f"{field}_present"] = present
        normalized[f"{field}_invalid"] = invalid
    for field in _INT_FIELDS:
        value, present, invalid = _integer(record, field)
        normalized[field] = value
        normalized[f"{field}_present"] = present
        normalized[f"{field}_invalid"] = invalid
    return normalized


def _classify(record: Mapping[str, Any], *, duplicate_identity: bool) -> ResourceMeasurementSampleProjection:
    if record.get("record_invalid") is True:
        return ResourceMeasurementSampleProjection(
            None, None, None, None, None, None, None,
            ResourceMeasurementStatus.INVALID, False,
        )

    metric_fields = _FLOAT_FIELDS + _INT_FIELDS
    invalid = (
        bool(record["sample_id_invalid"])
        or bool(record["observed_invalid"])
        or any(bool(record[f"{field}_invalid"]) for field in metric_fields)
        or duplicate_identity
    )
    missing_identity = not bool(record["sample_id_present"])
    missing_observation = not bool(record["observed_present"])
    valid_metrics = sum(record[field] is not None for field in metric_fields)
    missing_metrics = sum(not bool(record[f"{field}_present"]) for field in metric_fields)

    if invalid:
        status = ResourceMeasurementStatus.INVALID
    elif missing_identity or missing_observation or valid_metrics == 0:
        status = ResourceMeasurementStatus.UNKNOWN
    elif missing_metrics:
        status = ResourceMeasurementStatus.PARTIAL
    else:
        status = ResourceMeasurementStatus.COMPLETE

    return ResourceMeasurementSampleProjection(
        sample_id=record["sample_id"],
        observed_at_unix_seconds=record["observed_at_unix_seconds"],
        cycle_duration_seconds=record["cycle_duration_seconds"],
        cpu_time_seconds=record["cpu_time_seconds"],
        rss_bytes=record["rss_bytes"],
        open_fd_count=record["open_fd_count"],
        queue_depth=record["queue_depth"],
        status=status,
        duplicate_identity=duplicate_identity,
    )


def project_resource_measurements(
    records: Iterable[Mapping[str, Any]],
) -> ResourceMeasurementProjection:
    """Validate detached resource samples without acquiring or enforcing metrics."""
    normalized: list[dict[str, Any]] = []
    input_truncated = False
    for index, record in enumerate(records):
        if index >= MAX_RESOURCE_SAMPLES:
            input_truncated = True
            break
        normalized.append(_normalize(record))

    id_counts: dict[str, int] = {}
    for record in normalized:
        sample_id = record.get("sample_id")
        if isinstance(sample_id, str):
            id_counts[sample_id] = id_counts.get(sample_id, 0) + 1
    duplicate_ids = {key for key, count in id_counts.items() if count > 1}

    samples = tuple(
        _classify(
            record,
            duplicate_identity=(record.get("sample_id") in duplicate_ids),
        )
        for record in normalized
    )
    complete = sum(item.status is ResourceMeasurementStatus.COMPLETE for item in samples)
    partial = sum(item.status is ResourceMeasurementStatus.PARTIAL for item in samples)
    invalid = sum(item.status is ResourceMeasurementStatus.INVALID for item in samples)
    unknown = sum(item.status is ResourceMeasurementStatus.UNKNOWN for item in samples)

    if not samples:
        health = ResourceMeasurementIntegrity.UNKNOWN
    elif partial or invalid or unknown or duplicate_ids or input_truncated:
        health = ResourceMeasurementIntegrity.DEGRADED
    else:
        health = ResourceMeasurementIntegrity.HEALTHY

    return ResourceMeasurementProjection(
        processed_records=len(samples),
        complete_count=complete,
        partial_count=partial,
        invalid_count=invalid,
        unknown_count=unknown,
        duplicate_sample_id_count=len(duplicate_ids),
        input_truncated=input_truncated,
        health=health,
        units=RESOURCE_MEASUREMENT_UNITS,
        samples=samples,
    )


def _enum_value(
    record: Mapping[str, Any],
    field: str,
    allowed: set[str],
) -> tuple[str | None, bool]:
    value = record.get(field)
    if isinstance(value, str) and value in allowed:
        return value, False
    return None, True


def project_resource_measurement_trust_stability(
    records: Iterable[Mapping[str, Any]],
) -> ResourceMeasurementTrustStabilityProjection:
    """Project detached measurement trust/stability facts without SLO authority."""
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            normalized.append({"record_invalid": True})
            continue

        sample_id, sample_present, sample_invalid = _symbol(record, "sample_id")
        source_id, source_present, source_invalid = _symbol(record, "source_id")
        window_id, window_present, window_invalid = _symbol(
            record, "observation_window_id"
        )
        observed_at, observed_present, observed_invalid = _number(
            record, "observed_at_unix_seconds"
        )
        trust_status, trust_unknown = _enum_value(
            record,
            "trust_status",
            {"TRUSTED", "UNTRUSTED", "UNKNOWN"},
        )
        stability_status, stability_unknown = _enum_value(
            record,
            "stability_status",
            {"STABLE", "UNSTABLE", "UNKNOWN"},
        )

        normalized.append({
            "record_invalid": False,
            "sample_id": sample_id,
            "sample_present": sample_present,
            "sample_invalid": sample_invalid,
            "source_id": source_id,
            "source_present": source_present,
            "source_invalid": source_invalid,
            "observation_window_id": window_id,
            "window_present": window_present,
            "window_invalid": window_invalid,
            "observed_at_unix_seconds": observed_at,
            "observed_present": observed_present,
            "observed_invalid": observed_invalid,
            "trust_status": trust_status,
            "trust_unknown": trust_unknown,
            "stability_status": stability_status,
            "stability_unknown": stability_unknown,
        })

    identity_counts: dict[tuple[str, str, str], int] = {}
    for record in normalized:
        identity = (
            record.get("sample_id"),
            record.get("source_id"),
            record.get("observation_window_id"),
        )
        if all(isinstance(part, str) for part in identity):
            identity_counts[identity] = identity_counts.get(identity, 0) + 1
    duplicate_identities = {
        identity for identity, count in identity_counts.items() if count > 1
    }

    projected_records: list[ResourceMeasurementTrustStabilityRecordProjection] = []
    for record in normalized:
        if record.get("record_invalid") is True:
            projected_records.append(
                ResourceMeasurementTrustStabilityRecordProjection(
                    sample_id=None,
                    source_id=None,
                    observation_window_id=None,
                    observed_at_unix_seconds=None,
                    trust_status=ResourceMeasurementTrustStatus.UNKNOWN,
                    stability_status=ResourceMeasurementStabilityStatus.UNKNOWN,
                    duplicate_identity=False,
                    unknown_record=True,
                )
            )
            continue

        identity = (
            record.get("sample_id"),
            record.get("source_id"),
            record.get("observation_window_id"),
        )
        duplicate_identity = identity in duplicate_identities
        trust = record["trust_status"] or "UNKNOWN"
        stability = record["stability_status"] or "UNKNOWN"
        unknown_record = (
            duplicate_identity
            or bool(record["sample_invalid"])
            or bool(record["source_invalid"])
            or bool(record["window_invalid"])
            or bool(record["observed_invalid"])
            or not bool(record["sample_present"])
            or not bool(record["source_present"])
            or not bool(record["window_present"])
            or not bool(record["observed_present"])
            or bool(record["trust_unknown"])
            or bool(record["stability_unknown"])
            or trust == "UNKNOWN"
            or stability == "UNKNOWN"
        )
        projected_records.append(
            ResourceMeasurementTrustStabilityRecordProjection(
                sample_id=record["sample_id"],
                source_id=record["source_id"],
                observation_window_id=record["observation_window_id"],
                observed_at_unix_seconds=record["observed_at_unix_seconds"],
                trust_status=ResourceMeasurementTrustStatus(trust),
                stability_status=ResourceMeasurementStabilityStatus(stability),
                duplicate_identity=duplicate_identity,
                unknown_record=unknown_record,
            )
        )

    projections = tuple(projected_records)
    trusted = sum(
        item.trust_status is ResourceMeasurementTrustStatus.TRUSTED
        for item in projections
    )
    untrusted = sum(
        item.trust_status is ResourceMeasurementTrustStatus.UNTRUSTED
        for item in projections
    )
    stable = sum(
        item.stability_status is ResourceMeasurementStabilityStatus.STABLE
        for item in projections
    )
    unstable = sum(
        item.stability_status is ResourceMeasurementStabilityStatus.UNSTABLE
        for item in projections
    )
    unknown = sum(item.unknown_record for item in projections)
    duplicates = len(duplicate_identities)

    if not projections:
        health = ResourceMeasurementIntegrity.UNKNOWN
    elif untrusted or unstable or unknown or duplicates:
        health = ResourceMeasurementIntegrity.DEGRADED
    else:
        health = ResourceMeasurementIntegrity.HEALTHY

    return ResourceMeasurementTrustStabilityProjection(
        total_records=len(projections),
        trusted_count=trusted,
        untrusted_count=untrusted,
        stable_count=stable,
        unstable_count=unstable,
        unknown_record_count=unknown,
        duplicate_identity_count=duplicates,
        health=health,
        records=projections,
    )


def project_resource_slo_definitions(
    records: Iterable[Mapping[str, Any]],
) -> ResourceSloDefinitionProjection:
    """Project detached non-enforcing SLO definitions without evaluating samples."""
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            normalized.append({"record_invalid": True})
            continue

        slo_id, slo_present, slo_invalid = _symbol(record, "slo_id")
        window_id, window_present, window_invalid = _symbol(
            record, "observation_window_id"
        )
        scope_id, scope_present, scope_invalid = _symbol(record, "effective_scope_id")
        metric_name, metric_present, metric_invalid = _symbol(record, "metric_name")
        relation, relation_unknown = _enum_value(
            record,
            "objective_relation",
            set(_SLO_OBJECTIVE_RELATIONS),
        )
        relation_present = "objective_relation" in record

        objective_value: float | int | None
        objective_present = "objective_value" in record
        objective_invalid = False
        objective_value = None
        if objective_present:
            if metric_name in _INT_FIELDS:
                integer_value, _, integer_invalid = _integer(record, "objective_value")
                objective_value = integer_value
                objective_invalid = integer_invalid
            else:
                numeric_value, _, numeric_invalid = _number(record, "objective_value")
                objective_value = numeric_value
                objective_invalid = numeric_invalid

        expected_unit = _RESOURCE_METRIC_UNITS.get(metric_name or "")
        objective_unit, unit_present, unit_invalid = _symbol(record, "objective_unit")
        if objective_unit is not None and expected_unit is not None:
            unit_invalid = objective_unit != expected_unit

        normalized.append({
            "record_invalid": False,
            "slo_id": slo_id,
            "slo_present": slo_present,
            "slo_invalid": slo_invalid,
            "metric_name": metric_name,
            "metric_present": metric_present,
            "metric_invalid": metric_invalid or metric_name not in _SLO_METRIC_NAMES,
            "objective_relation": relation,
            "relation_present": relation_present,
            "relation_unknown": relation_unknown,
            "objective_value": objective_value,
            "objective_present": objective_present,
            "objective_invalid": objective_invalid,
            "objective_unit": objective_unit,
            "unit_present": unit_present,
            "unit_invalid": unit_invalid,
            "observation_window_id": window_id,
            "window_present": window_present,
            "window_invalid": window_invalid,
            "effective_scope_id": scope_id,
            "scope_present": scope_present,
            "scope_invalid": scope_invalid,
        })

    identity_counts: dict[str, int] = {}
    for record in normalized:
        slo_id = record.get("slo_id")
        if isinstance(slo_id, str):
            identity_counts[slo_id] = identity_counts.get(slo_id, 0) + 1
    duplicate_ids = {key for key, count in identity_counts.items() if count > 1}

    projected_records: list[ResourceSloDefinitionRecordProjection] = []
    for record in normalized:
        if record.get("record_invalid") is True:
            projected_records.append(
                ResourceSloDefinitionRecordProjection(
                    slo_id=None,
                    metric_name=None,
                    objective_relation=ResourceSloObjectiveRelation.UNKNOWN,
                    objective_value=None,
                    objective_unit=None,
                    observation_window_id=None,
                    effective_scope_id=None,
                    status=ResourceSloDefinitionStatus.INVALID,
                    duplicate_identity=False,
                )
            )
            continue

        duplicate_identity = record.get("slo_id") in duplicate_ids
        invalid = (
            duplicate_identity
            or bool(record["slo_invalid"])
            or bool(record["metric_invalid"])
            or (bool(record["relation_unknown"]) and bool(record["relation_present"]))
            or bool(record["objective_invalid"])
            or bool(record["unit_invalid"])
            or bool(record["window_invalid"])
            or bool(record["scope_invalid"])
        )
        unknown = (
            not bool(record["slo_present"])
            or not bool(record["metric_present"])
            or not bool(record["relation_present"])
            or not bool(record["objective_present"])
            or not bool(record["unit_present"])
            or not bool(record["window_present"])
            or not bool(record["scope_present"])
        )
        if invalid:
            status = ResourceSloDefinitionStatus.INVALID
        elif unknown:
            status = ResourceSloDefinitionStatus.UNKNOWN
        else:
            status = ResourceSloDefinitionStatus.COMPLETE

        projected_records.append(
            ResourceSloDefinitionRecordProjection(
                slo_id=record["slo_id"],
                metric_name=record["metric_name"],
                objective_relation=ResourceSloObjectiveRelation(
                    record["objective_relation"] or "UNKNOWN"
                ),
                objective_value=record["objective_value"],
                objective_unit=record["objective_unit"],
                observation_window_id=record["observation_window_id"],
                effective_scope_id=record["effective_scope_id"],
                status=status,
                duplicate_identity=duplicate_identity,
            )
        )

    projections = tuple(projected_records)
    complete = sum(
        item.status is ResourceSloDefinitionStatus.COMPLETE for item in projections
    )
    invalid = sum(
        item.status is ResourceSloDefinitionStatus.INVALID for item in projections
    )
    unknown = sum(
        item.status is ResourceSloDefinitionStatus.UNKNOWN for item in projections
    )

    if not projections:
        health = ResourceMeasurementIntegrity.UNKNOWN
    elif invalid or unknown or duplicate_ids:
        health = ResourceMeasurementIntegrity.DEGRADED
    else:
        health = ResourceMeasurementIntegrity.HEALTHY

    return ResourceSloDefinitionProjection(
        total_records=len(projections),
        complete_count=complete,
        invalid_count=invalid,
        unknown_count=unknown,
        duplicate_slo_id_count=len(duplicate_ids),
        health=health,
        records=projections,
    )
