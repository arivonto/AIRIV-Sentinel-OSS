from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .budget import BudgetManager
from .evaluator import DiagnosisEvaluator
from .evidence import EvidenceAdapter
from .executor import DiagnosticExecutor
from .hypothesis import HypothesisManager
from .hypothesis_generator import EvidenceHypothesisGenerator
from .investigation import InvestigationManager
from .models import (
    DiagnosticAction,
    DiagnosticActionState,
    Diagnosis,
    Hypothesis,
    HypothesisStatus,
    Investigation,
    InvestigationState,
)
from .planner import DiagnosticPlanner
from .recovery import RecoveryManager


@dataclass(frozen=True, slots=True)
class DiagnosticStepResult:
    investigation: Investigation
    action: DiagnosticAction | None = None
    diagnosis: Diagnosis | None = None


class DiagnosticActionSelector:
    """
    Deterministic selector for registered diagnostic catalog entries.

    The selector chooses only catalog names. It never generates commands,
    executes actions, authorizes operations, or modifies investigation state.
    """

    def __init__(
        self,
        catalog_names: list[str],
        selector: Callable[
            [Investigation, list[Hypothesis], list[str]], str
        ] | None = None,
    ) -> None:
        if not catalog_names:
            raise ValueError("Diagnostic catalog must not be empty")

        self._catalog_names = tuple(catalog_names)
        self._selector = selector

    @property
    def catalog_names(self) -> tuple[str, ...]:
        return self._catalog_names

    def select(
        self,
        investigation: Investigation,
        hypotheses: list[Hypothesis],
    ) -> str:
        if investigation.state is not InvestigationState.ACTIVE:
            raise ValueError("Cannot select an action for inactive investigation")

        if self._selector is not None:
            selected = self._selector(
                investigation,
                hypotheses,
                list(self._catalog_names),
            )
        else:
            selected = self._catalog_names[
                investigation.budget.consumed_actions
                % len(self._catalog_names)
            ]

        if selected not in self._catalog_names:
            raise ValueError(
                f"Diagnostic selector returned unregistered catalog entry: "
                f"{selected}"
            )

        return selected


