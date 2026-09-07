"""Deterministic candidates from persisted canonical TMUX observations only."""

from hashlib import sha256
import json

from .models import Hypothesis, HypothesisStatus, Investigation, InvestigationState
from .store import InvestigationStore


class EvidenceHypothesisGenerator:
    def __init__(self, store: InvestigationStore) -> None:
        self.store = store

    def generate(self, investigation: Investigation) -> list[Hypothesis]:
        if (investigation.state is not InvestigationState.ACTIVE
                or investigation.budget.exhausted()
                or len(investigation.action_ids) >= investigation.budget.max_actions):
            return []

        observations = []
        for reference in sorted(set(investigation.observation_ids)):
            if reference not in investigation.evidence_ids:
                continue
            observation = self.store.get_observation(investigation.investigation_id, reference)
            if (observation is None
                    or observation.observation_id != reference
                    or observation.investigation_id != investigation.investigation_id
                    or observation.component_id != investigation.component_id
                    or observation.source != "TMUX"
                    or observation.subject != "pane_dead"
                    or not isinstance(observation.value, dict)
                    or observation.value.get("pane_id") != investigation.component_id
                    or type(observation.value.get("pane_dead")) is not bool):
                continue
            observations.append(observation)

        # Mixed liveness evidence is outside V1: never select a stale dead fact.
        if not observations or any(o.value["pane_dead"] is False for o in observations):
            return []
        first = min(observations, key=lambda o: (o.observed_at, o.observation_id))
        identity = json.dumps(["tmux-pane-dead-v1", investigation.investigation_id,
                               investigation.incident_id, investigation.component_id])
        return [Hypothesis(
            hypothesis_id="hypothesis:" + sha256(identity.encode()).hexdigest(),
            investigation_id=investigation.investigation_id,
            statement=f"Monitored TMUX pane {investigation.component_id} was observed terminated (pane_dead=True).",
            status=HypothesisStatus.SUPPORTED,
            supporting_evidence_ids=[first.observation_id],
            created_at=first.observed_at,
            updated_at=first.observed_at,
        )]
