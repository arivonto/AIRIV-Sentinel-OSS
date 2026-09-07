"""Inert production-systemd orchestration preparation boundary.

Phase 2.13D.D8.8B composes already-locked pure boundaries:

D8.6 dispatch assessment
→ D8.7A trusted evidence
→ D8.7A.1 continuity/freshness binding
→ D8.7B canonical bound-plan construction

This module does not authorize, claim a permit, execute, verify,
terminalize an incident, or automatically dispatch remediation.
"""

from dataclasses import dataclass

from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
)
from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_evidence import (
    TrustedSystemdEvidenceRecord,
)
from sentinel.systemd_evidence_plan_handoff import (
    build_bound_systemd_plan_from_trusted_binding,
)
from sentinel.systemd_incident_dispatch import (
    SystemdIncidentDispatchAssessment,
)
from sentinel.systemd_remediation_safety import (
    SystemdPrivilegeBoundary,
)


@dataclass(
    frozen=True,
    slots=True,
)
class PreparedSystemdProductionRemediation:
    """Pure pre-execution result.

    Possession of this object does not mean remediation is authorized.
    Downstream RemediationPolicy remains the sole ALLOW/DENY authority.
    """

    binding: TrustedSystemdDispatchEvidenceBinding
    plan: BoundSystemdRemediationPlan
    prepared_at: float


class SystemdProductionPreparationBoundary:
    """Compose trusted dispatch/evidence into a canonical bound plan only."""

    def prepare(
        self,
        *,
        assessment: SystemdIncidentDispatchAssessment,
        evidence: TrustedSystemdEvidenceRecord,
        now: float,
        max_age_seconds: float,
        privilege: SystemdPrivilegeBoundary,
        run_id: str,
        execution_id: str,
        permit_id: str,
    ) -> PreparedSystemdProductionRemediation:
        binding = TrustedSystemdDispatchEvidenceBinding(
            assessment=assessment,
            evidence=evidence,
            now=now,
            max_age_seconds=max_age_seconds,
        )

        plan = build_bound_systemd_plan_from_trusted_binding(
            binding=binding,
            now=now,
            privilege=privilege,
            run_id=run_id,
            execution_id=execution_id,
            permit_id=permit_id,
        )

        return PreparedSystemdProductionRemediation(
            binding=binding,
            plan=plan,
            prepared_at=now,
        )
