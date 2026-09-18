import ast
from dataclasses import FrozenInstanceError

import pytest

from sentinel.worker.resource_measurements import (
    MAX_RESOURCE_SAMPLES,
    RESOURCE_MEASUREMENT_UNITS,
    ResourceMeasurementIntegrity,
    ResourceMeasurementProjection,
    ResourceMeasurementStabilityStatus,
    ResourceMeasurementStatus,
    ResourceMeasurementTrustStatus,
    ResourceMeasurementTrustStabilityProjection,
    ResourceMeasurementTrustStabilityRecordProjection,
    ResourceSloDefinitionProjection,
    ResourceSloDefinitionRecordProjection,
    ResourceSloDefinitionStatus,
    ResourceSloObjectiveRelation,
    project_resource_measurement_trust_stability,
    project_resource_measurements,
    project_resource_slo_definitions,
)


def _sample(**overrides):
    record = {
        "sample_id": "SAMPLE-1",
        "observed_at_unix_seconds": 1_800_000_000.0,
        "cycle_duration_seconds": 0.25,
        "cpu_time_seconds": 12.5,
        "rss_bytes": 64_000_000,
        "open_fd_count": 18,
        "queue_depth": 0,
    }
    record.update(overrides)
    return record


def test_complete_sample_preserves_explicit_units_and_zero_values():
    projection = project_resource_measurements([_sample()])

    assert projection.processed_records == 1
    assert projection.complete_count == 1
    assert projection.partial_count == 0
    assert projection.invalid_count == 0
    assert projection.unknown_count == 0
    assert projection.health is ResourceMeasurementIntegrity.HEALTHY
    assert projection.units == RESOURCE_MEASUREMENT_UNITS
    assert projection.samples[0].queue_depth == 0
    assert projection.samples[0].status is ResourceMeasurementStatus.COMPLETE


def test_missing_one_metric_is_partial_not_synthetic_complete():
    record = _sample()
    del record["open_fd_count"]
    projection = project_resource_measurements([record])

    assert projection.partial_count == 1
    assert projection.complete_count == 0
    assert projection.samples[0].status is ResourceMeasurementStatus.PARTIAL
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_missing_identity_is_unknown():
    record = _sample()
    del record["sample_id"]
    projection = project_resource_measurements([record])

    assert projection.unknown_count == 1
    assert projection.samples[0].status is ResourceMeasurementStatus.UNKNOWN


def test_missing_observation_timestamp_is_unknown():
    record = _sample()
    del record["observed_at_unix_seconds"]
    projection = project_resource_measurements([record])

    assert projection.unknown_count == 1
    assert projection.samples[0].status is ResourceMeasurementStatus.UNKNOWN


def test_no_resource_metrics_is_unknown():
    projection = project_resource_measurements([{
        "sample_id": "SAMPLE-1",
        "observed_at_unix_seconds": 1_800_000_000.0,
    }])

    assert projection.unknown_count == 1
    assert projection.samples[0].status is ResourceMeasurementStatus.UNKNOWN


@pytest.mark.parametrize("field", ["cycle_duration_seconds", "cpu_time_seconds"])
def test_negative_float_measurement_is_invalid(field):
    projection = project_resource_measurements([_sample(**{field: -0.01})])

    assert projection.invalid_count == 1
    assert projection.samples[0].status is ResourceMeasurementStatus.INVALID
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_float_measurement_is_invalid(value):
    projection = project_resource_measurements([_sample(cpu_time_seconds=value)])
    assert projection.invalid_count == 1


@pytest.mark.parametrize("field", ["rss_bytes", "open_fd_count", "queue_depth"])
def test_negative_integer_measurement_is_invalid(field):
    projection = project_resource_measurements([_sample(**{field: -1})])
    assert projection.invalid_count == 1


