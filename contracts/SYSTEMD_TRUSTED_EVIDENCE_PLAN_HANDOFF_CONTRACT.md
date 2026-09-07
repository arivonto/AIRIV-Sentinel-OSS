# AIRIV Sentinel — Trusted Systemd Evidence to Bound Plan Handoff V1

## Scope

Phase 2.13D.D8.7B owns only the pure construction handoff from an
already validated `TrustedSystemdDispatchEvidenceBinding` to the
existing canonical `BoundSystemdRemediationPlan`.

## Mandatory Input

The public handoff accepts the D8.7A.1 trusted binding.

It does not accept independent raw incident, component, unit, or
evidence strings that could reintroduce evidence substitution.

## Freshness

D8.7A.1 owns freshness semantics.

D8.7B must recheck binding freshness at the explicit caller-supplied
handoff time immediately before constructing bound-plan data.

A binding that expired after its initial validation must fail closed.

No hidden freshness threshold is introduced here.

## Identity Continuity

The canonical pre-effect `SystemdUnitSnapshot` and target identity are
taken directly from the trusted binding's evidence.

The handoff must not reconstruct target identity from incident strings,
aliases, globs, or fuzzy matching.

The canonical resource-bound builder remains responsible for validating
snapshot/scope/effect/permit-binding consistency.

## Privilege Boundary

`SystemdPrivilegeBoundary` is caller-supplied canonical construction
data and validates itself during normal dataclass construction.

D8.7B must not manually invoke its `__post_init__`.

Supplying privilege-boundary data does not grant host authorization.

## Protected Targets

D8.7B may defensively reject structurally protected production targets.

This is not an allowlist decision.

`SystemdProductionTargetPolicy` and `RemediationPolicy` remain the
downstream target-safety and canonical ALLOW/DENY authorities.

## Canonical Plan Construction

D8.7B must reuse:

- `BoundSystemdActionScope`
- `build_bound_systemd_remediation_plan`
- `ResourceBoundPermitBinding` produced by that canonical builder
- existing `BoundSystemdRemediationPlan`

No parallel plan model is permitted.

The exact bound remediation action remains `systemd_restart`.

## Identifier Ownership

`run_id`, `execution_id`, and `permit_id` remain explicit
plan-construction inputs and are validated by existing canonical
constructors.

They must not be derived from evidence fingerprints.

## Authority Separation

D8.7B must not:

- evaluate remediation policy;
- claim a permit;
- execute an effect;
- create/update execution identity;
- write production-attempt records;
- acquire the production-effect lease;
- verify recovery;
- resolve an incident;
- mutate durable evidence;
- automatically dispatch from the daemon.

## Side Effects

Plan construction is in-memory only.

No canonical runtime/evidence filesystem state may be created or
modified by the handoff itself.
