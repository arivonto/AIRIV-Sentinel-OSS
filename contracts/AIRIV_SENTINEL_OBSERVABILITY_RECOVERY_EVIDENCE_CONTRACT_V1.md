# AIRIV Sentinel Observability Recovery Evidence Contract V1

Status: **LOCKED**

## Purpose

Define deterministic, read-only recovery evidence projection for synthetic/non-production failure scenarios without creating fault-injection, remediation, restart, rollback, policy, execution, verification, or Incident-lifecycle authority.

This foundation observes caller-supplied detached facts describing a scenario. It does not cause the failure, perform recovery, invoke a verifier, or mutate any runtime state.

## Authority boundary

The recovery evidence projection MUST NOT:

- inject faults into production or non-production systems;
- invoke subprocesses, shells, systemd, network clients, providers, or external services;
- authorize or execute remediation, restart, deployment, upgrade, or rollback;
- call `RemediationPolicy`, `ExecutionBoundary`, or any effect-bearing adapter;
- invoke independent verification itself;
- mutate `IncidentManager` or any Incident lifecycle state;
- infer effect authority from a successful synthetic scenario;
- auto-retry failed, incomplete, or indeterminate scenarios.

A scenario result is diagnostic evidence only.

## Input model

Projection accepts detached mapping snapshots. A record may provide:

- `scenario_id` — stable scenario identity;
- `failure_class` — symbolic failure classification;
- `injection_scope` — exactly `SYNTHETIC` or `NON_PRODUCTION` for foundation-eligible scenarios;
- `before_state` — symbolic observed state before the synthetic failure;
- `failure_state` — symbolic state while the failure is observed;
- `after_state` — symbolic state after the external recovery attempt or test transition;
- `expected_recovery_state` — symbolic expected post-recovery state;
- `verification_status` — exactly `VERIFIED`, `FAILED`, or `UNKNOWN`;
- `effect_attempted` — explicit boolean proving whether this projection/test path attempted an effect. Foundation-safe records require `False`.

State and identity values are bounded symbolic metadata only. Raw commands, credentials, prompts, unrestricted provider output, host-private topology, and arbitrary evidence payloads are outside this projection surface.

## Recovery classification

### `RECOVERED`

A record may be classified `RECOVERED` only when all required symbolic facts are present, the scope is explicitly `SYNTHETIC` or `NON_PRODUCTION`, `effect_attempted is False`, the failure observation is distinct from the before observation, `verification_status == VERIFIED`, and `after_state == expected_recovery_state`.

### `NOT_RECOVERED`

A fully specified foundation-safe record is `NOT_RECOVERED` when independent verification explicitly failed, or when verification is `VERIFIED` but `after_state != expected_recovery_state`.

### `UNKNOWN`

Missing, malformed, ambiguous, unsupported, production-scoped, effect-attempting, or explicitly `UNKNOWN` verification facts remain `UNKNOWN`. They MUST NOT be converted into `RECOVERED` or used as authority.

## Integrity violations

The projection reports, but never executes around, the following integrity violations:

- duplicate stable `scenario_id` values;
- explicit `PRODUCTION` or other non-foundation injection scope;
- `effect_attempted is True`.

Integrity violations degrade aggregate health and prevent the affected record from being classified as recovered.

## Aggregate health

- empty observation set: `UNKNOWN`;
- one or more records with any `NOT_RECOVERED`, `UNKNOWN`, duplicate identity, scope violation, or effect-attempt violation: `DEGRADED`;
- otherwise: `HEALTHY`.

Aggregate health is observability state, never policy or remediation permission.

## Required semantics

1. Read-only and side-effect free.
2. Deterministic for identical normalized inputs.
3. Immutable projection outputs.
4. Preserve scenario input order in per-scenario results.
5. Preserve unknown/incomplete facts explicitly.
6. Successful state matching without explicit `VERIFIED` evidence is not recovery proof.
7. A synthetic success grants no production authority.
8. No filesystem write, subprocess, shell, systemd, network, provider, remediation-policy, execution, verifier, or Incident-lifecycle dependency.
9. CI/tests MUST NOT inject production faults or mutate external production state.

## Acceptance gates

- focused recovery evidence behavior tests;
- architecture dependency-isolation test;
- deterministic/immutability tests;
- explicit production-scope/effect-attempt fail-closed tests;
- full canonical regression;
- curated public distribution validation;
- no hidden production effects.

## Non-goals / separately decision-gated

This contract does not authorize:

- production fault injection;
- automatic restart or remediation;
- recovery execution;
- rollback execution;
- live AI-provider activation;
- external Commander delivery;
- new production targets;
- SLO enforcement.
