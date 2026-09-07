# Controlled Remediation Safety Contract — Phase 2.13A

Scope: repository-only deterministic validation of the existing autonomous path.
No production enablement or new production authority is introduced.

## Required path and authority

Observation → Investigation → Diagnosis → CommanderSemanticPolicy →
CommanderIntentAssessment → CommanderIntentDecider → RemediationPolicy →
RemediationActionCatalog → ExecutionBoundary → Verification →
FinalOutcomeMapper → IncidentManager.resolve().

Catalog availability is inspected before intent assessment in the existing
composition; this is availability evidence, never authorization. No phase may
substitute for another authority.

1. Autonomous remediation requires explicit semantic configuration. Unknown or
   unconfigured input fails closed to commander-required semantics.
2. Intent must be AUTONOMOUS_REMEDIATE before remediation policy is evaluated.
   CommanderSemanticPolicy exclusively owns semantic requirements; the assessor
   produces facts and CommanderIntentDecider exclusively selects intent.
3. RemediationPolicy exclusively authorizes. DENY prevents execution. Catalog
   membership does not authorize; the action and command must be registered.
4. ExecutionBoundary exclusively executes. Harness commands are inert tokens
   handled by a test adapter, never submitted to its production shell backend.
5. Command success alone is not recovery. RECOVERED requires autonomous intent,
   ALLOW, successful execution, and independent successful verification.
6. Missing or failed verification yields UNRESOLVED. Failed execution yields
   UNRESOLVED and must not invoke verification. DENY and NEED_COMMANDER yield
   ESCALATED.
7. FinalOutcomeMapper exclusively maps final outcomes. Only
   IncidentManager.resolve() terminalizes incidents. Actions may not mutate
   lifecycle. Evidence attachment grants no lifecycle authority.
8. Each reached authority runs once per completed investigation handoff;
   execution is at most once, verification only after successful new execution.
   Non-autonomous paths never evaluate remediation policy.
9. Every execution uses the existing execution_id and durable identity journal,
   linked to incident, component, action, and command. ALLOW precedes identity
   claim. Failed execution results remain inspectable.
10. Replay of a consumed execution_id does not execute or verify again. Completed
    investigation handoffs do not repeat mapping or resolution. This does not
    promise deduplication of different IDs or concurrent coordinator handoffs.
11. Verification is correlated inside RemediationEvidenceRecord and incident
    evidence with the execution_id. The durable execution journal stores command
    results, not verification. Incident history retains verification in memory;
    this phase does not introduce restart-durable verification storage.
12. Harness configuration and adapters are test-only and non-destructive: no
    shell, subprocess, network, service control, privilege elevation, filesystem
    destruction, reboot, shutdown, systemd, /etc, or live stimulus. Temporary
    evidence and identity storage are permitted. No production actions or
    semantic triggers may be registered by this phase.

## Existing fail-closed edge contracts

Missing catalog action raises KeyError before intent decision and policy
evaluation, with no execution, identity claim, mapping, or terminal mutation.
The incident remains active; an ALLOW-configured policy cannot bypass this gate.
Do not fabricate an ALLOW decision to force this case through later phases.

Canonical diagnostic DENY does not call Commander.remediate(), so it allocates
no execution_id. The lower-level direct Commander API can allocate an ID for
denial evidence, but does not claim a durable execution identity on DENY.

Production semantic policy and action catalog remain empty. The existing
runtime policy allow-list contains restart_test; that is not a catalog action
and is not changed here. Direct low-level command APIs are outside the
autonomous diagnostic entrypoint tested here.

## Executable evidence

`tests/test_controlled_remediation_safety_v1.py` covers A–H using one real runtime,
manager, Commander, and diagnostic coordinator per fixture, real persisted
observation/hypothesis/diagnosis, real policy and mapper, and the existing
CountingExecutor test adapter. Matrix counts are asserted by reached branch,
including zero for boundaries deliberately blocked upstream. Production-default
and structural checks supplement behavioral lifecycle and external-operation
guards. Phase 2.13B is not implemented.
