# AIRIV Sentinel — Production Runtime Delegation Bridge Contract V1

## Phase

2.13D.D8.9D

## Purpose

Define the explicit bridge from the D8.9C runtime invocation surface to
the already-locked D8.9B delegation boundary.

This milestone validates composition only.

## Default State

The runtime-owned bridge MUST be disabled by default.

The existing runtime-owned layers also remain disabled:

1. D8.9D runtime delegation bridge
2. D8.9C runtime invocation surface
3. D8.9A execution-dispatch gate

Production target allowlist remains empty.

## Runtime Ownership

`SentinelRuntime` may own one
`SystemdProductionRuntimeDelegationBridge`.

The bridge MUST reference the exact runtime-owned D8.9C invocation
surface.

The runtime MUST NOT store or automatically instantiate a D8.9B
delegation boundary inside the bridge.

The runtime bridge MUST NOT store an execution integration.

Both are explicit arguments to the invocation API.

## Disabled Behavior

When D8.9D is disabled:

- return BLOCKED;
- do not call D8.9C;
- do not inspect a delegation boundary;
- do not inspect an integration;
- perform no downstream work.

## Explicit Enabled Behavior

Only isolated tests may exercise the enabled branch in D8.9D.

When enabled:

1. call D8.9C `assess_explicit()` exactly once;
2. if D8.9C blocks, return BLOCKED and do not delegate;
3. require a non-null D8.9A dispatch decision marked READY_FOR_POLICY;
4. call D8.9B `delegate_for_test()` exactly once.

## Authority Separation

D8.9D owns routing only.

It MUST NOT directly call:

- remediation policy;
- production target policy;
- production runtime guard;
- permit claim;
- execution boundary;
- verifier;
- final outcome mapper;
- incident resolution.

The sole downstream delegation API is the already-locked D8.9B
boundary.

## Runtime Automation

`SentinelRuntime.__init__` may construct the disabled bridge.

`SentinelRuntime.run_once()` MUST NOT call it.

Workers, diagnostics, scheduler and daemon startup MUST NOT call it.

## Testing Safety

All tests that exercise successful delegation MUST replace D8.9B and
the integration with fakes.

No focused D8.9D test may invoke a real command, systemctl, D-Bus,
polkit, permit, attempt ledger, production lease or verifier.

## Host Authorization

D8.9D does not modify polkit or any unit file.

It does not expand production targets.

## Future Work

A later phase may define a controlled activation contract for the
runtime layers.

Actual host-affecting production activation is outside this contract
and requires a separate Commander authorization gate.
