# AIRIV Sentinel — Production Systemd Runtime Invocation Contract V1

## Phase

2.13D.D8.9C

## Purpose

Expose a runtime-owned but default-disabled control surface between an
already-prepared production systemd remediation and the D8.9A
execution-dispatch gate.

This phase does **not** connect runtime processing to execution.

## Defense in Depth

Two independent controls remain closed by default:

1. `SystemdProductionRuntimeInvocationBoundary.enabled == False`
2. runtime-owned `SystemdProductionExecutionDispatchGate.enabled == False`

Both must eventually be opened by a later explicitly controlled design
before a plan could reach delegation.

D8.9C opens neither.

## Runtime Composition

`SentinelRuntime` owns one
`SystemdProductionRuntimeInvocationBoundary`.

It must reference the exact same canonical runtime-owned D8.9A gate.

No duplicate execution-dispatch gate is permitted.

## Automatic Runtime Behavior

The following MUST NOT invoke `assess_explicit()`:

- `SentinelRuntime.__init__`;
- `SentinelRuntime.run_once`;
- worker execution;
- scheduler execution;
- diagnostics;
- incident processing;
- daemon startup.

Construction alone is inert.

## Explicit Assessment

When the runtime invocation boundary itself is disabled:

- return `BLOCKED`;
- reason = `production_runtime_invocation_disabled`;
- do not call the D8.9A gate.

When explicitly enabled in isolated tests:

- call the canonical D8.9A gate exactly once;
- propagate BLOCKED if D8.9A blocks;
- return `READY_FOR_DELEGATION` only if D8.9A returns
  `READY_FOR_POLICY`.

## Meaning of READY_FOR_DELEGATION

`READY_FOR_DELEGATION` is routing readiness only.

It does not mean:

- RemediationPolicy ALLOW;
- production target authorization;
- permit granted;
- attempt recorded;
- execution started;
- verification succeeded.

## D8.9B Separation

D8.9C MUST NOT import, instantiate, or call
`SystemdProductionExecutionDelegationBoundary`.

It MUST NOT call `execute_verified()`.

D8.9B remains unwired from runtime.

## Authority Separation

D8.9C MUST NOT directly call:

- remediation policy;
- production target policy;
- production runtime guard;
- execution permit;
- execution boundary;
- production attempt ledger;
- production effect lease;
- verifier;
- final outcome mapper;
- incident resolution.

## Durable State

Assessment is pure and in-memory.

No canonical state may be created or modified.

## Default Production State

Production target allowlist remains empty.

No host authorization expansion occurs.

No systemd service is restarted.

## Future Milestone

A later phase may define a separately controlled bridge from
`READY_FOR_DELEGATION` into the D8.9B canonical delegation boundary.

That phase must remain disabled by default and must not imply
authorization to perform a real production effect.
