# AIRIV Sentinel Observability Attention, Delivery & AI Health Contract V1

Status: **LOCKED**

## Purpose

Extend the read-only observability foundation with deterministic projections for Commander attention backlog, delivery health, and AI execution identity/verifier health.

This contract does not create runtime authority. It only projects already-observed facts.

## Authority boundary

The projection layer MUST NOT:

- invoke Commander orchestration;
- authorize or execute remediation;
- mutate Incident lifecycle;
- invoke AI providers or agent execution;
- invoke result verification;
- deliver external messages;
- restart services or alter deployment state;
- infer authorization from health or backlog values.

Canonical execution, policy, lifecycle, verification, and delivery boundaries remain authoritative.

## Input model

Projection functions accept detached mapping snapshots only. Callers are responsible for obtaining those facts from canonical evidence/runtime surfaces.

Unknown, malformed, or incomplete values MUST remain explicit and MUST NOT be silently promoted to success.

### Commander attention facts

Each record may provide:

- `attention_id` — stable observed identity;
- `requires_attention` — explicit boolean;
- `resolved` — explicit boolean.

A record counts as pending only when `requires_attention is True` and `resolved is False`.

### Delivery facts

Each record may provide:

- `delivery_id` — stable observed identity;
- `status` — exactly `PENDING`, `DELIVERED`, or `FAILED`.

Any other/missing status is `UNKNOWN`.

Delivery projection health is `DEGRADED` when failed, unknown, or duplicate identities exist; otherwise `HEALTHY`.

### AI execution health facts

Each record may provide:

- `execution_id` — stable observed identity;
- `identity_status` — exactly `PRESENT`, `MISSING`, or `UNKNOWN`;
- `verification_status` — exactly `VERIFIED`, `FAILED`, or `UNKNOWN`.

A record is healthy only when identity is explicitly `PRESENT` and verification is explicitly `VERIFIED`.

AI execution projection health is `DEGRADED` when identity is missing, verification failed, unknown facts exist, or duplicate execution identities exist; otherwise `HEALTHY`.

## Required semantics

1. Read-only and side-effect free.
2. Deterministic for identical inputs.
3. Immutable output values.
4. Preserve input order for reported pending identities.
5. Preserve unknown/incomplete states explicitly.
6. Duplicate stable identities are observable degradation, never silently deduplicated.
7. Empty input yields zero counts and `HEALTHY` health for delivery/AI projections because no failing observation exists.
8. No network, subprocess, filesystem write, provider, policy, execution, lifecycle, verifier, or external-delivery dependency.

## Acceptance gates

- focused projection tests;
- architecture test proving dependency isolation;
- full repository regression;
- public-distribution validation;
- no hidden production effects.

## Non-goals / separately decision-gated

- external Commander delivery;
- live AI provider activation;
- automatic remediation from backlog/health thresholds;
- production SLO enforcement;
- new production targets;
- rollback execution.
