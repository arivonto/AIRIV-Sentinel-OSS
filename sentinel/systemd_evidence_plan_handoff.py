"""Trusted fresh systemd evidence to canonical bound-plan handoff.

Phase 2.13D.D8.7B.

This module owns plan construction only. It performs no policy
evaluation, permit claim, execution, durable runtime mutation,
verification, or incident lifecycle mutation.
"""

from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
    build_bound_systemd_remediation_plan,
)
from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_target_policy import (
    protected_target,
)
from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope,
    SystemdOperation,
    SystemdPrivilegeBoundary,
)


def build_bound_systemd_plan_from_trusted_binding(
    *,
    binding: TrustedSystemdDispatchEvidenceBinding,
    now: float,
    privilege: SystemdPrivilegeBoundary,
    run_id: str,
    execution_id: str,
    permit_id: str,
) -> BoundSystemdRemediationPlan:
    """Build one canonical pre-execution plan from exact trusted evidence."""

    if type(binding) is not TrustedSystemdDispatchEvidenceBinding:
        raise TypeError(
            "TrustedSystemdDispatchEvidenceBinding required"
        )

    if type(privilege) is not SystemdPrivilegeBoundary:
        raise TypeError(
            "SystemdPrivilegeBoundary required"
        )

    # Freshness authority belongs to D8.7A.1.
    # Recheck immediately at the handoff boundary before constructing
    # any downstream bound-plan data.
    if not binding.is_fresh(now):
        raise ValueError(
            "binding is not fresh at handoff"
        )

    before = binding.evidence.snapshot

    # Structural defence only. This does not evaluate the production
    # target allowlist and does not replace D8.1/D8.2 policy authority.
    if protected_target(
        before.identity.unit_name
    ):
        raise ValueError(
            "protected_target"
        )

    # SystemdPrivilegeBoundary has already validated itself when it was
    # constructed. Never invoke __post_init__ manually here.
    scope = BoundSystemdActionScope(
        target=before.identity,
        operation=SystemdOperation.RESTART,
        privilege=privilege,
        expected_pre_active_state=before.active_state,
        expected_post_active_state="active",
        require_new_invocation=True,
    )

    # Exact canonical vocabulary translation already established by
    # the existing systemd remediation pipeline:
    #
    # target-safety action: RESTART
    # bound remediation action: systemd_restart
    return build_bound_systemd_remediation_plan(
        before=before,
        scope=scope,
        run_id=run_id,
        incident_id=binding.evidence.incident_id,
        action="systemd_restart",
        execution_id=execution_id,
        permit_id=permit_id,
    )
