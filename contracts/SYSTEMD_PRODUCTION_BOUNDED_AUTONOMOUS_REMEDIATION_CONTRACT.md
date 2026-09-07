# AIRIV Sentinel — Gate 4 Bounded Autonomous Production Remediation Contract V1

**Status:** GATE 4 FOUNDATION
**Change classification:** Capability expansion
**Live authorization:** NONE

## 1. Purpose

Gate 4 introduces a bounded autonomous production-systemd remediation path without weakening or impersonating the existing Commander-approved path.

Autonomous remediation remains subject to the canonical RemediationPolicy, exact bound-effect authorization, durable production-attempt accounting, execution identity, execution gate, independent verification, evidence, and IncidentManager lifecycle boundaries.

## 2. Initial Target Boundary

The Gate 4 V1 autonomous target is exactly:

`airiv-sentinel-production-remediation-probe.service`

The only supported action is `RESTART` with exact argv:

`/usr/bin/systemctl --no-ask-password restart airiv-sentinel-production-remediation-probe.service`

No wildcard, template, alias expansion, inferred dependency, alternate systemctl verb, or second target is permitted.

## 3. Authority Model

`RemediationPolicy` remains the sole canonical ALLOW/DENY authority.

Gate 4 capability configuration is trusted composition input. It is not policy authorization and MUST NOT manufacture, reuse, or impersonate Commander approval evidence.

For an autonomous attempt:

- `commander_authorization` MUST be absent;
- the production target rule MUST be `AUTONOMOUS`;
- canonical exact-bound policy MUST already be ALLOW;
- target safety MUST independently report `autonomous_eligible=true`.

A Commander-only target can never become autonomous merely because Gate 4 is enabled.

## 4. Default Disabled

Gate 4 capability defaults to disabled.

Repository merge, import, object construction with defaults, daemon startup, or ordinary runtime cycles MUST NOT activate production remediation.

Host enablement and live validation require a separate explicit Commander-approved milestone.

## 5. Exact Effect Binding

Every attempt MUST use an existing canonical `PreparedSystemdProductionRemediation` and preserve exact continuity across:

- trusted systemd evidence;
- incident identity;
- component identity;
- target identity and fingerprint;
- action;
- exact argv;
- run ID;
- execution ID;
- permit ID;
- effect fingerprint.

Gate 4 does not create a weaker effect format.

## 6. Temporary Policy Exposure

Instance-local action/catalog/bound-effect activation may exist only for the duration of one exact attempt.

The activation lease MUST restore the previous policy and catalog state after success or failure.

Production target policy MUST also be restored to default-empty after the attempt.

No persistent broad allowlist is introduced.

## 7. Bounded Target Safety

The exact autonomous target rule MUST enforce:

- positive cooldown;
- finite retry window;
- positive maximum attempts per window;
- at most one active production effect;
- mandatory loaded/active post-state verification;
- mandatory InvocationID change.

The initial Gate 4 profile is conservative:

- cooldown: 3600 seconds;
- retry window: 86400 seconds;
- maximum attempts per window: 1.

Durable production-attempt facts are authoritative for cooldown and retry-budget evaluation.

## 8. Execution and Replay

Policy ALLOW occurs before execution.

Production attempt recording, execution identity, permit validation, execution, and verification remain owned by the existing canonical production integration.

A consumed execution identity cannot execute twice.

A previous production attempt that consumes cooldown/retry budget MUST prevent another autonomous execution inside the configured limits.

## 9. Independent Verification

Execution success alone is not recovery.

Recovery requires independent post-effect observation proving:

- target remains loaded;
- target is active;
- InvocationID differs from the trusted pre-effect snapshot.

## 10. Failure Semantics

All malformed, unknown, mismatched, stale, protected, unsupported, concurrent, cooldown-blocked, or retry-exhausted conditions fail closed.

Failed or indeterminate execution MUST NOT cause automatic retry.

`UNKNOWN` execution identity remains terminal under the existing execution-identity contract.

## 11. Commander Boundary Preservation

Gate 4 MUST NOT alter the semantics of `COMMANDER_ONLY`.

Existing Commander issuance, consumption, activation binding, authorization context, and Gate 3 evidence remain unchanged.

No autonomous component may create a fake `approval_id` or `SystemdProductionCommanderAuthorizationContext`.

## 12. Foundation Scope

The initial repository foundation provides an explicit, default-disabled bounded autonomous composer that can be verified in CI with fake execution and snapshots.

This foundation does not yet:

- wire automatic daemon detection to production remediation;
- enable Gate 4 on a host;
- alter systemd or polkit;
- restart the production probe;
- authorize any live autonomous effect.

Automatic daemon wiring and live proof are separate Gate 4 milestones.
