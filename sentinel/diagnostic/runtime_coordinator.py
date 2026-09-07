"""AIRIV Sentinel runtime boundary for autonomous diagnostics."""

from __future__ import annotations

import threading
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Any

from sentinel.diagnostic.budget import BudgetManager
from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_decider import CommanderIntentDecider
from sentinel.commander_intent_assessor import CommanderIntentAssessor
from sentinel.commander_semantic_policy import CommanderSemanticPolicy

from sentinel.diagnostic.commander_handoff import (
    CommanderHandoff,
    RemediationActionRequest,
)
from sentinel.diagnostic.engine import DiagnosticEngine
from sentinel.diagnostic.evidence import EvidenceAdapter
from sentinel.diagnostic.evaluator import DiagnosisEvaluator
from sentinel.diagnostic.executor import DiagnosticExecutor
from sentinel.diagnostic.hypothesis import HypothesisManager
from sentinel.diagnostic.investigation import InvestigationManager
from sentinel.diagnostic.models import (
    DiagnosticBudget,
    Investigation,
    InvestigationState,
)
from sentinel.diagnostic.planner import (
    DiagnosticActionCatalog,
    DiagnosticCatalogEntry,
    DiagnosticPlanner,
)
from sentinel.diagnostic.recovery import RecoveryManager
from sentinel.diagnostic.store import InvestigationStore
from sentinel.incidents.manager import Incident
from sentinel.remediation_action_catalog import (
    RemediationActionCatalog,
    RemediationActionSelector,
)
from sentinel.commander import CommanderResult
from sentinel.final_outcome_mapper import FinalOutcomeMapper
from sentinel.incidents.manager import IncidentManager
from sentinel.remediation_policy import PolicyDecision


@dataclass(frozen=True, slots=True)
class RuntimeDiagnosticConfig:
    max_duration_seconds: float = 60.0
    max_actions: int = 5
    max_repeated_action: int = 2
    max_risk: int = 5
    minimum_evidence: int = 1
    cycle_interval_seconds: float = 1.0


@dataclass(frozen=True, slots=True)
class CommanderHandoffResult:
    request: RemediationActionRequest
    decision: Any


