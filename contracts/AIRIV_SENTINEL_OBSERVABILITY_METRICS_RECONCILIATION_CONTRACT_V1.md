# AIRIV Sentinel Observability Metrics & Reconciliation Contract V1

Status: LOCKED

## Purpose

Define a passive, read-only projection boundary for incident/remediation metrics and reconciliation health. This contract does not grant policy, execution, remediation, verification, restart, lifecycle mutation, or external-delivery authority.

## Canonical inputs

The projection MAY read only already-produced canonical state or immutable snapshots supplied by callers. It MUST NOT call worker start/stop/health/heartbeat methods, execute commands, evaluate remediation policy, resolve incidents, mutate evidence, or trigger recovery.

## Incident projection

The projection MUST preserve lifecycle facts exactly as observed. At minimum it exposes:

- active incident count;
- active lifecycle counts for OPEN / INVESTIGATING / TERMINAL;
- historical terminal count;
- historical final-outcome counts for RECOVERED / UNRESOLVED / ESCALATED / INSUFFICIENT_EVIDENCE;
- explicit unknown/unrecognized values rather than coercing them into a known category.

## Remediation projection

Remediation metrics are accepted only as caller-supplied immutable records or mappings representing already-completed canonical decisions/executions. The projection MAY count records by explicit outcome/status labels. It MUST NOT infer ALLOW/DENY, success/failure, or recovery from missing fields.

## Reconciliation health

Reconciliation is diagnostic only. It reports consistency facts such as:

- active incidents unexpectedly marked TERMINAL;
- history entries not marked TERMINAL;
- history entries missing final outcomes;
- duplicate incident identities across active/history views.

Health values are exactly HEALTHY or DEGRADED. DEGRADED is observational only and MUST NOT trigger remediation or lifecycle changes.

## Determinism and immutability

Given equivalent inputs, projections MUST be deterministic. Returned projections MUST be immutable values and must not expose mutable backing collections.

## Safety boundary

No method in this foundation may import or invoke ExecutionBoundary, RemediationPolicy, CommanderIntentDecider, FinalOutcomeMapper, IncidentManager.resolve(), RuntimeSupervisor.recover(), systemd execution, provider delivery, or host mutation paths.
