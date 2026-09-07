"""Pure dispatch continuity and caller-bounded freshness; no authorization."""
from dataclasses import dataclass, field, InitVar
import math

from sentinel.systemd_evidence import TrustedSystemdEvidenceRecord
from sentinel.systemd_incident_dispatch import (
    SystemdDispatchEvidenceIdentity, SystemdIncidentDispatchAssessment,
)
from sentinel.systemd_production_target_policy import ACTION_RESTART


def _finite_nonnegative(value):
    try:
        return (type(value) in (int, float)
                and math.isfinite(value) and value >= 0)
    except OverflowError:
        return False


@dataclass(frozen=True, slots=True, kw_only=True)
class TrustedSystemdDispatchEvidenceBinding:
    """Bind one exact assessed record. Callers must recheck at actual handoff.

    Like D8.6, this checks trusted in-process inputs, not their provenance.
    Multiple supporting records remain separately identified in the assessment.
    A binding certifies freshness only for its supplied record.
    """

    assessment: SystemdIncidentDispatchAssessment
    evidence: TrustedSystemdEvidenceRecord
    now: InitVar[float]
    max_age_seconds: float
    validated_at: float = field(init=False)
    expires_at: float = field(init=False)
    identity: SystemdDispatchEvidenceIdentity = field(init=False)

    def __post_init__(self, now):
        if (type(self.assessment) is not SystemdIncidentDispatchAssessment
                or self.assessment.candidate is not True
                or type(self.evidence) is not TrustedSystemdEvidenceRecord):
            raise ValueError('eligible dispatch and trusted evidence required')
        self.evidence.__post_init__()
        assessment, evidence = self.assessment, self.evidence
        identities = assessment.trusted_evidence_identities
        identity = SystemdDispatchEvidenceIdentity.from_record(evidence)
        if (assessment.incident_id != evidence.incident_id
                or assessment.component_id != evidence.component_id
                or assessment.unit != evidence.snapshot.identity.unit_name
                or assessment.action != ACTION_RESTART
                or type(identities) is not tuple
                or any(type(item) is not SystemdDispatchEvidenceIdentity for item in identities)
                or identities.count(identity) != 1):
            raise ValueError('dispatch evidence continuity mismatch')
        if not _finite_nonnegative(now):
            raise ValueError('now must be finite and non-negative')
        if (not _finite_nonnegative(self.max_age_seconds)
                or self.max_age_seconds <= 0):
            raise ValueError('max_age_seconds must be finite and positive')
        if (now < evidence.observed_at
                or now - evidence.observed_at > self.max_age_seconds):
            raise ValueError('future or stale evidence')
        expires_at = evidence.observed_at + self.max_age_seconds
        if not _finite_nonnegative(expires_at):
            raise ValueError('evidence expiry must be finite')
        object.__setattr__(self, 'validated_at', now)
        object.__setattr__(self, 'expires_at', expires_at)
        object.__setattr__(self, 'identity', identity)

    def is_fresh(self, now):
        """False for invalid time, evidence from the future, or expired evidence."""
        return (_finite_nonnegative(now)
                and self.identity.observed_at <= now <= self.expires_at
                and now - self.identity.observed_at <= self.max_age_seconds)
