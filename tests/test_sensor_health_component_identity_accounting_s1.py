"""Lane 1 tests for deterministic component-identity health accounting."""

from sentinel.runtime_sensor_adapter import RuntimeSensorAdapter


def test_component_identity_counts_observations_not_distinct_ids():
    projections = [
        {
            "component_id": "%1",
            "agent_identity": "UNKNOWN",
            "sensor_facts": {},
        },
        {
            "component_id": "%1",
            "agent_identity": "UNKNOWN",
            "sensor_facts": {},
        },
        {
            "component_id": None,
            "agent_identity": "UNKNOWN",
            "sensor_facts": {},
        },
    ]

    health = RuntimeSensorAdapter.project_sensor_health(projections)

    assert health["observation_count"] == 3
    assert health["distinct_component_count"] == 1
    assert health["component_identity"] == {
        "present": 2,
        "unknown": 1,
    }
    assert (
        health["component_identity"]["present"]
        + health["component_identity"]["unknown"]
        == health["observation_count"]
    )


def test_component_identity_accounting_keeps_distinctness_separate():
    projections = [
        {"component_id": "%1", "sensor_facts": {}},
        {"component_id": "%2", "sensor_facts": {}},
        {"component_id": "%2", "sensor_facts": {}},
        {"component_id": "", "sensor_facts": {}},
        {"component_id": 7, "sensor_facts": {}},
    ]

    health = RuntimeSensorAdapter.project_sensor_health(projections)

    assert health["observation_count"] == 5
    assert health["distinct_component_count"] == 2
    assert health["component_identity"] == {
        "present": 3,
        "unknown": 2,
    }
    assert (
        health["component_identity"]["present"]
        + health["component_identity"]["unknown"]
        == health["observation_count"]
    )
