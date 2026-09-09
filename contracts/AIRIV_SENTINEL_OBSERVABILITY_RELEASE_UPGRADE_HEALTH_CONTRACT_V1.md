# AIRIV Sentinel Observability Release & Upgrade Health Contract V1

Status: **LOCKED**

## Purpose

Define a passive, read-only observability projection boundary for release readiness, release-artifact validation health, and post-upgrade verification health.

This contract creates no release, deployment, rollback, remediation, verification, or runtime authority. It projects detached facts that were already produced by canonical boundaries.

## Authority boundary

The projection layer MUST NOT:

- invoke `UpgradePreflight` or create an `UpgradePlan`;
- invoke `ReleaseArtifactValidator`;
- invoke `PostUpgradeVerifier`;
- mutate a repository or release artifact;
- deploy, restart, rollback, or execute shell/system-control effects;
- authorize rollback or remediation;
- mutate Incident lifecycle;
- infer authorization from readiness or health values.

Canonical planning, validation, verification, policy, execution, lifecycle, and trusted-host boundaries remain authoritative.

## Input model

Projection functions accept detached mapping snapshots only. Callers are responsible for obtaining those facts from canonical planning, artifact-validation, post-upgrade-verification, evidence, or reporting surfaces.

Unknown, malformed, duplicated, or incomplete values MUST remain observable and MUST NOT be silently promoted to success.

### Release-readiness facts

Each record may provide:

- `release_id` — stable observed identity;
- `status` — exactly `READY` or `NOT_READY`.

Any other or missing status is unknown. Duplicate stable identities are degradation and are not silently deduplicated.

### Artifact-validation facts

Each record may provide:

- `artifact_id` — stable observed identity;
- `status` — exactly `VERIFIED` or `REJECTED`.

Any other or missing status is unknown. `VERIFIED` is observational only and does not imply deployment authorization.

### Post-upgrade-verification facts

Each record may provide:

- `verification_id` — stable observed identity;
- `status` — exactly `VERIFIED`, `FAILED`, or `UNKNOWN`;
- `rollback_authorized` — explicit boolean copied from canonical verification output.

A record is healthy only when status is exactly `VERIFIED`, rollback authorization is explicitly `False`, and the stable identity is present and non-duplicated.

Observed `rollback_authorized=True` is an authority-integrity violation. It is reported as degradation and MUST NOT be treated as permission to execute rollback.

Missing or non-boolean rollback authorization is unknown/incomplete evidence and is also degradation.

## Health semantics

Projection health values are exactly:

- `HEALTHY` — observations exist and all required facts are explicitly successful/consistent;
- `DEGRADED` — any explicit failure, rejection, not-ready state, unknown/incomplete record, duplicate identity, or authority-integrity violation exists;
- `UNKNOWN` — no observations exist.

Health is diagnostic only and MUST NOT trigger remediation, deployment, restart, rollback, provider calls, or lifecycle mutation.

## Required semantics

1. Read-only and side-effect free.
2. Deterministic for identical inputs.
3. Immutable output values.
4. Preserve explicit failure/rejection/not-ready states.
5. Preserve unknown/incomplete states explicitly.
6. Duplicate stable identities are observable degradation, never silently deduplicated.
7. Empty input yields `UNKNOWN`, not synthetic health success.
8. No network, subprocess, filesystem write, provider, policy, execution, lifecycle, validator, verifier, or external-delivery dependency.
9. No projection value grants authority.

## Acceptance gates

- focused projection tests;
- architecture test proving dependency isolation;
- full repository regression;
- public-distribution validation;
- no hidden production effects.

## Non-goals / separately decision-gated

- upgrade execution;
- rollback execution;
- live host deployment effects;
- production SLO enforcement;
- external Commander delivery;
- live AI provider activation;
- automatic remediation from release/readiness health;
- new production targets.
