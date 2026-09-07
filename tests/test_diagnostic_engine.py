from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from sentinel.diagnostic.budget import BudgetDecision
from sentinel.diagnostic.engine import (
    DiagnosticActionSelector,
    DiagnosticEngine,
    DiagnosticStepResult,
)
from sentinel.diagnostic.executor import DiagnosticResult
from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    Diagnosis,
    DiagnosisStatus,
    Investigation,
    InvestigationState,
)
from sentinel.diagnostic.planner import DiagnosticActionCatalog, DiagnosticCatalogEntry


def make_investigation(
    *,
    state=InvestigationState.ACTIVE,
    consumed_actions=0,
    evidence_ids=None,
):
    now = datetime.now(timezone.utc)

    return Investigation(
        investigation_id="investigation:test",
        incident_id="incident:test",
        component_id="component:test",
        trigger="test",
        state=state,
        budget=DiagnosticBudget(
            max_duration_seconds=300,
            max_actions=5,
            max_repeated_action=2,
            max_risk=5,
            minimum_evidence=1,
            consumed_actions=consumed_actions,
        ),
        evidence_ids=list(evidence_ids or []),
        created_at=now,
        updated_at=now,
    )


def make_engine(
    *,
    investigation=None,
    result=None,
    diagnosis=None,
    selector=None,
):
    manager = MagicMock()
    active_investigation = investigation or make_investigation()
    manager.get.return_value = active_investigation
    manager.record_action.side_effect = (
        lambda investigation_id, action, **kwargs: action
    )
    manager.update_action.side_effect = (
        lambda investigation_id, action: action
    )

    planner = MagicMock()

    action = DiagnosticAction(
        diagnostic_action_id="diagnostic-action:test",
        investigation_id="investigation:test",
        incident_id="incident:test",
        classification=DiagnosticActionClassification.OBSERVE,
        command="printf diagnostic",
        rationale="test",
        expected_information="test output",
    )

    planner.plan.return_value = action

    executor = MagicMock()

    if result is None:
        result = DiagnosticResult(
            diagnostic_action_id=action.diagnostic_action_id,
            command=action.command,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            stdout="diagnostic output",
            stderr="",
            exit_code=0,
            success=True,
            state="COMPLETED",
        )

    executor.execute.return_value = result

    hypothesis_manager = MagicMock()
    hypothesis_manager.get.return_value = None

    evaluator = MagicMock()
    evaluator.evaluate.return_value = diagnosis

    budget_manager = MagicMock()
    budget_manager.check.return_value = BudgetDecision(
        allowed=True,
        reason="action_authorized",
    )

    recovery_manager = MagicMock()

    evidence_adapter = MagicMock()

    if selector is None:
        selector = DiagnosticActionSelector(["safe_observe"])

    return (
        DiagnosticEngine(
            investigation_manager=manager,
            planner=planner,
            executor=executor,
            hypothesis_manager=hypothesis_manager,
            diagnosis_evaluator=evaluator,
            budget_manager=budget_manager,
            recovery_manager=recovery_manager,
            evidence_adapter=evidence_adapter,
            selector=selector,
        ),
        manager,
        planner,
        executor,
        budget_manager,
        evidence_adapter,
    )


def test_step_executes_exactly_one_action():
    engine, manager, planner, executor, budget, evidence = make_engine()

    result = engine.step("investigation:test")

    assert isinstance(result, DiagnosticStepResult)
    assert result.action is not None

    planner.plan.assert_called_once()
    executor.execute.assert_called_once()

    assert executor.execute.call_count == 1
    budget.consume.assert_called_once()
    evidence.record_diagnostic_result.assert_called_once()
    evidence.record_observation.assert_called_once()


def test_step_never_accesses_planner_store():
    engine, manager, planner, executor, budget, evidence = make_engine()

    planner.store = MagicMock()

    engine.step("investigation:test")

    planner.store.assert_not_called()


