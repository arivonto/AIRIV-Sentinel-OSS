from sentinel.diagnostic.models import (
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    Hypothesis,
    Investigation,
    InvestigationState,
)
from sentinel.diagnostic.planner import (
    DiagnosticActionCatalog,
    DiagnosticCatalogEntry,
    DiagnosticPlanner,
)


def make_investigation():
    return Investigation(
        investigation_id="inv-planner",
        incident_id="inc-001",
        component_id="pane-1",
        trigger="test failure",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=10,
            max_repeated_action=3,
            max_risk=10,
            minimum_evidence=1,
        ),
    )


def make_catalog():
    return DiagnosticActionCatalog(
        [
            DiagnosticCatalogEntry(
                name="inspect-pane",
                command="printf pane-state",
                classification=DiagnosticActionClassification.OBSERVE,
                rationale="Inspect current pane state",
                expected_information="pane state",
            ),
            DiagnosticCatalogEntry(
                name="inspect-runtime",
                command="printf runtime-state",
                classification=DiagnosticActionClassification.DIAGNOSTIC,
                rationale="Test runtime hypothesis",
                expected_information="runtime state",
            ),
        ]
    )


def test_catalog_accepts_only_safe_diagnostic_classes():
    catalog = make_catalog()

    assert len(catalog.list()) == 2
    assert all(
        entry.classification
        in {
            DiagnosticActionClassification.OBSERVE,
            DiagnosticActionClassification.DIAGNOSTIC,
        }
        for entry in catalog.list()
    )


def test_catalog_rejects_consequential_action():
    try:
        DiagnosticActionCatalog(
            [
                DiagnosticCatalogEntry(
                    name="restart-service",
                    command="systemctl restart something",
                    classification=(
                        DiagnosticActionClassification.CONSEQUENTIAL
                    ),
                    rationale="restart",
                    expected_information="service state",
                )
            ]
        )
    except ValueError as exc:
        assert str(exc) == "catalog_action_classification_not_allowed"
    else:
        raise AssertionError(
            "CONSEQUENTIAL action must not enter diagnostic catalog"
        )


def test_catalog_rejects_prohibited_action():
    try:
        DiagnosticActionCatalog(
            [
                DiagnosticCatalogEntry(
                    name="prohibited",
                    command="rm -rf /",
                    classification=(
                        DiagnosticActionClassification.PROHIBITED
                    ),
                    rationale="prohibited",
                    expected_information="none",
                )
            ]
        )
    except ValueError as exc:
        assert str(exc) == "catalog_action_classification_not_allowed"
    else:
        raise AssertionError(
            "PROHIBITED action must not enter diagnostic catalog"
        )


def test_planner_creates_planned_action_from_catalog():
    investigation = make_investigation()
    planner = DiagnosticPlanner(make_catalog())

    action = planner.plan(
        investigation,
        "inspect-pane",
    )

    assert action.investigation_id == investigation.investigation_id
    assert action.incident_id == investigation.incident_id
    assert action.command == "printf pane-state"
    assert action.classification is DiagnosticActionClassification.OBSERVE
    assert action.state is DiagnosticActionState.PLANNED
    assert action.diagnostic_action_id.startswith(
        "diagnostic-action:"
    )


def test_each_plan_receives_new_action_identity():
    investigation = make_investigation()
    planner = DiagnosticPlanner(make_catalog())

    first = planner.plan(
        investigation,
        "inspect-pane",
    )

    second = planner.plan(
        investigation,
        "inspect-pane",
    )

    assert first.diagnostic_action_id != second.diagnostic_action_id


def test_planner_can_plan_diagnostic_action_for_hypothesis():
    investigation = make_investigation()
    planner = DiagnosticPlanner(make_catalog())

    hypothesis = Hypothesis(
        hypothesis_id="hyp-001",
        investigation_id=investigation.investigation_id,
        statement="runtime is unhealthy",
    )

    action = planner.plan(
        investigation,
        "inspect-runtime",
        hypothesis=hypothesis,
    )

    assert action.classification is DiagnosticActionClassification.DIAGNOSTIC
    assert action.command == "printf runtime-state"


def test_planner_rejects_foreign_hypothesis():
    investigation = make_investigation()
    planner = DiagnosticPlanner(make_catalog())

    hypothesis = Hypothesis(
        hypothesis_id="hyp-foreign",
        investigation_id="other-investigation",
        statement="foreign hypothesis",
    )

    try:
        planner.plan(
            investigation,
            "inspect-runtime",
            hypothesis=hypothesis,
        )
    except ValueError as exc:
        assert str(exc) == "hypothesis_investigation_id_mismatch"
    else:
        raise AssertionError(
            "foreign hypothesis must be rejected"
        )


def test_planner_rejects_unknown_catalog_action():
    investigation = make_investigation()
    planner = DiagnosticPlanner(make_catalog())

    try:
        planner.plan(
            investigation,
            "not-registered",
        )
    except ValueError as exc:
        assert str(exc) == "diagnostic_action_not_in_catalog"
    else:
        raise AssertionError(
            "unknown catalog action must be rejected"
        )


def test_planner_rejects_inactive_investigation():
    investigation = make_investigation()
    investigation.state = InvestigationState.COMPLETED

    planner = DiagnosticPlanner(make_catalog())

    try:
        planner.plan(
            investigation,
            "inspect-pane",
        )
    except ValueError as exc:
        assert str(exc) == "investigation_not_active"
    else:
        raise AssertionError(
            "inactive investigation must be rejected"
        )


def test_planner_exposes_no_execution_or_authorization_authority():
    planner = DiagnosticPlanner(make_catalog())

    public_methods = {
        name
        for name in dir(planner)
        if not name.startswith("_")
    }

    assert public_methods == {"catalog", "plan"}

def test_planner_binds_component_id_safely():
    investigation = Investigation(
        investigation_id="INV-BIND",
        incident_id="INC-BIND",
        component_id="airiv:0'; touch /tmp/should-not-exist; echo '",
        trigger="ANOMALY",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=5,
            max_repeated_action=2,
            max_risk=5,
            minimum_evidence=1,
        ),
    )

    catalog = DiagnosticActionCatalog(
        entries=[
            DiagnosticCatalogEntry(
                name="tmux_probe",
                command="tmux display-message -p -t {component_id} '#{{pane_dead}}'",
                classification=DiagnosticActionClassification.OBSERVE,
                rationale="Inspect pane state.",
                expected_information="pane state",
            )
        ]
    )

    planner = DiagnosticPlanner(catalog)
    action = planner.plan(investigation, "tmux_probe")

    assert action.command.startswith("tmux display-message -p -t ")
    assert "{component_id}" not in action.command
    assert "touch /tmp/should-not-exist" in action.command
    assert action.command.endswith("'#{{pane_dead}}'")

