# AIRIV Sentinel — Systemd Commander Production Policy Wiring Contract V1

## 1. Purpose

D8.3 wires the D8.2 production-systemd target-safety authorization
into the existing `SystemdCommanderIntegration.execute_verified()`
execution path.

The existing integration remains the single systemd Commander
execution path.

D8.3 is repository-only.

No host authorization or live systemd effect is introduced.

---

## 2. Legacy Compatibility

Existing `execute_verified()` behavior MUST remain the default.

When no production context is supplied, authorization MUST use exactly:

`RemediationPolicy.evaluate_bound()`

Existing callers MUST require no changes.

Existing canary behavior and tests MUST remain compatible.

---

## 3. Production Mode

Production-aware execution is explicitly selected by supplying a
production evaluation timestamp.

Production mode MUST use exactly:

`RemediationPolicy.evaluate_systemd_production_bound()`

The returned target-safety assessment is informational to the
integration; ALLOW/DENY remains owned by `RemediationPolicy`.

---

## 4. Exactly One Canonical Policy Evaluation

For one invocation of `execute_verified()`:

- legacy mode invokes `evaluate_bound()` exactly once;
- production mode invokes
  `evaluate_systemd_production_bound()` exactly once;
- D8.2 internally invokes existing `evaluate_bound()` exactly once.

The integration MUST NOT independently evaluate target eligibility.

---

## 5. No Duplicate Execution Path

D8.3 MUST NOT:

- add a second executor;
- add a second permit adapter;
- add a second execution identity boundary;
- add a second verifier;
- duplicate the execution body;
- call `execute_verified()` recursively.

Both legacy and production authorization MUST converge into the
existing permit/execution/verification path.

---

## 6. Production Context

Production mode accepts only these additional facts:

- `production_now`;
- `production_attempts`;
- `active_production_effects`.

These facts are forwarded unchanged to the canonical D8.2 policy
method.

The integration MUST NOT own cooldown, retry-budget, target allowlist,
or blast-radius policy.

---

## 7. Denial Semantics

If D8.2 returns DENY:

- no permit may be issued;
- no execution identity may be created;
- no executor call may occur;
- no post-effect snapshot may be requested;
- no verification may occur.

Existing denial behavior remains authoritative.

---

## 8. Production Default-Deny

Production allowlist remains empty by default.

Therefore enabling production mode without explicit target-policy
configuration MUST deny before execution.

D8.3 itself MUST NOT populate a production allowlist.

---

## 9. Host Authorization

D8.3 MUST NOT:

- modify polkit;
- modify systemd units;
- restart Sentinel;
- restart the canary;
- create a live request;
- execute systemctl.

Real production host authorization remains a later
Commander-gated milestone.

---

## 10. Authority Invariants

Authority remains:

- target-safety facts:
  `SystemdProductionTargetPolicy`;
- canonical ALLOW/DENY:
  `RemediationPolicy`;
- permit:
  existing permit adapter/boundary;
- execution:
  existing ExecutionBoundary;
- verification:
  existing SystemdRestartVerifier;
- final lifecycle:
  existing higher-level Commander/incident authority.

D8.3 introduces no new authority.
