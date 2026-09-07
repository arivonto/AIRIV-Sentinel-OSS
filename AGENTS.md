# AIRIV Sentinel — Engineering Guide

## Purpose

This file defines repository-level engineering expectations for humans and coding agents working on AIRIV Sentinel.

## Canonical authority

The normative architecture and safety rules live under `contracts/`. If implementation, tests, local preference, or generated guidance conflicts with a canonical contract, stop and resolve the conflict explicitly.

**Contract > Implementation > Local Preference**

## Locked architectural pipeline

```text
Observation
→ Investigation
→ Diagnosis
→ CommanderSemanticPolicy
→ CommanderIntentAssessment
→ CommanderIntentDecider
→ RemediationPolicy
→ RemediationActionCatalog
→ Execution
→ Verification
→ FinalOutcomeMapper
→ IncidentManager.resolve()
```

## Authority boundaries

- Investigation owns incident investigation lifecycle.
- DiagnosisEvaluator owns Diagnosis.
- CommanderSemanticPolicy exclusively owns semantic remediation facts.
- CommanderIntentDecider owns CommanderIntent.
- RemediationPolicy is the sole canonical remediation ALLOW/DENY authority.
- RemediationActionCatalog owns action availability and command metadata only.
- ExecutionBoundary is the sole command executor.
- Verification independently verifies remediation effects.
- FinalOutcomeMapper is the sole final-outcome mapper.
- IncidentManager.resolve() is the sole terminal lifecycle mutation authority.
- CommanderHandoff must not evaluate remediation policy, execute remediation, or mutate incident lifecycle.
- No duplicate policy evaluation, execution, verification, or terminal lifecycle mutation.

## Production safety

- Production remediation defaults fail closed.
- Unknown or incomplete production facts deny consequential effects.
- Do not invent autonomous remediation rules.
- Do not weaken fail-closed behavior to make tests pass.
- Commander-only production authorization requires exact typed durable continuity.
- Replay protection and single-use semantics remain mandatory where specified.
- Autonomous production behavior must remain bounded by canonical target/action policy, cooldown, retry budget, blast radius, and independent verification.

## Repository safety

Repository development and CI must not restart production services, reboot hosts, mutate external production state, or perform live remediation. Host-specific validation belongs to separately governed operational procedures.

Do not commit credentials, private keys, machine-specific secrets, runtime evidence stores, or host-local state.

Do not create or commit backup files such as `.bak*`, `.pre_*`, `*.identity_backup*`, or timestamped scratch copies. Git history is the historical record.

## Testing discipline

For a coherent change:

1. Inspect the relevant dependency closure and contracts.
2. Implement the smallest complete vertical slice.
3. Run focused behavioral tests while iterating.
4. Run integration/regression tests for the affected boundary.
5. Run the full regression before declaring the change complete.
6. Run the public-release secret/history scan.

Priority of evidence:

1. Behavioral tests
2. Integration tests
3. Structural/AST invariant tests where they protect real architecture boundaries
4. Text assertions only when no stronger test is practical

## Working style

- Prefer simple explicit Python.
- Prefer existing canonical components over speculative abstractions.
- Do not redesign architecture during implementation unless a demonstrated blocker requires it.
- Keep changes focused and auditable.
- Preserve exact effect identity and evidence continuity across safety-sensitive paths.

## Security reporting

Follow `SECURITY.md`. Do not disclose suspected vulnerabilities or secrets in public issues or pull requests.
