# AIRIV Sentinel SLO Report-Only Authority Contract V1

Status: **IMPLEMENTED / NON-EXECUTABLE**

## Purpose

Define the narrow authority record for classifying caller-supplied detached SLO
evidence into reporting projections. This contract authorizes no host polling,
production health evaluation, alert delivery, throttling, remediation,
restart, deployment, rollback, provider call, or Incident lifecycle mutation.

## Authority record

The record MUST contain durable values for `decision_id`, `decided_at`,
`commander_identity`, `approved_scope_id`, `slo_definition_ids`,
`measurement_source_ids`, `trust_requirements`, `evaluation_window`,
`enforcement_mode`, `allowed_consequences`, `blast_radius`, `cooldown`,
`retry_budget`, `verification_requirements`, `rollback_position`,
`production_activation_gate`, and `expiration`.

For this contract, `enforcement_mode` MUST be `REPORT_ONLY` and
`allowed_consequences` MUST be exactly `report_projection`. Empty definition
or source lists are valid when the decision is only establishing the passive
scope; they do not authorize evaluation of unspecified data.

## Fail-closed validation

Missing, blank, malformed, expired, contradictory, or non-durable fields MUST
be rejected. The validator MUST reject any mode other than `REPORT_ONLY` and
any consequence other than `report_projection`. Validation is a pure local
operation and has no runtime or production side effect.

## Explicit non-authorizations

This contract does not authorize live metric acquisition, breach detection,
external alerting, throttling, remediation, service restart, deployment,
upgrade, rollback, AI provider access, production activation, or lifecycle
mutation.