class DiagnosticEngine:
    """
    Orchestration facade for autonomous diagnostic investigation.

    This class owns sequencing only. Existing managers retain their
    respective authority boundaries.
    """

    def __init__(
        self,
        investigation_manager: InvestigationManager,
        planner: DiagnosticPlanner,
        executor: DiagnosticExecutor,
        hypothesis_manager: HypothesisManager,
        diagnosis_evaluator: DiagnosisEvaluator,
        budget_manager: BudgetManager,
        recovery_manager: RecoveryManager,
        evidence_adapter: EvidenceAdapter,
        selector: DiagnosticActionSelector | None = None,
    ) -> None:
        self.investigation_manager = investigation_manager
        self.planner = planner
        self.executor = executor
        self.hypothesis_manager = hypothesis_manager
        self.diagnosis_evaluator = diagnosis_evaluator
        self.budget_manager = budget_manager
        self.recovery_manager = recovery_manager
        self.evidence_adapter = evidence_adapter
        self.hypothesis_generator = EvidenceHypothesisGenerator(investigation_manager.store)

        if selector is None:
            catalog_names = [
                entry.name for entry in self.planner.catalog.list()
            ]
            selector = DiagnosticActionSelector(catalog_names)

        self.selector = selector

    def start(
        self,
        incident_id: str,
        component_id: str,
        trigger: str,
        budget,
        investigation_id: str | None = None,
    ) -> Investigation:
        return self.investigation_manager.start(
            incident_id=incident_id,
            component_id=component_id,
            trigger=trigger,
            budget=budget,
            investigation_id=investigation_id,
        )

    def get(self, investigation_id: str) -> Investigation | None:
        return self.investigation_manager.get(investigation_id)

    def recover(self) -> list:
        return self.recovery_manager.recover()

    def step(self, investigation_id: str) -> DiagnosticStepResult:
        investigation = self.investigation_manager.get(investigation_id)

        if investigation is None:
            raise KeyError(
                f"Investigation not found: {investigation_id}"
            )

        if investigation.state is not InvestigationState.ACTIVE:
            return DiagnosticStepResult(
                investigation=investigation,
                diagnosis=None,
            )

        hypotheses = self._load_hypotheses(investigation)
        for candidate in self.hypothesis_generator.generate(investigation):
            if candidate.hypothesis_id not in investigation.current_hypothesis_ids:
                investigation = self.investigation_manager.record_hypothesis(
                    investigation_id, candidate,
                )
                hypotheses.append(candidate)

        diagnosis = self._evaluate_if_ready(
            investigation,
            hypotheses,
        )

        if diagnosis is not None:
            return DiagnosticStepResult(
                investigation=self.investigation_manager.get(
                    investigation_id
                ) or investigation,
                diagnosis=diagnosis,
            )

        if (investigation.budget.exhausted()
                or len(investigation.action_ids) >= investigation.budget.max_actions):
            investigation = self.investigation_manager.mark_budget_exhausted(
                investigation_id
            )
            return DiagnosticStepResult(
                investigation=investigation,
            )

        catalog_name = self.selector.select(
            investigation,
            hypotheses,
        )

        action = self.planner.plan(
            investigation,
            catalog_name,
            hypothesis=self._select_hypothesis(hypotheses),
        )

        budget_decision = self.budget_manager.check(
            investigation,
            action,
        )

        if not budget_decision.allowed:
            investigation = self.investigation_manager.mark_budget_exhausted(
                investigation_id
            )
            return DiagnosticStepResult(
                investigation=investigation,
                action=action,
            )

        self.budget_manager.consume(
            investigation,
            action,
        )

        self.investigation_manager.record_action(
            investigation_id,
            action,
            consumed_budget=investigation.budget,
        )

        result = self.executor.execute(action)

        action.result = result
        action.started_at = result.started_at
        action.finished_at = result.finished_at
        action.state = (
            DiagnosticActionState.COMPLETED
            if result.state == "COMPLETED"
            else DiagnosticActionState.UNKNOWN
        )

        self.investigation_manager.update_action(
            investigation_id,
            action,
        )

        observation = self._build_observation(
            investigation,
            action,
            result,
        )

        self.evidence_adapter.record_observation(
            investigation,
            observation,
        )

        self.evidence_adapter.record_diagnostic_result(
            investigation,
            action,
            result,
            observation=observation,
        )

        refreshed = (
            self.investigation_manager.get(investigation_id)
            or investigation
        )

        hypotheses = self._load_hypotheses(refreshed)

        diagnosis = self._evaluate_if_ready(
            refreshed,
            hypotheses,
        )

        refreshed = (
            self.investigation_manager.get(investigation_id)
            or refreshed
        )

        if diagnosis is None and refreshed.budget.exhausted():
            refreshed = self.investigation_manager.mark_budget_exhausted(
                investigation_id
            )

        return DiagnosticStepResult(
            investigation=refreshed,
            action=action,
            diagnosis=diagnosis,
        )

    def finalize(self, investigation_id: str) -> Investigation:
        investigation = self.investigation_manager.get(investigation_id)

        if investigation is None:
            raise KeyError(
                f"Investigation not found: {investigation_id}"
            )

        if investigation.state is InvestigationState.ACTIVE:
            raise ValueError(
                "Cannot finalize an active investigation"
            )

        return investigation

    def _load_hypotheses(
        self,
        investigation: Investigation,
    ) -> list[Hypothesis]:
        hypotheses: list[Hypothesis] = []

        for hypothesis_id in investigation.current_hypothesis_ids:
            hypothesis = self.hypothesis_manager.get(
                investigation.investigation_id,
                hypothesis_id,
            )
            if hypothesis is not None:
                hypotheses.append(hypothesis)

        return hypotheses

    @staticmethod
    def _select_hypothesis(
        hypotheses: list[Hypothesis],
    ) -> Hypothesis | None:
        for hypothesis in hypotheses:
            if hypothesis.status in (
                HypothesisStatus.PROPOSED,
                HypothesisStatus.SUPPORTED,
                HypothesisStatus.UNRESOLVED,
            ):
                return hypothesis

        return None

    def _evaluate_if_ready(
        self,
        investigation: Investigation,
        hypotheses: list[Hypothesis],
    ) -> Diagnosis | None:
        if not hypotheses:
            return None

        if len(investigation.evidence_ids) < (
            investigation.budget.minimum_evidence
        ):
            return None

        diagnosis = self.diagnosis_evaluator.evaluate(
            investigation,
            hypotheses,
        )

        if diagnosis.status.value == "ESTABLISHED":
            self.investigation_manager.record_diagnosis(
                investigation.investigation_id,
                diagnosis,
            )
            self.investigation_manager.complete(
                investigation.investigation_id,
            )
            return diagnosis

        return None

    @staticmethod
    def _build_observation(
        investigation: Investigation,
        action: DiagnosticAction,
        result,
    ):
        from datetime import datetime, timezone
        from uuid import uuid4

        return __import__(
            "sentinel.diagnostic.models",
            fromlist=["Observation"],
        ).Observation(
            observation_id=f"observation:{uuid4()}",
            investigation_id=investigation.investigation_id,
            diagnostic_action_id=action.diagnostic_action_id,
            component_id=investigation.component_id,
            observed_at=datetime.now(timezone.utc),
            source="diagnostic_executor",
            subject=action.command,
            value={
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            raw_evidence={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "success": result.success,
                "state": result.state,
            },
        )
