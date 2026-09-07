# Production incident dispatch boundary — 2.13D.D8.6

`sentinel.systemd_incident_dispatch.assess_systemd_incident_dispatch` is an
explicit, pure assessment API. It is not subscribed to incident events and is
not called by the daemon, diagnostic coordinator or runtime composition.
`SystemdIncidentDispatchAssessment` is immutable routing information, never
an authorization, execution capability, final outcome or reusable approval.

## Discovered authority boundaries

- `incidents.manager.Incident` holds OPEN → INVESTIGATING → TERMINAL state;
  `IncidentManager` owns canonical incident lookup and terminal `resolve`.
- `diagnostic.investigation.InvestigationManager` owns investigation lifecycle;
  `diagnostic.engine.DiagnosticEngine` records evaluator output and completes
  the investigation. `diagnostic.evaluator.DiagnosisEvaluator` alone diagnoses.
- `diagnostic.runtime_coordinator.RuntimeDiagnosticCoordinator` selects catalog
  metadata, calls `CommanderIntentAssessor` with `CommanderSemanticPolicy`, then
  `CommanderIntentDecider`, and creates `RemediationActionRequest`.
- `diagnostic.commander_handoff.CommanderHandoff` delegates to Commander;
  `RemediationPolicy` owns authorization, `RemediationActionCatalog` metadata,
  `ExecutionBoundary` execution, and the verification boundary recovery facts.
  `FinalOutcomeMapper` supplies the outcome to `IncidentManager.resolve`.
- `runtime.SentinelRuntime.systemd_production_integration` shares the runtime
  Commander and policy. Its explicit production execution path lazily enters
  `production_runtime_guard` for durable attempt records and the process lease.
  D8.6 neither invokes nor modifies this path.
- `SystemdUnitIdentity.component_id` defines `systemd:<exact-unit>.service`.
  `SystemdReadOnlyInspector` produces strong snapshots independently. The
  current incident sensor, observation adapter and deterministic hypothesis
  producer operate on TMUX. Generic diagnostic observations contain command
  results, not decoded, bound systemd identities.

## Input and eligibility contract

Callers must supply canonical outputs from the same trusted diagnostic and
Commander processing context. This API checks their consistency; it does not
authenticate arbitrary caller-created Python objects or rerun their owners.

A candidate requires all of the following:

1. Canonical Incident in INVESTIGATING in both lifecycle fields, with no final
   outcome, and a nonempty exact incident identity.
2. Exact component name validated with the existing D8.1 unit validator. No
   trimming, wildcard, template/instance, alias resolution or fuzzy matching.
3. Completed canonical Investigation linked to the incident, component,
   trigger and Diagnosis; ESTABLISHED Diagnosis with nonempty conclusion and
   defensible nonempty supporting references. Contradictory support fails.
4. Exact RemediationActionRequest incident/investigation/diagnosis/reference
   linkage with canonical `RESTART` action. Commands are neither parsed nor
   generated. Action availability is consumed from the canonical assessment.
5. Configured Commander semantic assessment requiring remediation with action
   available and no Commander intervention; matching diagnosis status and
   `CommanderIntentDecision.intent is AUTONOMOUS_REMEDIATE`.
6. Explicit tuple of canonical diagnostic Observations covering exactly the
   diagnosis support, registered in investigation observation/evidence IDs,
   each bound to the same investigation and component. For this new in-memory
   contract their source is `SYSTEMD`, subject is `unit_snapshot`, and value is
   a typed `SystemdUnitSnapshot` from a trusted evidence adapter. Plain strings,
   dictionaries or raw command output are not identity proof. Snapshot unit
   must match exactly, be loaded and failed. Duplicate references, conflicting
   snapshots, missing or foreign evidence fail closed.
7. Early protected-name exclusion by reusing D8.1 `protected_target`; this
   excludes Sentinel, the controlled-live canary and other protected names
   without duplicating their definitions or evaluating the target policy.

Candidates still require a fresh evidence-to-bound-plan handoff, an explicit
production autonomous target rule, current D8.1 target-safety facts (including
protection, cooldown, retry budget and blast radius), and canonical downstream
RemediationPolicy authorization. An empty production target policy can never
be bypassed by a positive routing assessment. Inputs are mutable canonical
objects; results cannot authorize later use after those inputs change.

## Deliberate split and default inertness

There is currently no trusted systemd diagnostic evidence producer or typed
snapshot round-trip adapter. D8.6 defines its required input shape, but does
not manufacture evidence or claim that the existing daemon can produce a
candidate. Tests supply synthetic snapshots and use the real DiagnosisEvaluator
and Commander semantic/intent owners.

No plan is built. `build_bound_systemd_remediation_plan` requires a fresh exact
snapshot, action scope and run/execution/permit bindings absent from canonical
incident objects. Adding those by inference would cross this phase's boundary.

NEXT: trusted systemd evidence-to-bound-plan milestone, including persisted
snapshot decoding/provenance and canonical builder handoff, before any separate
autonomous dispatch activation. Production target allowlist, action activation,
bound effects, attempt ledger, lease and execution identity remain untouched.
