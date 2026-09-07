# AIRIV Sentinel — Commander Authorization Context Handoff Contract

Phase: D8.20

## Purpose

D8.20 composes the exact Commander-only path through D8.19 with the existing
D8.15 `SystemdProductionCommanderAuthorizationContext`.

It is an inert authorization-fact handoff.

It does not evaluate policy and cannot execute remediation.

## Canonical authorization fact

D8.15 remains the sole owner of:

`SystemdProductionCommanderAuthorizationContext`

D8.20 delegates exactly one context-construction request to that existing
type.

D8.20 MUST NOT construct a competing trusted Commander approval.

## Inputs

D8.20 requires exact canonical objects:

- D8.16 `SystemdProductionCommanderIncidentContinuation`
- D8.19 `SystemdProductionConsumedActivationBinding`
- D8.14 `SystemdProductionCommanderApprovalIssuer`
- D8.10B `SystemdProductionActivationConsumptionStore`

The issuer and consumption store are supplied as canonical durable ledger
owners, not as authorities for D8.20 to invoke directly.

D8.20 MUST NOT call:

- `issuer.issue()`
- `issuer.records()`
- `consumption_store.consume()`
- `consumption_store.records()`

Those storage reads belong to the D8.15 context constructor.

## Commander-path continuity

Before context construction D8.20 validates:

- canonical D8.16 continuation
- exact prepared object identity
- approval_id continuity
- incident_id continuity
- component_id continuity
- execution_id continuity
- consumption not before Commander continuation
- consumption not after D8.19 binding
- binding not before Commander continuation
- binding before Commander approval expiry
- grant approval_id equals Commander approval
- grant issued_at equals Commander approval
- grant expires_at equals Commander approval

## Durable evidence authority

D8.15 remains responsible for proving:

- exact durable D8.14 issuance record exists
- exact durable D8.10B consumption record exists
- D8.10C binding is canonical
- reconstructed trusted approval is exact
- authorization binding is current and internally consistent at binding time

D8.20 MUST NOT duplicate those ledger reads.

## Returned context

The result must be the canonical D8.15 context.

D8.20 validates only handoff identity:

- exact D8.19 binding object
- approval_id
- effect
- issued_at
- expires_at

## Policy separation

The authorization context is an input fact only.

D8.20 MUST NOT call:

- `RemediationPolicy.evaluate_systemd_production_bound()`
- any other ALLOW/DENY evaluation
- `context.matches()`

Policy remains the sole ALLOW/DENY authority.

## Execution separation

D8.20 MUST NOT:

- execute remediation
- verify remediation
- mutate Incident lifecycle
- map FinalOutcome

## Runtime state

D8.20 is intentionally not wired into SentinelRuntime.

Production defaults remain:

- production allowlist EMPTY
- D8.10D activation bridge DISABLED
- D8.9D runtime bridge DISABLED
- D8.9C runtime surface DISABLED
- D8.9A runtime gate DISABLED

No generic production effect is possible through D8.20 alone.
