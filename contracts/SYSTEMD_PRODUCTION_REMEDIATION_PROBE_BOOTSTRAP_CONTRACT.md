# AIRIV Sentinel — Production Remediation Probe Bootstrap Contract V1

## Phase

2.13D.D8.12C

## Exact Target

`airiv-sentinel-production-remediation-probe.service`

## Purpose

D8.12C performs bounded host bootstrap only.

It installs the exact probe and exact least-privilege polkit rule while
production remediation remains unreachable.

## Authorized Host Effects

D8.12C may only:

1. install the exact D8.12B probe unit;
2. run `systemctl daemon-reload`;
3. start the probe exactly once as bootstrap;
4. install the exact D8.12B polkit rule directly at its final `.rules`
   path;
5. verify exact bytes, metadata, identity, hardening, and rule predicates.

## Authorization Evidence Boundary

D8.12C follows the already-locked D7D.1 / D7D.2 evidence semantics.

`pkcheck --process PID,START_TIME,UID` is synthetic evidence.

It MUST NOT be used by D8.12C to claim proof of:

- `subject.system_unit`;
- `subject.no_new_privileges`;
- real systemd D-Bus authorization;
- successful restart authorization.

On polkit 127, a non-trusted caller supplying action details may itself
be rejected by `CheckAuthorization()`.

Such a result is not evidence that the installed rule is defective.

## What D8.12C Validates

D8.12C validates:

- exact unit identity;
- exact unit bytes and SHA-256;
- root:root 0644 unit metadata;
- exact probe hardening;
- exact polkit bytes and SHA-256;
- root:root 0644 polkit metadata;
- direct final-path `.rules` installation;
- exact action ID predicate;
- exact unit predicate;
- exact `restart` verb predicate;
- exact `arivonto` user predicate;
- exact `airiv-sentinel.service` system-unit predicate;
- exact `no_new_privileges === true` predicate;
- `NOT_HANDLED` fallback;
- existing canary rule remains unchanged.

These prove authorization configuration integrity, not live execution
authorization.

## Real Authorization

Real strong authorization evidence requires the trusted safe-pidfd /
systemd D-Bus path.

That future validation is a separate Commander-gated milestone because
it can cause an actual restart effect.

D8.12C MUST NOT perform that effect.

## Runtime State

All production runtime layers remain disabled:

1. D8.10D activation-aware runtime bridge;
2. D8.9D runtime delegation bridge;
3. D8.9C runtime invocation surface;
4. D8.9A execution-dispatch gate.

## Production Policy

Production target allowlist remains empty.

## Failure and Rollback

Any failure after the first host mutation triggers bounded rollback.

Rollback may affect only D8.12C-created artifacts whose hashes still
match the locked design.

Sentinel and canary artifacts must remain untouched.

## Next Gate

A future real D-Bus authorization/restart validation requires a fresh
Commander approval.

D8.12C bootstrap approval does not authorize that effect.