@pytest.mark.parametrize(
    "field",
    [
        "observed_at_unix_seconds",
        "cycle_duration_seconds",
        "cpu_time_seconds",
        "rss_bytes",
        "open_fd_count",
        "queue_depth",
    ],
)
def test_boolean_is_not_accepted_as_numeric_measurement(field):
    projection = project_resource_measurements([_sample(**{field: True})])
    assert projection.invalid_count == 1


def test_malformed_identity_is_invalid():
    projection = project_resource_measurements([_sample(sample_id="raw identity with spaces")])
    assert projection.invalid_count == 1
    assert projection.samples[0].sample_id is None


def test_duplicate_sample_identity_invalidates_all_affected_samples():
    projection = project_resource_measurements([
        _sample(),
        _sample(cpu_time_seconds=13.0),
    ])

    assert projection.duplicate_sample_id_count == 1
    assert projection.invalid_count == 2
    assert all(item.duplicate_identity for item in projection.samples)
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_non_mapping_record_is_invalid_without_exception():
    projection = project_resource_measurements([None])
    assert projection.invalid_count == 1
    assert projection.samples[0].status is ResourceMeasurementStatus.INVALID


def test_projection_is_bounded_to_1024_processed_samples():
    records = (
        _sample(sample_id=f"SAMPLE-{index}")
        for index in range(MAX_RESOURCE_SAMPLES + 1)
    )
    projection = project_resource_measurements(records)

    assert projection.processed_records == MAX_RESOURCE_SAMPLES
    assert projection.complete_count == MAX_RESOURCE_SAMPLES
    assert projection.input_truncated is True
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_empty_input_is_unknown_not_healthy():
    projection = project_resource_measurements([])

    assert projection == ResourceMeasurementProjection(
        processed_records=0,
        complete_count=0,
        partial_count=0,
        invalid_count=0,
        unknown_count=0,
        duplicate_sample_id_count=0,
        input_truncated=False,
        health=ResourceMeasurementIntegrity.UNKNOWN,
        units=RESOURCE_MEASUREMENT_UNITS,
        samples=(),
    )


def test_projection_preserves_order_is_deterministic_and_immutable():
    records = (
        _sample(sample_id="SAMPLE-2"),
        _sample(sample_id="SAMPLE-1", queue_depth=2),
    )
    projection = project_resource_measurements(records)

    assert projection == project_resource_measurements(records)
    assert tuple(item.sample_id for item in projection.samples) == ("SAMPLE-2", "SAMPLE-1")
    with pytest.raises(FrozenInstanceError):
        projection.complete_count = 99
    with pytest.raises(FrozenInstanceError):
        projection.samples[0].status = ResourceMeasurementStatus.INVALID


def test_module_has_no_metric_acquisition_effect_or_slo_enforcement_dependency():
    from sentinel.worker import resource_measurements

    tree = ast.parse(open(resource_measurements.__file__, encoding="utf-8").read())
    imported = set()
    function_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert imported <= {"collections", "dataclasses", "enum", "math", "typing"}
    assert not imported.intersection({"os", "pathlib", "subprocess", "socket", "psutil"})
    assert not any(
        name.startswith(("poll", "acquire", "enforce", "execute", "restart", "remediate", "rollback"))
        for name in function_names
    )


def test_projection_contains_no_threshold_or_authorization_fields():
    fields = set(ResourceMeasurementProjection.__dataclass_fields__)
    assert not any("threshold" in field or "authorized" in field for field in fields)


def test_measurement_statuses_cannot_be_used_as_boolean_authority():
    assert ResourceMeasurementIntegrity.HEALTHY != True
    assert ResourceMeasurementIntegrity.DEGRADED != False
    assert ResourceMeasurementStatus.COMPLETE != True
    assert ResourceMeasurementStatus.INVALID != False


def _trust_record(**overrides):
    record = {
        "sample_id": "SAMPLE-1",
        "source_id": "runtime-worker",
        "observation_window_id": "WINDOW-1",
        "observed_at_unix_seconds": 1_800_000_000.0,
        "trust_status": "TRUSTED",
        "stability_status": "STABLE",
    }
    record.update(overrides)
    return record


