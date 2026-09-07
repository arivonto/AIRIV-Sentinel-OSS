# AIRIV Sentinel — Consumed Activation to Prepared Effect Binding Contract V1

## Phase

2.13D.D8.10C

## Purpose

Prove exact continuity between:

1. D8.10A immutable activation grant;
2. D8.10B durable single-use consumption record;
3. D8.8B prepared systemd remediation.

D8.10C is a pure binding boundary.

## Required Inputs

The binding requires exact canonical types:

- `SystemdProductionActivationGrant`;
- `SystemdProductionActivationConsumptionRecord`;
- `PreparedSystemdProductionRemediation`;
- explicit finite non-negative binding time.

The prepared object must contain the canonical:

- `TrustedSystemdDispatchEvidenceBinding`;
- `BoundSystemdRemediationPlan`.

## Grant to Durable Consumption Continuity

Exact equality is required for:

- activation ID;
- approval ID;
- incident ID;
- component ID;
- execution ID;
- effect fingerprint;
- grant fingerprint.

No substitution is permitted.

## Consumption Time

The durable consumption timestamp must satisfy:

`issued_at <= consumed_at < expires_at`

It must also satisfy:

`consumed_at <= bound_at`

A future-dated consumption fails closed.

## Activation Freshness

The activation grant must still be active at D8.10C binding time.

Consumption during the original activation window does not create
indefinite authorization after the activation expires.

## Durable Consumption to Prepared Effect Continuity

Exact equality is required for:

- incident ID;
- component ID;
- execution ID;
- effect fingerprint.

The prepared effect is never inferred from text or unit aliases.

## Trusted Evidence Freshness

D8.10C reuses the canonical
`TrustedSystemdDispatchEvidenceBinding.is_fresh(now)` semantic.

It does not create another evidence freshness authority.

## Meaning of Successful Binding

A successful D8.10C binding means only:

> this still-current activation grant was durably consumed exactly once
> and the durable record refers to this exact prepared effect whose
> trusted evidence is still fresh.

It does NOT mean:

- production target policy ALLOW;
- RemediationPolicy ALLOW;
- runtime bridge enabled;
- runtime invocation enabled;
- execution-dispatch gate enabled;
- permit granted;
- host authorization present;
- effect executed.

## Runtime

D8.10C MUST NOT be instantiated automatically by `SentinelRuntime`.

`SentinelRuntime.run_once()` MUST NOT invoke D8.10C.

All existing runtime layers remain disabled.

## Persistence

D8.10C performs no write.

D8.10B remains the sole owner of activation consumption persistence.

## Authority Separation

D8.10C MUST NOT directly call:

- production target policy;
- RemediationPolicy;
- production runtime guard;
- D8.9D runtime delegation bridge;
- D8.9B delegation boundary;
- permit adapter;
- execution boundary;
- verifier;
- final outcome mapper;
- incident resolution.

## Host State

No systemd, polkit, D-Bus, service restart, or other host effect is
permitted.

## Future Work

A later phase may require a current D8.10C binding before an explicitly
controlled runtime delegation path can be opened.

That future activation remains default-disabled and Commander-gated
before any real production host effect.
