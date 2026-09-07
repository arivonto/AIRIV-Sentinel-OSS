from __future__ import annotations

from datetime import datetime, timezone

from .investigation import InvestigationManager
from .models import Hypothesis, HypothesisStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HypothesisManager:
    """
    Manages hypothesis state inside an existing investigation.

    Authority boundary:
    - may register hypotheses
    - may update hypothesis status
    - may attach supporting evidence references
    - may attach contradicting evidence references

    This manager does not:
    - execute commands
    - authorize remediation
    - create or resolve incidents
    - create diagnosis
    - treat AI output as verified fact
    - bypass InvestigationManager
    """

    ALLOWED_STATUSES = frozenset(HypothesisStatus)

    def __init__(self, investigation_manager: InvestigationManager) -> None:
        self._investigation_manager = investigation_manager

    def propose(
        self,
        investigation_id: str,
        hypothesis: Hypothesis,
    ):
        if hypothesis.status != HypothesisStatus.PROPOSED:
            raise ValueError("new_hypothesis_must_be_proposed")

        return self._investigation_manager.record_hypothesis(
            investigation_id,
            hypothesis,
        )

    def update_status(
        self,
        investigation_id: str,
        hypothesis_id: str,
        status: HypothesisStatus,
    ):
        investigation = self._investigation_manager.get(investigation_id)

        if investigation is None:
            raise ValueError("investigation_not_found")

        if investigation.state.value != "ACTIVE":
            raise ValueError("investigation_not_active")

        if hypothesis_id not in investigation.current_hypothesis_ids:
            raise ValueError("hypothesis_not_found")

        if status not in self.ALLOWED_STATUSES:
            raise ValueError("invalid_hypothesis_status")

        hypothesis = self._get_hypothesis(
            investigation_id,
            hypothesis_id,
        )

        if hypothesis is None:
            raise ValueError("hypothesis_not_found")

        hypothesis.status = status
        hypothesis.updated_at = utc_now()

        self._investigation_manager.store.save_hypothesis(hypothesis)

        self._investigation_manager.store.append_history(
            investigation_id,
            {
                "event": "HYPOTHESIS_STATUS_UPDATED",
                "investigation_id": investigation_id,
                "hypothesis_id": hypothesis_id,
                "status": status.value,
                "occurred_at": utc_now(),
            },
        )

        return self._investigation_manager.get(investigation_id)

    def support(
        self,
        investigation_id: str,
        hypothesis_id: str,
        evidence_id: str,
    ):
        hypothesis = self._require_hypothesis(
            investigation_id,
            hypothesis_id,
        )

        if evidence_id in hypothesis.supporting_evidence_ids:
            raise ValueError("supporting_evidence_already_attached")

        if evidence_id in hypothesis.contradicting_evidence_ids:
            raise ValueError("evidence_already_attached_as_contradicting")

        hypothesis.supporting_evidence_ids.append(evidence_id)
        hypothesis.updated_at = utc_now()

        self._investigation_manager.store.save_hypothesis(hypothesis)

        self._investigation_manager.store.append_history(
            investigation_id,
            {
                "event": "HYPOTHESIS_SUPPORTED",
                "investigation_id": investigation_id,
                "hypothesis_id": hypothesis_id,
                "evidence_id": evidence_id,
                "occurred_at": utc_now(),
            },
        )

        return hypothesis

    def contradict(
        self,
        investigation_id: str,
        hypothesis_id: str,
        evidence_id: str,
    ):
        hypothesis = self._require_hypothesis(
            investigation_id,
            hypothesis_id,
        )

        if evidence_id in hypothesis.contradicting_evidence_ids:
            raise ValueError("contradicting_evidence_already_attached")

        if evidence_id in hypothesis.supporting_evidence_ids:
            raise ValueError("evidence_already_attached_as_supporting")

        hypothesis.contradicting_evidence_ids.append(evidence_id)
        hypothesis.updated_at = utc_now()

        self._investigation_manager.store.save_hypothesis(hypothesis)

        self._investigation_manager.store.append_history(
            investigation_id,
            {
                "event": "HYPOTHESIS_CONTRADICTED",
                "investigation_id": investigation_id,
                "hypothesis_id": hypothesis_id,
                "evidence_id": evidence_id,
                "occurred_at": utc_now(),
            },
        )

        return hypothesis

    def get(
        self,
        investigation_id: str,
        hypothesis_id: str,
    ) -> Hypothesis | None:
        investigation = self._investigation_manager.get(investigation_id)

        if investigation is None:
            return None

        if hypothesis_id not in investigation.current_hypothesis_ids:
            return None

        return self._get_hypothesis(
            investigation_id,
            hypothesis_id,
        )

    def _require_hypothesis(
        self,
        investigation_id: str,
        hypothesis_id: str,
    ) -> Hypothesis:
        investigation = self._investigation_manager.get(investigation_id)

        if investigation is None:
            raise ValueError("investigation_not_found")

        if investigation.state.value != "ACTIVE":
            raise ValueError("investigation_not_active")

        if hypothesis_id not in investigation.current_hypothesis_ids:
            raise ValueError("hypothesis_not_found")

        hypothesis = self._get_hypothesis(
            investigation_id,
            hypothesis_id,
        )

        if hypothesis is None:
            raise ValueError("hypothesis_not_found")

        return hypothesis

    def _get_hypothesis(
        self,
        investigation_id: str,
        hypothesis_id: str,
    ) -> Hypothesis | None:
        return self._investigation_manager.store.get_hypothesis(
            investigation_id, hypothesis_id,
        )
