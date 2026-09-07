"""Pure production routing facts; deliberately not connected to the runtime loop.

The caller supplies canonical investigation/diagnosis and Commander outputs for
the same incident. Systemd evidence must be a diagnostic Observation whose value
is an existing SystemdUnitSnapshot, linked as supporting investigation evidence.
Optional D8.7A records bind those observations to exact durable evidence facts.
The caller loads records from the trusted store; this assessment performs no I/O
and does not certify persistence of directly constructed records. The current
TMUX-only diagnostic producer cannot supply systemd evidence.

A candidate is NOT permission to remediate. Target rules, current safety facts,
canonical authorization and a fresh evidence-to-bound-plan handoff remain
downstream. No plan is built here: canonical incidents do not carry its scope,
run, execution or permit bindings. Callers must reassess mutable inputs before
any future handoff; this result is neither a capability nor a durable approval.
"""

from dataclasses import dataclass
from datetime import datetime

from sentinel.systemd_evidence import TrustedSystemdEvidenceRecord

from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_assessment import CommanderIntentAssessment
from sentinel.commander_intent_decider import CommanderIntentDecision
from sentinel.diagnostic.commander_handoff import RemediationActionRequest
from sentinel.diagnostic.models import (
    Diagnosis, DiagnosisStatus, Investigation, InvestigationState, Observation,
)
from sentinel.incidents.manager import Incident
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART, protected_target, validate_unit_name,
)
from sentinel.systemd_remediation_safety import (
    SystemdManagerIdentity, SystemdUnitIdentity, SystemdUnitSnapshot,
)


@dataclass(frozen=True, slots=True)
class SystemdDispatchEvidenceIdentity:
    evidence_fingerprint: str
    target_fingerprint: str
    invocation_id: str
    observed_at: float

    @classmethod
    def from_record(cls, record: TrustedSystemdEvidenceRecord):
        return cls(record.fingerprint, record.snapshot.identity.fingerprint,
                   record.snapshot.invocation_id, record.observed_at)


@dataclass(frozen=True, slots=True)
class SystemdIncidentDispatchAssessment:
    candidate: bool
    incident_id: str | None
    component_id: str | None
    unit: str | None
    action: str | None
    reasons: tuple[str, ...]
    required_downstream_facts: tuple[str, ...] = (
        "trusted_fresh_evidence_to_bound_plan",
        "explicit_autonomous_production_target_rule",
        "production_target_safety_including_protection_cooldown_retry_blast_radius",
        "canonical_remediation_authorization",
    )
    trusted_evidence_identities: tuple[SystemdDispatchEvidenceIdentity, ...] = ()


def _text(value):
    return type(value) is str and bool(value) and value == value.strip()


def _references(value):
    return (type(value) in (list, tuple) and bool(value)
            and all(_text(item) for item in value)
            and len(set(value)) == len(value))


