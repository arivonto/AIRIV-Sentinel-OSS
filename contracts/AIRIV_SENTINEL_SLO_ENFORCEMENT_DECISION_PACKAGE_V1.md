# AIRIV Sentinel SLO Enforcement Decision Package V1

Status: **DECISION PACKAGE / NON-EXECUTABLE**

## Purpose

Define the Commander decision record required before any future AIRIV Sentinel SLO enforcement work may begin.

This package is deliberately non-executable. It records what must be decided, evidenced, and bounded before enforcement is designed. It does not authorize enforcement, alerting, throttling, remediation, restart, deployment, rollback, live provider activation, production fault injection, or Incident lifecycle mutation.

## Current authority state

SLO enforcement is **NOT AUTHORIZED**.

The current completed foundation may only project caller-supplied detached resource measurements, trust/stability evidence, and non-enforcing SLO definition records. Those projections are descriptive evidence surfaces. They are not policy, permission, breach detection, alert generation, or execution authority.

## Commander decision record

A future SLO enforcement decision must be explicit and must identify:

- `decision_id` — stable Commander decision identity;
- `decided_at` — durable decision timestamp;
- `commander_identity` — approved Commander authority identity;
- `approved_scope_id` — bounded Sentinel scope covered by the decision;
- `slo_definition_ids` — exact detached SLO definitions under review;
- `measurement_source_ids` — exact measurement sources permitted for evaluation;
- `trust_requirements` — required source trust/stability facts before evaluation;
- `evaluation_window` — bounded observation window and freshness semantics;
- `enforcement_mode` — one of `REPORT_ONLY`, `COMMANDER_CONFIRM`, or `AUTONOMOUS_BOUNDED`;
- `allowed_consequences` — exact allowed outputs/effects for the selected mode;
- `blast_radius` — exact maximum affected target set;
- `cooldown` — minimum interval between consequential attempts;
- `retry_budget` — maximum retries and ambiguity handling;
- `verification_requirements` — independent post-effect verification, if effects are authorized;
- `rollback_position` — explicit statement that rollback execution is not implied;
- `production_activation_gate` — separate live-host activation requirement;
- `expiration` — durable expiry or review requirement.

Missing, ambiguous, contradictory, stale, or non-durable decision facts must fail closed.

## Enforcement-mode meanings

### `REPORT_ONLY`

May allow future code to classify SLO observations for reporting only. It does not authorize alerts outside existing non-authoritative delivery surfaces, throttling, restart, remediation, rollback, deployment, or lifecycle mutation.

### `COMMANDER_CONFIRM`

May allow future code to prepare a proposed consequence for explicit Commander confirmation. It does not execute the consequence and does not convert observation evidence into permission.

### `AUTONOMOUS_BOUNDED`

Requires a separate effect-capable contract before implementation. The contract must bind exact target identity, action identity, evidence continuity, replay protection, cooldown, retry budget, blast radius, independent verification, and terminal `UNKNOWN` semantics. This package alone does not authorize autonomous enforcement.

## Required preconditions for any future enforcement design

1. Non-enforcing SLO definitions are integrated in canonical `main`.
2. Measurement trust/stability facts are integrated and treated as evidence quality only.
3. The Commander decision record exists with all required fields.
4. The selected enforcement mode is explicit.
5. The allowed consequences are exact and bounded.
6. Production activation is separately approved if production state may be affected.
7. CI and repository tests prove no hidden host polling, provider call, remediation, lifecycle mutation, restart, deployment, rollback, or branch-governance assumption.
8. The design includes independent verification before any terminal success claim for side effects.

## Explicit non-authorizations

This package does not authorize:

- reading live host metrics;
- evaluating current production health;
- detecting or declaring SLO breaches in production;
- creating external alerts;
- throttling work;
- executing remediation;
- restarting services;
- deploying or upgrading software;
- executing rollback;
- calling live AI providers;
- mutating Incident lifecycle state;
- configuring GitHub branch protection;
- bypassing CI or repository governance.

## Acceptance gates for this package

- contract text records `DECISION PACKAGE / NON-EXECUTABLE`;
- roadmap records SLO enforcement as still separately decision-gated;
- status registry records this package without promoting enforcement authority;
- tests assert the package contains required decision fields and explicit non-authorizations;
- project documentation validation passes;
- full regression passes before integration.
