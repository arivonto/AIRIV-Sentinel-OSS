# AIRIV Sentinel — Live Remediation Safety Boundary Contract

Status: Phase 2.13C.1 safety repair.

This contract extends the existing remediation safety envelope without
moving any locked authority.

## 1. Authority Preservation

The canonical authority chain remains:

Observation
→ Investigation
→ Diagnosis
→ CommanderSemanticPolicy
→ CommanderIntentAssessment
→ CommanderIntentDecider
→ RemediationPolicy
→ RemediationActionCatalog
→ ExecutionBoundary
→ Verification
→ FinalOutcomeMapper
→ IncidentManager.resolve()

No authority in this contract may duplicate or replace those boundaries.

## 2. Live Target Identity

`pane_id` alone is insufficient for live remediation.

A live-safe TMUX target must carry an immutable enrolled identity containing
at least:

- validation run identity
- explicit TMUX server endpoint
- TMUX server generation identity when available
- session native identity
- exact session name
- window native identity
- pane native identity

Display names, indexes, or pane IDs alone are insufficient.

Legacy observations lacking strong identity remain valid historical evidence
but are not eligible for live remediation.

## 3. Resource-Specific Authorization

Live remediation authorization must bind:

- incident identity
- component identity
- target identity
- action
- effect specification
- execution identity / permit identity

Authorization for one target must never authorize another target.

Missing or mismatched target identity fails closed.

## 4. Immutable Effect Binding

The effect actually executed must be the same effect authorized.

Post-authorization substitution of any of these is prohibited:

- incident
- component
- target
- action
- executable
- argv

Catalog ownership of action/effect remains unchanged.

## 5. Execution Model

Live-safe actions must use typed argv execution.

Live-safe actions must not use:

- shell=True
- free-form shell interpolation
- unbounded subprocess execution

Execution must have an explicit timeout.

Existing legacy string execution may remain for compatibility but is not
automatically live-remediation eligible.

## 6. One-Run Rule

One controlled authorization permits at most one external effect.

Durable execution identity must be claimed before the effect.

Replay, concurrent calls, crash recovery, and retry must not generate a
second external effect for the same controlled authorization.

## 7. Verification

Execution success is not recovery.

Live TMUX verification must independently verify the exact enrolled target.

Verification must check, where applicable:

- explicit TMUX server endpoint
- exact session identity
- exact session name
- exact window identity
- exact pane identity
- expected pane liveness

Verification is bounded by timeout.

Timeout, malformed data, missing identity, command failure, or identity
mismatch fails verification.

Only FinalOutcomeMapper may map successful execution + successful verification
to RECOVERED.

## 8. Production Defaults

Fresh production composition must contain:

- no semantic remediation rules
- no remediation catalog actions
- no remediation catalog trigger mappings
- no default remediation-policy action allowance

Temporary controlled configuration must be instance-local and removable.

## 9. Host Safety

Phase 2.13C.1 does not authorize:

- live remediation
- systemd mutation
- service restart
- reboot/shutdown
- sudo host mutation
- network changes
- SSH changes
- unrelated TMUX actions

