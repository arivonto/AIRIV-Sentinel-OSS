# AIRIV Sentinel — Systemd Production Commander Incident Continuation Contract

Phase: D8.16

## Purpose

Define one inert boundary proving that an active systemd incident requiring
Commander action remains exactly continuous with trusted evidence, one
prepared production remediation, and one exact Commander approval.

This phase does not perform runtime execution.

## Lifecycle

IncidentManager remains the sole lifecycle authority.

D8.16 introduces no new lifecycle state.

A continuation is valid only when the canonical incident remains:

OPEN -> INVESTIGATING

and specifically:

- status = INVESTIGATING
- lifecycle_state = INVESTIGATING
- final_outcome = None

A terminal incident cannot be continued.

D8.16 itself never terminalizes an incident.

## Commander intent

The continuation requires:

CommanderIntent.NEED_COMMANDER

It does not convert the incident to AUTONOMOUS_REMEDIATE.

Existing autonomous systemd dispatch behavior remains unchanged.

## Exact bindings

The continuation requires exact continuity of:

- incident_id
- component_id / exact systemd target
- action
- execution_id
- trusted dispatch evidence binding
- prepared production remediation
- permit/effect binding
- approval_id
- approval validity / expiry

Mismatch fails closed.

## Authority boundaries

This continuation is a fact boundary only.

It MUST NOT:

- decide RemediationPolicy ALLOW/DENY
- issue activation
- consume activation
- execute remediation
- verify remediation
- call FinalOutcomeMapper
- call IncidentManager.resolve
- mutate Incident lifecycle

Existing authorities remain unchanged:

- IncidentManager = lifecycle authority
- FinalOutcomeMapper = terminal semantic authority
- RemediationPolicy = sole ALLOW/DENY authority
- D8.14 = durable approval-level single-use issuance
- D8.10A = immutable activation grant
- D8.10B = durable activation consumption
- D8.10C = exact activation/prepared-effect binding
- D8.4 = production safety guard

## Runtime state

D8.16 is intentionally not wired into SentinelRuntime.

Production defaults remain:

- production allowlist EMPTY
- D8.10D activation bridge DISABLED
- D8.9D runtime bridge DISABLED
- D8.9C runtime surface DISABLED
- D8.9A runtime gate DISABLED

D8.16 grants no execution authority.