def assess_systemd_incident_dispatch(
    *, incident: Incident, investigation: Investigation, diagnosis: Diagnosis,
    assessment: CommanderIntentAssessment, decision: CommanderIntentDecision,
    request: RemediationActionRequest, observations: tuple[Observation, ...],
    trusted_evidence: tuple[TrustedSystemdEvidenceRecord, ...] | None = None,
) -> SystemdIncidentDispatchAssessment:
    """Validate supplied routing facts without invoking any downstream owner.

    Reuse D8.1's pure protected-name predicate for early exclusion, never its
    target assessment. All final target-safety facts still belong to D8.1/D8.2.
    No strings, raw output, aliases or component names are converted to identity.
    """
    incident_id = component_id = unit = action = None
    reasons = []
    evidence_identities = ()

    def result():
        return SystemdIncidentDispatchAssessment(
            not reasons, incident_id, component_id, unit, action,
            tuple(reasons) if reasons else ("candidate_pending_downstream_facts",),
            trusted_evidence_identities=evidence_identities,
        )

    expected = ((incident, Incident), (investigation, Investigation),
                (diagnosis, Diagnosis), (assessment, CommanderIntentAssessment),
                (decision, CommanderIntentDecision), (request, RemediationActionRequest))
    if any(type(value) is not cls for value, cls in expected):
        reasons.append("missing_or_malformed_canonical_context")
        return result()
    incident_id = incident.incident_id if _text(incident.incident_id) else None
    component_id = incident.component_id if _text(incident.component_id) else None
    action = request.action if type(request.action) is str else None
    if incident_id is None:
        reasons.append("invalid_incident_id")
    if (incident.status != "INVESTIGATING"
            or incident.lifecycle_state != "INVESTIGATING"
            or incident.final_outcome is not None):
        reasons.append("incident_not_investigating")
    if component_id is None or not component_id.startswith("systemd:"):
        reasons.append("invalid_systemd_component")
    else:
        try:
            unit = validate_unit_name(component_id[len("systemd:"):])
        except (TypeError, ValueError):
            reasons.append("invalid_systemd_unit")
        else:
            if protected_target(unit):
                reasons.append("protected_target")
    if action != ACTION_RESTART:
        reasons.append("unsupported_action")
    if (not _text(investigation.investigation_id)
            or not _text(diagnosis.diagnosis_id)
            or investigation.incident_id != incident_id
            or investigation.component_id != component_id
            or investigation.trigger != incident.anomaly_type
            or investigation.state is not InvestigationState.COMPLETED
            or investigation.diagnosis_id != diagnosis.diagnosis_id
            or diagnosis.investigation_id != investigation.investigation_id
            or request.incident_id != incident_id
            or request.investigation_id != investigation.investigation_id
            or request.diagnosis_id != diagnosis.diagnosis_id):
        reasons.append("canonical_context_mismatch")
    supporting = diagnosis.supporting_evidence_ids
    if (diagnosis.status is not DiagnosisStatus.ESTABLISHED
            or not _text(diagnosis.conclusion)
            or not _references(supporting)
            or not _references(investigation.evidence_ids)
            or type(diagnosis.contradictory_evidence_ids) is not list
            or any(not _text(item) for item in diagnosis.contradictory_evidence_ids)):
        reasons.append("insufficient_diagnosis_evidence")
        return result()
    if (not set(supporting).issubset(investigation.evidence_ids)
            or set(supporting).intersection(diagnosis.contradictory_evidence_ids)
            or request.supporting_evidence_ids != tuple(supporting)):
        reasons.append("diagnosis_evidence_mismatch")
    if (assessment.diagnosis_status is not diagnosis.status
            or assessment.semantic_configured is not True
            or assessment.remediation_required is not True
            or assessment.remediation_action_available is not True
            or assessment.commander_action_required is not False
            or decision.intent is not CommanderIntent.AUTONOMOUS_REMEDIATE):
        reasons.append("autonomous_intent_required")
    # Require all diagnosis support to resolve to unambiguous typed snapshots.
    # Extra/duplicate/foreign observations fail closed, including conflicting
    # healthy evidence; this API is intentionally narrower than generic diagnosis.
    if (type(observations) is not tuple or not observations
            or any(type(o) is not Observation for o in observations)
            or not _references(investigation.observation_ids)):
        reasons.append("missing_systemd_evidence")
        return result()
    ids = [o.observation_id for o in observations]
    if trusted_evidence is not None:
        try:
            if (type(trusted_evidence) is not tuple
                    or len(trusted_evidence) != len(observations)
                    or any(type(r) is not TrustedSystemdEvidenceRecord for r in trusted_evidence)
                    or len({r.observation_id for r in trusted_evidence}) != len(ids)):
                raise ValueError('ambiguous trusted evidence')
            by_id = {r.observation_id: r for r in trusted_evidence}
            for observation in observations:
                record = by_id[observation.observation_id]
                record.__post_init__()
                if (record.incident_id != incident_id
                        or record.investigation_id != investigation.investigation_id
                        or record.component_id != component_id
                        or record.snapshot != observation.value
                        or type(observation.observed_at) is not datetime
                        or observation.observed_at.utcoffset() is None
                        or record.observed_at != observation.observed_at.timestamp()):
                    raise ValueError('trusted evidence mismatch')
            evidence_identities = tuple(
                SystemdDispatchEvidenceIdentity.from_record(by_id[o.observation_id])
                for o in observations
            )
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            reasons.append('invalid_trusted_systemd_evidence')
            return result()
    if (not _references(ids) or set(ids) != set(supporting)
            or not set(ids).issubset(investigation.observation_ids)):
        reasons.append("ambiguous_systemd_evidence")
    first_snapshot = None
    for observation in observations:
        snapshot = observation.value
        if (observation.investigation_id != investigation.investigation_id
                or observation.component_id != component_id
                or observation.source != "SYSTEMD"
                or observation.subject != "unit_snapshot"
                or type(snapshot) is not SystemdUnitSnapshot
                or type(snapshot.identity) is not SystemdUnitIdentity
                or type(snapshot.identity.manager) is not SystemdManagerIdentity):
            reasons.append("missing_exact_systemd_identity")
            break
        if (snapshot.identity.component_id != component_id
                or snapshot.identity.unit_name != unit):
            reasons.append("systemd_identity_mismatch")
            break
        if snapshot.load_state != "loaded" or snapshot.active_state != "failed":
            reasons.append("systemd_failure_evidence_required")
            break
        if first_snapshot is not None and snapshot != first_snapshot:
            reasons.append("ambiguous_systemd_snapshots")
            break
        first_snapshot = snapshot
    return result()
