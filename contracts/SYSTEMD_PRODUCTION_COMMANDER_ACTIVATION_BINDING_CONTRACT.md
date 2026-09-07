# AIRIV Sentinel — Commander Consumed Activation Binding Handoff Contract

Phase: D8.19

## Purpose

D8.19 connects the exact durable D8.10B activation-consumption record from the
Commander-only continuation path to the existing D8.10C consumed-activation
to prepared-effect binding authority.

It remains inert and does not execute remediation.

## Sole binding authority

D8.10C remains the sole owner of:

`SystemdProductionConsumedActivationBinding`

and the sole canonical construction function:

`bind_consumed_activation_to_prepared_effect()`

D8.19 MUST NOT construct a competing consumed-activation binding.

It delegates exactly one call to D8.10C.

## Commander-path chronology

Before D8.10C delegation, D8.19 requires:

- canonical D8.16 continuation
- canonical D8.17 activation grant
- canonical D8.18 durable consumption record
- binding time not before continuation time
- consumption not before Commander continuation
- consumption not in the future
- Commander continuation not expired
- activation still active at binding handoff

This prevents an earlier or unrelated durable consumption from being
retroactively attached to a later Commander continuation.

## Exact continuity

Before delegation D8.19 validates:

- approval_id
- activation_id
- incident_id
- component_id
- execution_id
- effect fingerprint
- grant fingerprint
- grant issued_at
- grant expires_at
- prepared effect identity

D8.10C remains authoritative for canonical:

- activation freshness
- grant -> durable consumption continuity
- durable consumption -> prepared-effect continuity
- consumption timestamp validity
- trusted dispatch evidence freshness
- binding construction

## Returned binding

The returned object must be the canonical D8.10C binding and must contain the
exact same:

- grant object
- durable consumption object
- prepared remediation object
- binding timestamp

D8.19 does not perform a competing full D8.10C validation.

## Downstream separation

D8.19 MUST NOT construct:

`SystemdProductionCommanderAuthorizationContext`

Commander authorization remains a later boundary.

D8.19 MUST NOT:

- evaluate RemediationPolicy
- execute remediation
- verify remediation
- mutate Incident lifecycle
- call FinalOutcomeMapper

## Runtime state

D8.19 is intentionally not wired into SentinelRuntime.

Production defaults remain:

- production allowlist EMPTY
- D8.10D activation bridge DISABLED
- D8.9D runtime bridge DISABLED
- D8.9C runtime surface DISABLED
- D8.9A runtime gate DISABLED

No generic production effect is possible through D8.19 alone.
