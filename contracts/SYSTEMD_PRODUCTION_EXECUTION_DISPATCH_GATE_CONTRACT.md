# AIRIV Sentinel — Production Systemd Execution Dispatch Gate V1

## Phase

2.13D.D8.9A

## Purpose

Define a pure, default-disabled gate between an already prepared
production systemd remediation plan and the downstream canonical
policy/execution integration.

## Input

The gate consumes exactly:

- `PreparedSystemdProductionRemediation`
- explicit dispatch-time `now`

It does not accept raw incident strings, raw evidence, or an
independently constructed target.

## Default

`SystemdProductionExecutionDispatchGate()` is disabled by default.

`SentinelRuntime` must construct the gate in the disabled state.

No runtime loop, daemon, worker, diagnostic coordinator, or scheduler
may automatically invoke the gate in D8.9A.

## Meaning of READY_FOR_POLICY

`READY_FOR_POLICY` means only:

> structural/freshness continuity is valid and this prepared plan may
> be presented to the downstream canonical policy authority.

It does NOT mean:

- remediation ALLOW;
- target allowlisted;
- permit granted;
- execution approved;
- execution started.

`RemediationPolicy` remains the sole ALLOW/DENY authority.

## Freshness

The gate reuses `TrustedSystemdDispatchEvidenceBinding.is_fresh(now)`.

It must not define another freshness algorithm or threshold.

## Prepared-Plan Continuity

The gate must fail closed if a hand-built or substituted prepared
object breaks continuity between:

- trusted evidence snapshot;
- bound plan pre-effect snapshot;
- target fingerprint;
- InvocationID;
- incident ID;
- component ID;
- effect target fingerprint;
- permit-binding/effect identity.

## Authority

D8.9A must not call:

- `RemediationPolicy.evaluate_bound`;
- `RemediationPolicy.evaluate_systemd_production_bound`;
- `production_runtime_guard`;
- `SystemdCommanderIntegration.execute_verified`;
- execution permit claim;
- `ExecutionBoundary`;
- `execute_argv`;
- production attempt persistence;
- production lease acquisition;
- verifier;
- final outcome mapper;
- `IncidentManager.resolve`.

## State

Gate assessment is pure and in-memory.

It must not create or mutate canonical durable state.

## Runtime

`SentinelRuntime` may own exactly one disabled
`SystemdProductionExecutionDispatchGate`.

This is composition only.

D8.9A does not enable it.

## Future Activation

Enabling the live production execution-dispatch path is outside D8.9A.

A later milestone must define the exact controlled delegation into
`SystemdCommanderIntegration.execute_verified()` and must remain
default-disabled until separately authorized.
