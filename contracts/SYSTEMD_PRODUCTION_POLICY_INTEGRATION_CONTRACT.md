# AIRIV Sentinel — Systemd Production Policy Integration Contract V1

## 1. Purpose

Integrate D8.1 production-systemd target-safety facts into the canonical
RemediationPolicy authorization boundary.

D8.2 is repository-only and does not modify host authorization.

## 2. Authority

RemediationPolicy remains the sole canonical ALLOW/DENY authority.

SystemdProductionTargetPolicy remains a pure target-safety fact provider.

Target-safety facts may further restrict a canonical bound ALLOW, but
MUST NOT upgrade a canonical DENY.

## 3. Existing Bound Policy

The existing RemediationPolicy.evaluate_bound() implementation MUST
remain unchanged.

Production evaluation MUST invoke evaluate_bound() exactly once.

## 4. Configuration

Production target-policy configuration is instance-local.

Default production target policy is empty.

Configuration MUST NOT:
- add allowed actions;
- configure bound effects;
- create permits;
- execute commands;
- modify polkit.

## 5. Exact Target Binding

The immutable bound effect determines the target.

For systemd production evaluation:

effect.component_id MUST equal:

systemd:<effect.target.unit_name>

Caller-supplied alternate unit names are prohibited.

## 6. Action Mapping

Canonical bound action:

systemd_restart

maps only for target-safety evaluation to:

RESTART

No other action is translated.

## 7. Autonomous Target Eligibility

A canonical bound ALLOW remains ALLOW for autonomous production use
only if target-safety assessment proves:

- exact target allowlisted;
- target not protected;
- AUTONOMOUS mode;
- cooldown satisfied;
- retry budget available;
- no concurrent production effect;
- mandatory verification requirements intact.

Otherwise RemediationPolicy emits DENY.

## 8. Commander-Only

COMMANDER_ONLY production targets MUST be denied by the autonomous
production path.

A future milestone owns Commander-authorized production execution.

## 9. Default-Deny

Installing D8.2 alone MUST NOT make any real systemd service executable.

Default production allowlist remains empty.

Existing allowed_actions and bound-effect configuration remain separate
canonical requirements.

## 10. Fail-Closed

Malformed target identity, unsupported action, unknown target,
protected target, invalid timestamps, cooldown violation, exhausted
retry budget, and blast-radius conflict fail closed.

No retry is introduced.

## 11. Verification

D8.2 preserves D8.1 requirements:

- loaded post-state;
- active post-state;
- changed InvocationID.

Existing systemd verification authority remains unchanged.

## 12. Integration Boundary

D8.2 stops at RemediationPolicy.

SystemdCommanderIntegration MUST remain byte-for-byte unchanged during
this milestone.

No host authorization, service restart, canary effect, or live request
is permitted by D8.2.