def test_measurement_trust_stability_healthy_for_explicit_trusted_stable_facts():
    projection = project_resource_measurement_trust_stability([_trust_record()])

    assert projection == ResourceMeasurementTrustStabilityProjection(
        total_records=1,
        trusted_count=1,
        untrusted_count=0,
        stable_count=1,
        unstable_count=0,
        unknown_record_count=0,
        duplicate_identity_count=0,
        health=ResourceMeasurementIntegrity.HEALTHY,
        records=(
            ResourceMeasurementTrustStabilityRecordProjection(
                sample_id="SAMPLE-1",
                source_id="runtime-worker",
                observation_window_id="WINDOW-1",
                observed_at_unix_seconds=1_800_000_000.0,
                trust_status=ResourceMeasurementTrustStatus.TRUSTED,
                stability_status=ResourceMeasurementStabilityStatus.STABLE,
                duplicate_identity=False,
                unknown_record=False,
            ),
        ),
    )


def test_measurement_trust_stability_preserves_untrusted_unstable_and_unknown():
    projection = project_resource_measurement_trust_stability([
        _trust_record(sample_id="SAMPLE-1", trust_status="UNTRUSTED"),
        _trust_record(sample_id="SAMPLE-2", stability_status="UNSTABLE"),
        _trust_record(sample_id="SAMPLE-3", trust_status="UNKNOWN"),
        _trust_record(sample_id="SAMPLE-4", stability_status="UNKNOWN"),
    ])

    assert projection.total_records == 4
    assert projection.trusted_count == 2
    assert projection.untrusted_count == 1
    assert projection.stable_count == 2
    assert projection.unstable_count == 1
    assert projection.unknown_record_count == 2
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_measurement_trust_stability_missing_or_malformed_identity_is_unknown():
    projection = project_resource_measurement_trust_stability([
        _trust_record(source_id=""),
        _trust_record(sample_id="raw sample with spaces"),
        None,
    ])

    assert projection.total_records == 3
    assert projection.unknown_record_count == 3
    assert projection.records[0].source_id is None
    assert projection.records[1].sample_id is None
    assert projection.records[2].trust_status is ResourceMeasurementTrustStatus.UNKNOWN
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_measurement_trust_stability_duplicate_identity_is_degraded():
    projection = project_resource_measurement_trust_stability([
        _trust_record(),
        _trust_record(observed_at_unix_seconds=1_800_000_001.0),
    ])

    assert projection.duplicate_identity_count == 1
    assert projection.unknown_record_count == 2
    assert all(item.duplicate_identity for item in projection.records)
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_measurement_trust_stability_empty_input_is_unknown():
    projection = project_resource_measurement_trust_stability([])

    assert projection == ResourceMeasurementTrustStabilityProjection(
        total_records=0,
        trusted_count=0,
        untrusted_count=0,
        stable_count=0,
        unstable_count=0,
        unknown_record_count=0,
        duplicate_identity_count=0,
        health=ResourceMeasurementIntegrity.UNKNOWN,
        records=(),
    )


def test_measurement_trust_stability_contains_no_threshold_or_authority_fields():
    fields = set(ResourceMeasurementTrustStabilityProjection.__dataclass_fields__)
    record_fields = set(
        ResourceMeasurementTrustStabilityRecordProjection.__dataclass_fields__
    )

    assert not any("threshold" in field or "authorized" in field for field in fields)
    assert not any(
        "threshold" in field or "authorized" in field for field in record_fields
    )


def _slo_definition(**overrides):
    record = {
        "slo_id": "SLO-RSS-1",
        "metric_name": "rss_bytes",
        "objective_relation": "TARGET_AT_OR_BELOW",
        "objective_value": 512_000_000,
        "objective_unit": "bytes",
        "observation_window_id": "WINDOW-1",
        "effective_scope_id": "sentinel-worker",
    }
    record.update(overrides)
    return record