class RuntimeDiagnosticCoordinator:
    """
    Runtime -> DiagnosticEngine -> Commander integration boundary.

    Runtime owns detection and scheduling.
    DiagnosticEngine owns investigation sequencing.
    IncidentManager remains the sole Incident lifecycle authority.
    Commander remains the sole consequential authorization boundary.
    """

    def __init__(
        self,
        config: RuntimeDiagnosticConfig | None = None,
        *,
        commander_handoff: CommanderHandoff | None = None,
        incident_lookup: Callable[[str], Incident | None] | None = None,
        remediation_action_catalog: RemediationActionCatalog | None = None,
        commander_semantic_policy: CommanderSemanticPolicy | None = None,
        incident_manager: IncidentManager | None = None,
        decision_observer: Callable[[dict], None] | None = None,
    ) -> None:
        self.config = config or RuntimeDiagnosticConfig()

        self.store = InvestigationStore()
        self.investigation_manager = InvestigationManager(self.store)

        self.catalog = DiagnosticActionCatalog(
            entries=[
                DiagnosticCatalogEntry(
                    name="tmux_pane_state",
                    command=(
                        "tmux display-message -p -t {component_id} "
                        "'#{{pane_dead}}|#{{pane_pid}}|"
                        "#{{pane_current_command}}'"
                    ),
                    classification=__import__(
                        "sentinel.diagnostic.models",
                        fromlist=["DiagnosticActionClassification"],
                    ).DiagnosticActionClassification.OBSERVE,
                    rationale="Inspect canonical TMUX pane runtime state.",
                    expected_information=(
                        "pane dead state, pane PID, current command"
                    ),
                ),
                DiagnosticCatalogEntry(
                    name="tmux_pane_identity",
                    command=(
                        "tmux display-message -p -t {component_id} "
                        "'#{{session_name}}|#{{window_index}}|"
                        "#{{pane_index}}|#{{pane_id}}'"
                    ),
                    classification=__import__(
                        "sentinel.diagnostic.models",
                        fromlist=["DiagnosticActionClassification"],
                    ).DiagnosticActionClassification.OBSERVE,
                    rationale="Inspect canonical TMUX pane identity.",
                    expected_information=(
                        "session, window, pane identity"
                    ),
                ),
            ]
        )

        self.planner = DiagnosticPlanner(self.catalog)
        self.executor = DiagnosticExecutor()
        self.hypothesis_manager = HypothesisManager(
            self.investigation_manager
        )
        self.diagnosis_evaluator = DiagnosisEvaluator()
        self.budget_manager = BudgetManager()
        self.recovery_manager = RecoveryManager(self.store)
        self.evidence_adapter = EvidenceAdapter(
            self.investigation_manager
        )

        self.engine = DiagnosticEngine(
            investigation_manager=self.investigation_manager,
            planner=self.planner,
            executor=self.executor,
            hypothesis_manager=self.hypothesis_manager,
            diagnosis_evaluator=self.diagnosis_evaluator,
            budget_manager=self.budget_manager,
            recovery_manager=self.recovery_manager,
            evidence_adapter=self.evidence_adapter,
        )

        self.commander_handoff = commander_handoff
        self.commander_intent_decider = CommanderIntentDecider()
        self.commander_semantic_policy = (
            commander_semantic_policy
            if commander_semantic_policy is not None
            else CommanderSemanticPolicy()
        )
        self.commander_intent_assessor = CommanderIntentAssessor(
            semantic_policy=self.commander_semantic_policy
        )
        self.incident_lookup = incident_lookup
        self.incident_manager = incident_manager
        self.decision_observer = decision_observer

        self.remediation_action_catalog = (
            remediation_action_catalog
            if remediation_action_catalog is not None
            else RemediationActionCatalog()
        )
        self.remediation_action_selector = RemediationActionSelector(
            self.remediation_action_catalog
        )

        self._investigation_by_incident: dict[str, str] = {}
        self._handoff_by_investigation: dict[
            str,
            CommanderHandoffResult,
        ] = {}
        self._final_outcome_by_investigation: dict[str, str] = {}

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _budget(self) -> DiagnosticBudget:
        return DiagnosticBudget(
            max_duration_seconds=self.config.max_duration_seconds,
            max_actions=self.config.max_actions,
            max_repeated_action=self.config.max_repeated_action,
            max_risk=self.config.max_risk,
            minimum_evidence=self.config.minimum_evidence,
        )

    def register_incident(self, incident: Incident) -> Investigation:
        if not isinstance(incident, Incident):
            raise TypeError("incident must be a canonical Incident")

        with self._lock:
            existing_id = self._investigation_by_incident.get(
                incident.incident_id
            )

            if existing_id:
                existing = self.investigation_manager.get(existing_id)
                if existing is not None:
                    return self._record_incident_evidence(existing, incident)

            investigations = self.investigation_manager.recover()

            for investigation in investigations:
                if investigation.incident_id == incident.incident_id:
                    self._investigation_by_incident[
                        incident.incident_id
                    ] = investigation.investigation_id
                    return self._record_incident_evidence(investigation, incident)

            investigation = self.engine.start(
                incident_id=incident.incident_id,
                component_id=incident.component_id,
                trigger=incident.anomaly_type,
                budget=self._budget(),
            )

            self._investigation_by_incident[
                incident.incident_id
            ] = investigation.investigation_id

            return self._record_incident_evidence(investigation, incident)

    def _record_incident_evidence(self, investigation: Investigation, incident: Incident) -> Investigation:
        self.evidence_adapter.record_incident_observations(
            investigation, incident.get_evidence_records(),
        )
        return self.investigation_manager.get(investigation.investigation_id) or investigation

    def submit(self, incidents: Iterable[Incident]) -> None:
        for incident in incidents:
            self.register_incident(incident)


    def _map_and_terminalize_final_outcome(
        self,
        *,
        investigation_id: str,
        incident: Incident,
        intent: CommanderIntent,
        policy_decision: PolicyDecision | None = None,
        execution_succeeded: bool | None = None,
        verification_succeeded: bool | None = None,
    ) -> str | None:
        """
        Map semantic/runtime facts to a canonical Incident outcome.

        FinalOutcomeMapper is pure semantic authority.
        IncidentManager remains the sole lifecycle mutation authority.
        """
        final_outcome = FinalOutcomeMapper.map(
            intent=intent,
            policy_decision=policy_decision,
            execution_succeeded=execution_succeeded,
            verification_succeeded=verification_succeeded,
        )

        if final_outcome is None:
            return None

        if self.incident_manager is None:
            return final_outcome

        recovery_evidence = {
            "source": "final_outcome_mapper",
            "investigation_id": investigation_id,
            "incident_id": incident.incident_id,
            "component_id": incident.component_id,
            "commander_intent": intent.value,
            "policy_decision": (
                policy_decision.value
                if policy_decision is not None
                else None
            ),
            "execution_succeeded": execution_succeeded,
            "verification_succeeded": verification_succeeded,
            "final_outcome": final_outcome,
        }

        observation = {
            "incident_id": incident.incident_id,
            "component_id": incident.component_id,
            "final_outcome": final_outcome,
        }

        self.incident_manager.resolve(
            component_id=incident.component_id,
            recovery_evidence=recovery_evidence,
            observation=observation,
            operator_note=(
                "Autonomous Commander terminalized incident "
                f"with outcome: {final_outcome}."
            ),
            final_outcome=final_outcome,
        )

        with self._lock:
            self._final_outcome_by_investigation[
                investigation_id
            ] = final_outcome

        return final_outcome

    def _handoff_diagnosis(
        self,
        investigation: Investigation,
        diagnosis: Any,
    ) -> CommanderHandoffResult | None:
        """
        Convert diagnosis semantics into the canonical Commander path.

        This boundary:
        - does not generate commands
        - does not authorize remediation itself
        - does not execute commands itself
        - does not verify remediation itself
        - does not mutate Incident lifecycle directly
        """
        investigation_id = investigation.investigation_id

        # Terminalized and handoff results are idempotent at the
        # investigation boundary. This check occurs before incident lookup
        # because IncidentManager removes terminal incidents from active state.
        with self._lock:
            existing_handoff = self._handoff_by_investigation.get(
                investigation_id
            )
            already_terminalized = (
                investigation_id
                in self._final_outcome_by_investigation
            )

        if existing_handoff is not None:
            return existing_handoff

        if already_terminalized:
            return None

        if self.incident_lookup is None:
            return None

        incident = self.incident_lookup(
            investigation.incident_id
        )

        if incident is None:
            raise RuntimeError(
                "Commander handoff incident not found: "
                f"{investigation.incident_id}"
            )

        if (incident.incident_id != investigation.incident_id
                or incident.component_id != investigation.component_id):
            raise ValueError("diagnostic incident identity mismatch")

        remediation_action_available = False
        remediation_action_entry = None
        remediation_action_error: Exception | None = None

        if diagnosis.status.value == "ESTABLISHED":
            try:
                remediation_action_entry = (
                    self.remediation_action_selector.select(
                        incident=incident,
                        diagnosis=diagnosis,
                    )
                )
                remediation_action_available = True
            except (KeyError, ValueError) as exc:
                remediation_action_error = exc

        intent_assessment = self.commander_intent_assessor.assess(
            incident=incident,
            diagnosis=diagnosis,
            remediation_action_available=remediation_action_available,
        )

        if (
            diagnosis.status.value == "ESTABLISHED"
            and intent_assessment.remediation_required
            and not intent_assessment.commander_action_required
            and not remediation_action_available
        ):
            if remediation_action_error is not None:
                raise remediation_action_error

            raise RuntimeError(
                "semantic remediation requires a registered action"
            )

        intent_decision = self.commander_intent_decider.decide(
            intent_assessment
        )

        intent = intent_decision.intent

        decision_facts = dict(
            component_id=investigation.component_id,
            incident_id=investigation.incident_id,
            investigation_id=investigation_id,
            diagnosis_id=diagnosis.diagnosis_id,
            semantic_configured=intent_assessment.semantic_configured,
            remediation_required=intent_assessment.remediation_required,
            commander_action_required=intent_assessment.commander_action_required,
            semantic_reason=intent_assessment.semantic_reason,
            commander_intent=intent.value,
        )

        # --------------------------------------------------------
        # Non-autonomous semantic outcomes
        # --------------------------------------------------------

        if intent is not CommanderIntent.AUTONOMOUS_REMEDIATE:
            final_disposition = self._map_and_terminalize_final_outcome(
                investigation_id=investigation_id,
                incident=incident,
                intent=intent,
            )
            self._publish_decision(dict(decision_facts, final_disposition=final_disposition))
            return None

        # --------------------------------------------------------
        # Autonomous remediation requires the canonical Handoff.
        # --------------------------------------------------------

        if self.commander_handoff is None:
            self._publish_decision(decision_facts)
            return None

        if remediation_action_entry is None:
            raise RuntimeError(
                "AUTONOMOUS_REMEDIATE requires a registered action"
            )

        entry = remediation_action_entry

        request = RemediationActionRequest.from_diagnosis(
            incident_id=incident.incident_id,
            diagnosis=diagnosis,
            action=entry.action,
            reason=diagnosis.conclusion,
        )

        decision = self.commander_handoff.decide(
            request=request,
            incident=incident,
        )

        policy_decision = (
            PolicyDecision.ALLOW
            if decision.authorized
            else PolicyDecision.DENY
        )

        commander_result: CommanderResult | None = None
        execution_succeeded: bool | None = None
        verification_succeeded: bool | None = None

        if decision.authorized:
            remediation_result = self.commander_handoff.remediate(
                request=request,
                incident=incident,
                command=entry.command,
                decision=decision,
            )

            if not isinstance(
                remediation_result,
                CommanderResult,
            ):
                raise TypeError(
                    "authorized CommanderHandoff.remediate() "
                    "must return CommanderResult"
                )

            commander_result = remediation_result

            if commander_result.execution is not None:
                execution_succeeded = bool(
                    commander_result.execution.success
                )
            else:
                execution_succeeded = False

            if commander_result.remediation is not None:
                verification = (
                    commander_result.remediation.verification
                )

                if verification is not None:
                    verification_succeeded = bool(
                        verification.verified
                    )

        final_disposition = self._map_and_terminalize_final_outcome(
            investigation_id=investigation_id,
            incident=incident,
            intent=intent,
            policy_decision=policy_decision,
            execution_succeeded=execution_succeeded,
            verification_succeeded=verification_succeeded,
        )

        decision_facts.update(final_disposition=final_disposition,
                              remediation_policy_decision=policy_decision.value)
        if commander_result is not None and commander_result.remediation is not None:
            execution_id = getattr(commander_result.remediation, "execution_id", None)
            if execution_id is not None:
                decision_facts["execution_id"] = execution_id
        self._publish_decision(decision_facts)

        result = CommanderHandoffResult(
            request=request,
            decision=decision,
        )

        with self._lock:
            self._handoff_by_investigation[
                investigation_id
            ] = result

        return result

    def _publish_decision(self, facts: dict) -> None:
        """Publish existing results without giving the observer authority."""
        if self.decision_observer is not None:
            try:
                self.decision_observer(dict(facts))
            except Exception as error:
                logging.getLogger(__name__).warning(
                    "Commander evidence persistence failed: %s", type(error).__name__
                )

    def get_handoff(
        self,
        investigation_id: str,
    ) -> CommanderHandoffResult | None:
        with self._lock:
            return self._handoff_by_investigation.get(
                investigation_id
            )

    def run_cycle(self) -> list:
        """
        Execute at most one diagnostic step for each active investigation.

        An ESTABLISHED diagnosis may produce exactly one explicit
        Commander action-request handoff. The handoff performs
        authorization only; it does not execute remediation.
        """
        results = []

        with self._lock:
            investigation_ids = list(
                self._investigation_by_incident.values()
            )

        for investigation_id in investigation_ids:
            investigation = self.investigation_manager.get(
                investigation_id
            )

            if investigation is None:
                continue

            if investigation.state is not InvestigationState.ACTIVE:
                continue

            try:
                result = self.engine.step(investigation_id)

                if result.diagnosis is not None:
                    self._handoff_diagnosis(
                        result.investigation,
                        result.diagnosis,
                    )

            except Exception as exc:
                print(
                    "[SENTINEL] Diagnostic cycle error "
                    f"{investigation_id}: {exc}"
                )
                continue

            results.append(result)

        return results

    def recover(self) -> list:
        records = self.engine.recover()

        with self._lock:
            for investigation in self.investigation_manager.recover():
                self._investigation_by_incident[
                    investigation.incident_id
                ] = investigation.investigation_id

        return records

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            self.run_cycle()
            self._stop_event.wait(
                self.config.cycle_interval_seconds
            )

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_event.clear()
            self.recover()

            self._thread = threading.Thread(
                target=self._worker,
                name="airiv-diagnostic-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None

        if thread is not None:
            thread.join(timeout=2.0)
