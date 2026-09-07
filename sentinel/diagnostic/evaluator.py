from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .models import (
    Diagnosis,
    DiagnosisStatus,
    Hypothesis,
    HypothesisStatus,
    Investigation,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DiagnosisEvaluator:
    """
    Deterministically evaluates whether an investigation contains
    sufficient evidence for a defensible diagnosis.

    This evaluator:
    - consumes actual investigation state
    - evaluates hypotheses against evidence references
    - creates a Diagnosis value
    - never executes commands
    - never authorizes remediation
    - never creates or resolves incidents
    - never treats AI confidence as operational truth
    """

    def evaluate(
        self,
        investigation: Investigation,
        hypotheses: list[Hypothesis],
    ) -> Diagnosis:
        if not investigation.investigation_id:
            raise ValueError("investigation_id is required")

        matching_hypotheses = [
            hypothesis
            for hypothesis in hypotheses
            if hypothesis.investigation_id
            == investigation.investigation_id
        ]

        supported = [
            hypothesis
            for hypothesis in matching_hypotheses
            if hypothesis.status == HypothesisStatus.SUPPORTED
            and bool(hypothesis.supporting_evidence_ids)
        ]

        evidence_count = len(investigation.evidence_ids)
        minimum_evidence = investigation.budget.minimum_evidence

        if evidence_count < minimum_evidence:
            return self._insufficient(
                investigation,
                reason="minimum_evidence_not_met",
            )

        if not supported:
            return self._insufficient(
                investigation,
                reason="no_supported_hypothesis",
            )

        defensible = []

        for hypothesis in supported:
            contradiction = set(
                hypothesis.contradicting_evidence_ids
            )

            if contradiction.intersection(
                hypothesis.supporting_evidence_ids
            ):
                continue

            if not set(hypothesis.supporting_evidence_ids).issubset(
                set(investigation.evidence_ids)
            ):
                continue

            defensible.append(hypothesis)

        if not defensible:
            return self._insufficient(
                investigation,
                reason="supporting_evidence_not_defensible",
            )

        hypothesis = defensible[0]

        return Diagnosis(
            diagnosis_id=f"diagnosis:{uuid4()}",
            investigation_id=investigation.investigation_id,
            conclusion=hypothesis.statement,
            status=DiagnosisStatus.ESTABLISHED,
            supporting_evidence_ids=list(
                hypothesis.supporting_evidence_ids
            ),
            contradictory_evidence_ids=list(
                hypothesis.contradicting_evidence_ids
            ),
            confidence_basis=[
                "minimum_evidence_threshold_met",
                "supported_hypothesis_present",
                "supporting_evidence_verified_against_investigation",
                "no_direct_support_contradiction",
            ],
            created_at=utc_now(),
        )

    def _insufficient(
        self,
        investigation: Investigation,
        reason: str,
    ) -> Diagnosis:
        return Diagnosis(
            diagnosis_id=f"diagnosis:{uuid4()}",
            investigation_id=investigation.investigation_id,
            conclusion="",
            status=DiagnosisStatus.INSUFFICIENT_EVIDENCE,
            supporting_evidence_ids=[],
            contradictory_evidence_ids=[],
            confidence_basis=[reason],
            created_at=utc_now(),
        )
