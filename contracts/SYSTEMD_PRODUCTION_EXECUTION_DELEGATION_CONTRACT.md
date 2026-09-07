# AIRIV Sentinel — Production Systemd Execution Delegation Contract V1

## Phase

2.13D.D8.9B

## Purpose

Validate the final explicit handoff from a D8.9A
`READY_FOR_POLICY` decision and its exact prepared plan into the
already-existing canonical `SystemdCommanderIntegration`.

This phase is test-only composition validation.

## Runtime Status

The D8.9B delegation boundary MUST NOT be instantiated by
`SentinelRuntime`.

It MUST NOT be called by:

- `SentinelRuntime.run_once`;
- workers;
- scheduler;
- diagnostic coordinator;
- daemon startup;
- automatic incident processing.

The runtime-owned D8.9A gate remains `enabled=False`.

## Input

Delegation requires:

- exact `SystemdCommanderIntegration`;
- exact D8.9A `ProductionExecutionDispatchDecision`;
- exact D8.8B `PreparedSystemdProductionRemediation`;
- incident state;
- post-effect snapshot provider;
- explicit production time;
- optional timeout;
- production attempt facts;
- active production-effect count.

## Mandatory State

The decision must be exactly `READY_FOR_POLICY`.

`BLOCKED` decisions MUST NOT delegate.

## Identity Continuity

Before delegation, exact equality must hold for:

- incident ID;
- component ID;
- execution ID;
- effect fingerprint;
- permit-binding/effect identity.

The trusted evidence binding must still be fresh at the actual
delegation time.

D8.7A.1 remains the freshness authority.

## Sole Delegation

D8.9B may call exactly one downstream authority:

`SystemdCommanderIntegration.execute_verified(...)`

exactly once per explicit `delegate_for_test()` call.

## No Duplicate Authority

D8.9B MUST NOT directly call:

- `RemediationPolicy.evaluate_bound`;
- `RemediationPolicy.evaluate_systemd_production_bound`;
- `production_runtime_guard`;
- permit claim;
- `ExecutionBoundary.execute`;
- `execute_argv`;
- production attempt persistence;
- production lease acquisition;
- verifier;
- final outcome mapper;
- `IncidentManager.resolve`.

Those authorities remain in their canonical existing boundaries.

## Test Safety

Focused tests MUST replace the integration class with a fake and must
not reach real execution, systemctl, polkit, D-Bus, or host mutation.

## Production State

The production target allowlist remains empty.

D8.9B does not enable production execution and does not expand host
authorization.

## Future Work

A later milestone may design a controlled runtime invocation surface.

That future milestone is distinct from this test-only delegation
contract and must remain disabled until separately validated.