def test_non_enforcing_slo_definition_complete_for_detached_target_record():
    projection = project_resource_slo_definitions([_slo_definition()])

    assert projection == ResourceSloDefinitionProjection(
        total_records=1,
        complete_count=1,
        invalid_count=0,
        unknown_count=0,
        duplicate_slo_id_count=0,
        health=ResourceMeasurementIntegrity.HEALTHY,
        records=(
            ResourceSloDefinitionRecordProjection(
                slo_id="SLO-RSS-1",
                metric_name="rss_bytes",
                objective_relation=ResourceSloObjectiveRelation.TARGET_AT_OR_BELOW,
                objective_value=512_000_000,
                objective_unit="bytes",
                observation_window_id="WINDOW-1",
                effective_scope_id="sentinel-worker",
                status=ResourceSloDefinitionStatus.COMPLETE,
                duplicate_identity=False,
            ),
        ),
    )


def test_non_enforcing_slo_definition_accepts_matching_float_metric_unit():
    projection = project_resource_slo_definitions([
        _slo_definition(
            slo_id="SLO-CYCLE-1",
            metric_name="cycle_duration_seconds",
            objective_value=1.5,
            objective_unit="seconds",
        )
    ])

    assert projection.complete_count == 1
    assert projection.records[0].objective_value == 1.5
    assert projection.records[0].objective_unit == "seconds"


def test_non_enforcing_slo_definition_missing_required_fact_is_unknown():
    record = _slo_definition()
    del record["effective_scope_id"]
    projection = project_resource_slo_definitions([record])

    assert projection.unknown_count == 1
    assert projection.records[0].status is ResourceSloDefinitionStatus.UNKNOWN
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slo_id", "raw id with spaces"),
        ("metric_name", "observed_at_unix_seconds"),
        ("objective_relation", "ENFORCE_AT_OR_BELOW"),
        ("objective_value", -1),
        ("objective_value", True),
        ("objective_unit", "megabytes"),
        ("observation_window_id", ""),
        ("effective_scope_id", "scope with spaces"),
    ],
)
def test_non_enforcing_slo_definition_malformed_fact_is_invalid(field, value):
    projection = project_resource_slo_definitions([_slo_definition(**{field: value})])

    assert projection.invalid_count == 1
    assert projection.records[0].status is ResourceSloDefinitionStatus.INVALID
    assert projection.health is ResourceMeasurementIntegrity.DEGRADED


def test_non_enforcing_slo_definition_rejects_duplicate_identity():
    projection = project_resource_slo_definitions([
        _slo_definition(),
        _slo_definition(metric_name="open_fd_count", objective_unit="count"),
    ])

    assert projection.duplicate_slo_id_count == 1
    assert projection.invalid_count == 2
    assert all(item.duplicate_identity for item in projection.records)


def test_non_enforcing_slo_definition_empty_input_is_unknown():
    projection = project_resource_slo_definitions([])

    assert projection == ResourceSloDefinitionProjection(
        total_records=0,
        complete_count=0,
        invalid_count=0,
        unknown_count=0,
        duplicate_slo_id_count=0,
        health=ResourceMeasurementIntegrity.UNKNOWN,
        records=(),
    )


def test_non_enforcing_slo_definition_contains_no_evaluation_or_authority_fields():
    fields = set(ResourceSloDefinitionProjection.__dataclass_fields__)
    record_fields = set(ResourceSloDefinitionRecordProjection.__dataclass_fields__)
    forbidden_terms = (
        "actual",
        "alert",
        "authorized",
        "breach",
        "current",
        "enforce",
        "remediate",
        "restart",
        "rollback",
        "threshold",
    )

    assert not any(term in field for field in fields for term in forbidden_terms)
    assert not any(term in field for field in record_fields for term in forbidden_terms)