def test_step_persists_updated_action_through_investigation_manager():
    engine, manager, planner, executor, budget, evidence = make_engine()

    engine.step("investigation:test")

    manager.update_action.assert_called_once()

    updated_action = manager.update_action.call_args.args[1]

    assert updated_action.state is DiagnosticActionState.COMPLETED
    assert updated_action.result is not None


def test_step_creates_observation_from_actual_executor_result():
    engine, manager, planner, executor, budget, evidence = make_engine()

    engine.step("investigation:test")

    evidence.record_observation.assert_called_once()

    observation = evidence.record_observation.call_args.args[1]

    assert observation.investigation_id == "investigation:test"
    assert observation.diagnostic_action_id == "diagnostic-action:test"
    assert observation.component_id == "component:test"
    assert observation.value["stdout"] == "diagnostic output"
    assert observation.value["exit_code"] == 0
    assert observation.value["success"] is True


def test_step_does_not_execute_inactive_investigation():
    investigation = make_investigation(
        state=InvestigationState.COMPLETED,
    )

    engine, manager, planner, executor, budget, evidence = make_engine(
        investigation=investigation,
    )

    result = engine.step("investigation:test")

    executor.execute.assert_not_called()
    planner.plan.assert_not_called()
    budget.consume.assert_not_called()

    assert result.investigation.state is InvestigationState.COMPLETED


def test_unknown_result_becomes_unknown_action():
    result = DiagnosticResult(
        diagnostic_action_id="diagnostic-action:test",
        command="printf diagnostic",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        stdout="",
        stderr="transport failure",
        exit_code=None,
        success=False,
        state="UNKNOWN",
    )

    engine, manager, planner, executor, budget, evidence = make_engine(
        result=result,
    )

    step_result = engine.step("investigation:test")

    updated_action = manager.update_action.call_args.args[1]

    assert updated_action.state is DiagnosticActionState.UNKNOWN
    assert step_result.action is updated_action
    assert evidence.record_diagnostic_result.call_count == 1


def test_selector_rejects_unregistered_result():
    selector = DiagnosticActionSelector(["safe_observe"])

    investigation = make_investigation()

    selector_with_invalid = DiagnosticActionSelector(
        ["safe_observe"],
        selector=lambda *_: "not_registered",
    )

    with pytest.raises(ValueError, match="unregistered"):
        selector_with_invalid.select(investigation, [])


def test_selector_never_generates_command():
    selector = DiagnosticActionSelector(["safe_observe"])

    investigation = make_investigation()

    selected = selector.select(investigation, [])

    assert selected == "safe_observe"


def test_budget_denial_prevents_execution():
    engine, manager, planner, executor, budget, evidence = make_engine()

    budget.check.return_value = BudgetDecision(
        allowed=False,
        reason="budget_exhausted",
    )

    result = engine.step("investigation:test")

    executor.execute.assert_not_called()
    budget.consume.assert_not_called()
    evidence.record_diagnostic_result.assert_not_called()

    manager.mark_budget_exhausted.assert_called_once()
    assert result.action is not None


def test_recovery_delegates_to_recovery_manager():
    engine, manager, planner, executor, budget, evidence = make_engine()

    recovery = [MagicMock()]
    engine.recovery_manager.recover.return_value = recovery

    assert engine.recover() == recovery
    engine.recovery_manager.recover.assert_called_once()


def test_existing_full_diagnostic_boundaries_remain_importable():
    from sentinel.diagnostic.budget import BudgetManager
    from sentinel.diagnostic.evidence import EvidenceAdapter
    from sentinel.diagnostic.evaluator import DiagnosisEvaluator
    from sentinel.diagnostic.executor import DiagnosticExecutor
    from sentinel.diagnostic.hypothesis import HypothesisManager
    from sentinel.diagnostic.investigation import InvestigationManager
    from sentinel.diagnostic.planner import DiagnosticPlanner
    from sentinel.diagnostic.recovery import RecoveryManager

    assert all(
        cls is not None
        for cls in (
            BudgetManager,
            EvidenceAdapter,
            DiagnosisEvaluator,
            DiagnosticExecutor,
            HypothesisManager,
            InvestigationManager,
            DiagnosticPlanner,
            RecoveryManager,
        )
    )
