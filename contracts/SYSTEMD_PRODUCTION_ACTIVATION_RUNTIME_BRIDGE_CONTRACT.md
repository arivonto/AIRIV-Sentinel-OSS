# AIRIV Sentinel — Activation-Aware Runtime Bridge Contract V1

## Phase

2.13D.D8.10D

## Purpose

Add one final default-disabled runtime routing layer that requires a
current D8.10C consumed-activation binding before an explicit caller
could reach the already-locked D8.9D runtime delegation bridge.

This phase validates composition only.

## Runtime Layers

The production runtime now contains four independently fail-closed
layers:

1. D8.10D activation-aware runtime bridge;
2. D8.9D runtime delegation bridge;
3. D8.9C runtime invocation surface;
4. D8.9A execution-dispatch gate.

All four MUST be disabled by default.

## Canonical Activation Input

D8.10D accepts one exact:

`SystemdProductionConsumedActivationBinding`

It MUST NOT accept a separate prepared remediation argument.

The prepared effect used downstream MUST be:

`activation_binding.prepared`

This prevents prepared-effect substitution after D8.10C validation.

## Current Binding Requirement

Immediately before routing downstream, D8.10D must call:

`activation_binding.is_current(production_now)`

exactly once.

If false, routing stops.

A consumed activation is not indefinitely usable after activation or
trusted-evidence expiry.

## Disabled Behavior

If D8.10D is disabled:

- return BLOCKED;
- do not inspect the activation binding;
- do not call D8.9D;
- do not inspect delegation or integration;
- perform no durable operation.

## Enabled Test Behavior

Only isolated fake-downstream tests may exercise the enabled branch.

If enabled and the binding is current, D8.10D may invoke the existing
D8.9D bridge exactly once.

## No Activation Persistence

D8.10D MUST NOT:

- create activation grants;
- consume activation grants;
- query or modify the D8.10B durable store;
- delete consumption records.

D8.10B remains the sole persistence authority.

## Authority Separation

D8.10D MUST NOT directly call:

- production target policy;
- RemediationPolicy;
- production runtime guard;
- D8.9B delegation;
- permit adapter;
- execution boundary;
- verifier;
- final outcome mapper;
- incident resolution.

Its sole downstream route is D8.9D.

## Runtime Composition

`SentinelRuntime` may own one D8.10D bridge.

It must reference the exact runtime-owned D8.9D bridge.

The D8.10D instance must use `enabled=False`.

## Automatic Runtime Behavior

`SentinelRuntime.run_once()` MUST NOT call D8.10D.

No worker, scheduler, diagnostic path, or daemon startup path may call
D8.10D.

## Production Policy

Production target allowlist remains empty.

D8.10D does not change policy configuration.

## Testing

Any D8.10D test that exercises downstream routing MUST replace D8.9D,
delegation, and integration objects with fakes.

No test may reach real execution.

## Host State

No systemd command, D-Bus operation, polkit change, unit restart, or
other host effect is permitted.

## Activation Gate

Implementation and repository testing of this disabled boundary require
no Commander approval.

Any future change that enables the runtime layers or allows an actual
production host effect requires a fresh explicit Commander gate.
