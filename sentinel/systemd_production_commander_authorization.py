"""Trusted durable authorization facts for policy; no decision or execution.

Construction is explicit, outside policy, using the canonical ledger owners.
Like D8.14 trusted inputs, this is an in-process boundary, not authentication
of arbitrary Python code or caller-selected storage roots.
"""
from dataclasses import dataclass

from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer,
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_activation_binding import (
    SystemdProductionConsumedActivationBinding,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionStore,
)
from sentinel.systemd_evidence_plan_handoff import build_bound_systemd_plan_from_trusted_binding


@dataclass(frozen=True, slots=True, init=False)
class SystemdProductionCommanderAuthorizationContext:
    """Immutable snapshot of exact committed issuance and consumption facts.

    Trusted composition must supply the actual canonical ledger owners. Raw
    approval IDs, grants, records or booleans cannot construct this context.
    Policy evaluation performs no storage reads or writes.
    """
    binding: SystemdProductionConsumedActivationBinding
    approval: TrustedSystemdProductionCommanderApproval

    def __init__(self, *, binding, issuer, consumption_store):
        if type(binding) is not SystemdProductionConsumedActivationBinding:
            raise TypeError('canonical consumed activation binding required')
        if type(issuer) is not SystemdProductionCommanderApprovalIssuer:
            raise TypeError('canonical approval issuer required')
        if type(consumption_store) is not SystemdProductionActivationConsumptionStore:
            raise TypeError('canonical consumption store required')
        binding.__post_init__()
        grant = binding.grant
        approval = TrustedSystemdProductionCommanderApproval(
            grant.approval_id, binding.prepared.plan.permit_binding,
            grant.issued_at, grant.expires_at)
        expected = issuer._payload(approval, grant.activation_id)
        if expected not in issuer.records():
            raise ValueError('exact_durable_approval_issuance_required')
        if binding.consumption not in consumption_store.records():
            raise ValueError('exact_durable_activation_consumption_required')
        object.__setattr__(self, 'binding', binding)
        object.__setattr__(self, 'approval', approval)
        if not self.matches(effect=binding.prepared.plan.effect, now=binding.bound_at):
            raise ValueError('commander_authorization_binding_mismatch')

    def matches(self, *, effect, now):
        """Pure continuity/freshness fact, never a policy decision."""
        try:
            binding = self.binding
            if type(binding) is not SystemdProductionConsumedActivationBinding:
                return False
            if type(self.approval) is not TrustedSystemdProductionCommanderApproval:
                return False
            self.approval.__post_init__()
            binding.grant.__post_init__()
            binding.consumption.__post_init__()
            binding.__post_init__()
            if not binding.is_current(now):
                return False
            plan = binding.prepared.plan
            expected = build_bound_systemd_plan_from_trusted_binding(
                binding=binding.prepared.binding, now=now,
                privilege=plan.scope.privilege, run_id=plan.effect.run_id,
                execution_id=plan.effect.execution_id, permit_id=plan.effect.permit_id)
            return (
                plan == expected and effect == expected.effect
                and self.approval.effect == expected.permit_binding
                and self.approval.approval_id == binding.grant.approval_id
                and self.approval.issued_at == binding.grant.issued_at
                and self.approval.expires_at == binding.grant.expires_at
                and binding.prepared.binding.validated_at
                <= binding.prepared.prepared_at <= binding.bound_at
            )
        except (AttributeError, TypeError, ValueError, OverflowError):
            return False
