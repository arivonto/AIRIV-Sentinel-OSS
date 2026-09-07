# AIRIV Sentinel — Remediation Verification Contract V1

## 1. Purpose

This contract defines the canonical boundary for independently verifying
post-remediation system state.

Execution success MUST NOT be treated as remediation success.

A remediation is considered verified only when an independent observation
confirms the expected post-remediation state.

## 2. Authority

This contract operates below:

1. AIRIV_SENTINEL_MISSION_CONTRACT_V1
2. AIRIV_SENTINEL_SYSTEMD_CONTRACT_V1
3. AIRIV_SENTINEL_EXECUTION_CONTRACT_V1
4. AIRIV_SENTINEL_REMEDIATION_POLICY_CONTRACT_V1

The IncidentManager remains the sole authority for incident lifecycle.

Verification MUST NOT resolve an Incident.

## 3. Verification Boundary

Canonical flow:

Execution
    ->
Post-Remediation Observation
    ->
Verification
    ->
VerificationResult
    ->
Evidence

The verifier MUST be independent from the command execution result.

## 4. Verification Outcomes

The canonical verification outcomes are:

### VERIFIED

The expected post-remediation state was independently observed.

### VERIFICATION_FAILED

Execution occurred, but the expected post-remediation state was not
confirmed.

### UNVERIFIED

Execution occurred, but no valid post-remediation verification was
performed.

### VERIFICATION_ERROR

Verification could not be completed because the verification operation
failed.

## 5. Execution vs Verification

The following states are distinct:

- execution success != remediation success
- execution failure != verified recovery
- verification success requires independent observation
- verification failure MUST remain observable

An execution command returning exit code 0 MUST NOT by itself produce a
verified remediation outcome.

## 6. Evidence

Every remediation verification attempt MUST remain observable through the
canonical evidence flow.

Evidence SHOULD preserve:

- execution result
- verification outcome
- verification reason
- post-remediation observation
- incident identity
- component identity

Evidence MUST NOT be silently deleted or rewritten.

## 7. Incident Lifecycle

Verification MUST NOT mutate incident lifecycle state.

In particular:

VERIFIED
    !=
RESOLVED

Only the canonical IncidentManager MAY transition an incident to RESOLVED,
and explicit recovery evidence remains required.

## 8. Failure Handling

If verification fails:

1. The failure MUST be recorded.
2. The incident MUST remain active.
3. Sentinel MUST NOT claim successful recovery.
4. Further remediation MAY be considered according to remediation policy.
5. Escalation remains governed by the applicable incident authority.

## 9. Verification Authority

The verifier MAY inspect system state, but MUST NOT:

- execute remediation;
- bypass the execution gate;
- modify incident lifecycle;
- fabricate observations;
- convert execution success into verification success;
- conceal verification failure.

## 10. Tmux V1 Direction

For the initial Sentinel implementation, tmux state is the preferred
observable system state because tmux is already part of the canonical
sensor pipeline.

Tmux-specific verification MUST validate actual observed state rather
than assume that a remediation command succeeded.

## 11. Contract Status

Status: LOCKED — V1

This contract establishes the verification boundary.
Implementation details MAY evolve only while remaining conformant to
this contract and higher-priority Sentinel contracts.
