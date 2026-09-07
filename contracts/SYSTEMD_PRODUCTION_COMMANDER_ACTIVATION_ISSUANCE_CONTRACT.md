# AIRIV Sentinel — Commander Continuation to Activation Issuance Contract

Phase: D8.17

## Purpose

D8.17 connects the inert D8.16 Commander-only incident continuation fact to
the existing D8.14 durable approval issuer.

It introduces no new activation authority.

## Sole activation issuance authority

D8.14 `SystemdProductionCommanderApprovalIssuer.issue()` remains the sole:

- approval-level durable single-use reservation authority
- durable issuance record authority
- production `SystemdProductionActivationGrant` construction path

D8.17 MUST NOT construct `SystemdProductionActivationGrant` directly.

It delegates exactly one issuance request to D8.14.

## Input

D8.17 requires:

- canonical D8.16 `SystemdProductionCommanderIncidentContinuation`
- canonical D8.14 `SystemdProductionCommanderApprovalIssuer`
- activation_id
- current time

The D8.16 continuation is revalidated before durable issuance.

## Temporal continuity

Issuance is rejected when:

- now precedes continuation time
- continuation approval has expired
- D8.14 rejects the approval as inactive

D8.14 remains authoritative for approval validity and durable issuance.

## Returned grant continuity

The exact D8.14 grant must match:

- requested activation_id
- approval_id
- incident_id
- component_id
- execution_id
- effect fingerprint
- approval issued_at
- approval expires_at

Mismatch fails closed.

## Ownership boundaries

D8.17 does NOT:

- decide RemediationPolicy ALLOW/DENY
- create activation grants itself
- consume activation
- bind consumed activation
- create Commander authorization context
- execute remediation
- verify remediation
- mutate incident lifecycle
- call FinalOutcomeMapper

Existing ownership remains:

- D8.14: durable approval issuance + grant construction
- D8.10A: activation-grant semantics
- D8.10B: durable activation consumption
- D8.10C: consumed activation to prepared-effect binding
- D8.15: Commander-only policy authorization semantics
- D8.16: approved incident continuation fact
- RemediationPolicy: sole ALLOW/DENY authority
- IncidentManager: sole lifecycle authority

## Runtime state

D8.17 is intentionally not wired into SentinelRuntime.

Production defaults remain:

- production allowlist EMPTY
- D8.10D activation bridge DISABLED
- D8.9D runtime bridge DISABLED
- D8.9C runtime surface DISABLED
- D8.9A runtime gate DISABLED

No production effect is possible through D8.17 alone.
