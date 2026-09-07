from types import SimpleNamespace

import pytest

from sentinel.remediation_action_catalog import (
    RemediationActionCatalog,
    RemediationActionEntry,
    RemediationActionSelector,
)


def make_entry(
    action="restart_test",
    command="printf 'restart'",
):
    return RemediationActionEntry(
        action=action,
        command=command,
        rationale="registered remediation action",
    )


def make_incident(
    incident_id="incident-001",
    anomaly_type="TEST_ANOMALY",
):
    return SimpleNamespace(
        incident_id=incident_id,
        anomaly_type=anomaly_type,
    )


def make_diagnosis(status="ESTABLISHED"):
    return SimpleNamespace(
        status=SimpleNamespace(value=status),
    )


def test_catalog_registers_and_retrieves_action():
    catalog = RemediationActionCatalog()

    entry = make_entry()

    catalog.register(
        entry,
        trigger="TEST_ANOMALY",
    )

    assert catalog.get("restart_test") is entry
    assert catalog.select_for_trigger("TEST_ANOMALY") is entry
    assert catalog.list_actions() == ("restart_test",)
    assert catalog.list_triggers() == ("TEST_ANOMALY",)


def test_duplicate_action_registration_is_rejected():
    catalog = RemediationActionCatalog()

    catalog.register(make_entry())

    with pytest.raises(ValueError, match="already registered"):
        catalog.register(make_entry())


def test_duplicate_trigger_registration_is_rejected():
    catalog = RemediationActionCatalog()

    catalog.register(
        make_entry("restart_test"),
        trigger="TEST_ANOMALY",
    )

    with pytest.raises(ValueError, match="already registered"):
        catalog.register(
            make_entry("restart_other"),
            trigger="TEST_ANOMALY",
        )


def test_unknown_trigger_is_rejected():
    catalog = RemediationActionCatalog()

    catalog.register(
        make_entry(),
        trigger="TEST_ANOMALY",
    )

    with pytest.raises(KeyError, match="no remediation action"):
        catalog.select_for_trigger("UNKNOWN_ANOMALY")


def test_selector_uses_only_registered_catalog():
    catalog = RemediationActionCatalog()

    catalog.register(
        make_entry(
            action="restart_test",
            command="printf 'registered-command'",
        ),
        trigger="TEST_ANOMALY",
    )

    selector = RemediationActionSelector(catalog)

    entry = selector.select(
        incident=make_incident(),
        diagnosis=make_diagnosis(),
    )

    assert entry.action == "restart_test"
    assert entry.command == "printf 'registered-command'"


def test_selector_rejects_non_established_diagnosis():
    catalog = RemediationActionCatalog()

    catalog.register(
        make_entry(),
        trigger="TEST_ANOMALY",
    )

    selector = RemediationActionSelector(catalog)

    with pytest.raises(ValueError, match="ESTABLISHED"):
        selector.select(
            incident=make_incident(),
            diagnosis=make_diagnosis("INSUFFICIENT_EVIDENCE"),
        )


def test_selector_rejects_incident_without_anomaly_type():
    catalog = RemediationActionCatalog()

    catalog.register(
        make_entry(),
        trigger="TEST_ANOMALY",
    )

    selector = RemediationActionSelector(catalog)

    incident = SimpleNamespace(
        incident_id="incident-001",
        anomaly_type=None,
    )

    with pytest.raises(ValueError, match="anomaly_type"):
        selector.select(
            incident=incident,
            diagnosis=make_diagnosis(),
        )


def test_selector_cannot_invent_unregistered_action():
    catalog = RemediationActionCatalog()

    selector = RemediationActionSelector(catalog)

    with pytest.raises(KeyError):
        selector.select(
            incident=make_incident(),
            diagnosis=make_diagnosis(),
        )


def test_catalog_contains_operational_command_but_selector_does_not_generate_one():
    catalog = RemediationActionCatalog()

    entry = make_entry(
        command="printf 'catalog-command'",
    )

    catalog.register(
        entry,
        trigger="TEST_ANOMALY",
    )

    selector = RemediationActionSelector(catalog)

    selected = selector.select(
        incident=make_incident(),
        diagnosis=make_diagnosis(),
    )

    assert selected.command == "printf 'catalog-command'"
    assert selected.command != make_diagnosis().__dict__.get("command")
