# AIRIV Sentinel — Commander Semantic Policy Contract V1

## 1. Purpose

This contract defines the authoritative Commander-owned semantic source
for determining:

- remediation_required
- commander_action_required

These facts are consumed by CommanderIntentAssessment and must not be
derived from diagnosis status, remediation policy, action catalog state,
execution, verification, or incident final outcome.

## 2. Canonical Ownership

CommanderSemanticPolicy
        ↓
CommanderIntentAssessment
        ↓
CommanderIntentDecider

Ownership:

remediation_required
    -> CommanderSemanticPolicy

commander_action_required
    -> CommanderSemanticPolicy

remediation_action_available
    -> RemediationActionCatalog

## 3. Boundary

CommanderSemanticPolicy is independent from:

- DiagnosisEvaluator
- RemediationPolicy
- RemediationActionCatalog
- Execution
- Verification
- IncidentManager final outcome

No downstream boundary may become the authoritative source for these
semantic facts.

## 4. Semantic Rule

A semantic rule contains:

- trigger
- remediation_required
- commander_action_required
- reason

The trigger identifies the operational condition for which the Commander
semantic policy applies.

The rule does not contain executable commands.

The rule does not authorize actions.

The rule does not execute actions.

The rule does not verify actions.

The rule does not resolve or terminalize incidents.

## 5. Remediation Action Availability

remediation_action_available remains independently determined by the
RemediationActionCatalog.

Therefore:

- semantic remediation_required MUST NOT imply action availability
- action availability MUST NOT imply remediation_required
- an empty remediation catalog MUST NOT by itself determine CommanderIntent

## 6. Intent Evaluation

CommanderIntentDecider consumes CommanderIntentAssessment.

It does not create semantic facts.

The semantic pipeline is:

Operational context
    ↓
CommanderSemanticPolicy
    ↓
CommanderIntentAssessment
    ↓
CommanderIntentDecider
    ↓
CommanderIntent

## 7. Safety Boundary

CommanderSemanticPolicy MUST fail closed when the required semantic policy
is not explicitly configured.

Unconfigured semantic policy MUST NOT silently produce
AUTONOMOUS_REMEDIATE.

Such a condition requires the Commander path to remain non-autonomous
until an explicit semantic rule exists.

## 8. Separation of Concerns

Diagnosis establishes whether the available evidence supports a diagnosis.

CommanderSemanticPolicy establishes what semantic response requirements
apply to that diagnosed condition.

CommanderIntentDecider determines the resulting Commander intent.

Authorization remains owned by the existing remediation policy boundary.

Execution remains owned by the existing execution boundary.

Verification remains owned by the existing verification boundary.

Incident final outcome remains owned by IncidentManager.

## 9. Production Activation

Creation of CommanderSemanticPolicy does not activate production
remediation.

Production RemediationActionCatalog remains empty until the complete
Commander intent → authorization → execution → verification → outcome
loop is validated and explicitly activated.

## 10. Implementation Gate

Before production wiring:

1. CommanderSemanticPolicy API is implemented.
2. Semantic rules are explicitly testable.
3. remediation_required ownership is verified.
4. commander_action_required ownership is verified.
5. remediation_action_available remains independent.
6. Unknown/unconfigured policy is fail-closed.
7. CommanderIntentDecider consumes assessment only.
8. Existing locked boundaries remain unchanged.
9. Focused intent tests pass.
10. Full regression passes.
11. No production remediation action is activated.

