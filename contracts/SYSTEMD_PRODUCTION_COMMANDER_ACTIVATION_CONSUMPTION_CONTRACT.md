# AIRIV Sentinel — Commander Activation Consumption Handoff Contract

Phase: D8.18

## Purpose

D8.18 connects the exact activation grant produced through the Commander-only
continuation path to the existing D8.10B durable single-use activation
consumption boundary.

D8.18 is an inert handoff boundary. It does not execute remediation.

## Irreversible boundary

D8.10B remains the sole durable activation-consumption authority.

The canonical consumption operation is:

`SystemdProductionActivationConsumptionStore.consume()`

D8.18 delegates exactly one call to this operation.

D8.10B owns:

- activation eligibility assessment
- exact effect matching
- durable activation-ID single-use namespace
- O_EXCL reservation
- fail-closed replay denial
- crash-safe conservative consumption
- durable consumption-record construction and persistence

Once D8.10B has successfully claimed its durable reservation, a crash is
treated conservatively as activation consumed.

D8.18 MUST NOT attempt recovery, reuse, rollback, or reissue that activation.

## Upstream continuity

Before consumption, D8.18 revalidates:

- canonical D8.16 continuation
- canonical D8.17 activation grant
- continuation timestamp monotonicity
- approval / continuation expiry
- grant active window
- approval_id
- incident_id
- component_id
- execution_id
- effect fingerprint
- grant issued_at
- grant expires_at

Mismatch fails before irreversible consumption.

## Returned durable record continuity

The canonical D8.10B record is revalidated against the grant for:

- activation_id
- approval_id
- incident_id
- component_id
- execution_id
- effect fingerprint
- grant fingerprint
- consumed_at

D8.18 does not construct a competing consumption record.

## D8.10C separation

D8.18 ends after durable D8.10B consumption.

It MUST NOT call:

`bind_consumed_activation_to_prepared_effect()`

D8.10C remains the sole owner of consumed-activation to prepared-effect
binding.

## Other authority boundaries

D8.18 MUST NOT:

- evaluate RemediationPolicy
- create Commander authorization context
- execute remediation
- verify remediation
- mutate Incident lifecycle
- call FinalOutcomeMapper

Existing ownership remains unchanged.

## Runtime state

D8.18 is intentionally not wired into SentinelRuntime.

Production defaults remain:

- production allowlist EMPTY
- D8.10D activation bridge DISABLED
- D8.9D runtime bridge DISABLED
- D8.9C runtime surface DISABLED
- D8.9A runtime gate DISABLED

No generic production effect is possible through D8.18 alone.
