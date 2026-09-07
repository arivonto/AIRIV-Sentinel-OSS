# Controlled Live Remediation Design — Phase 2.13C

Status: **BLOCKED**. Design and repository-only characterization; no live
activation is specified or authorized. Phase 1 and phases through 2.13B remain
locked. The requirements below describe repairs for later approval, not new
implemented capabilities. Do not proceed to live preflight or execution.

## 1. Candidate and exact failure condition

Option A is the preferred candidate for further safety work: one retained dead
pane in a uniquely named, Commander-created validation session. Candidate name
format: `airiv-validation-<random-run-token>`; a prefix is never authorization.
No name/token has been allocated and no session has been created in this phase.
The canonical trigger is `PANE_DEAD` (`contract_verifier.py` and incident bridge),
with a fresh boolean `pane_dead=True` and an ESTABLISHED termination diagnosis.
Do not register a broad PANE_DEAD semantic rule or invent a synthetic diagnosis.
The eventual rule must additionally match the exact enrolled resource and run.

Option A conceptually respawns the retained pane without killing a live process.
Option B (recreate session/window/pane) has no repository action implementation
and introduces replacement identity mapping; reject it for this first run.
Option C (temporary marker repair) has no corresponding canonical live sensor,
diagnosis, catalog action or verifier; it is not an acceptable fallback/no-op.
No candidate currently satisfies all acceptance criteria A–M.

## 2. LIVE TARGET IDENTITY BLOCKER

`sensors/tmux/parser.py` captures session name, window name/index, pane ID/index,
pane PID, capture timestamp and output hash. Normalization and incident evidence
retain those facts. `runtime_sensor_adapter.py` identifies components and caches
state by pane ID alone. `diagnostic/evidence.py:record_incident_observations`
reduces canonical Observation.value to pane_id and pane_dead; session identity
is lost there. Neither this observation nor the sensor proves server generation,
session ID, window ID or controlled resource ownership. Output hash, incident ID
and investigation ID identify evidence/workflow, not a live TMUX incarnation.
Names, indexes, PIDs and `%0` alone are insufficient against reuse.

MINIMUM REQUIRED IDENTITY EXTENSION: preserve an immutable target snapshot from
sensor through canonical observation, supporting evidence, authorization,
execution identity and verification. It must include explicit server endpoint
and validated server generation (owner UID, PID plus process start identity),
session ID and exact name, window ID, pane ID, and an enrolled validation-run
nonce/creation identity. Bind observation ID, capture time and fingerprint plus
incident/investigation/diagnosis references to that snapshot. Socket path or
random name alone is not an incarnation guarantee. PID of the pane process may
change on recovery and is evidence, not the stable pane identity.

The future implementation must prove no target substitution between validation
and effect, including server replacement at the same socket and pane movement.
A separate check followed by an unguarded pane-ID command is insufficient.
An isolated server dedicated to this run is the preferred containment candidate,
but collection/diagnostic/verification endpoint support and race safety remain
unimplemented. Prove exclusivity, no attached clients, no shared/linked windows,
and no inherited hooks that can cause unrelated effects. Do not silently change
component_id semantics; add a target safety identity and fail closed on mismatch.
If this cannot be done additively, seek an explicit contract amendment later.

## 3. Action and deterministic execution binding

There is no TMUX recovery/respawn action in canonical production source.
`restart_test` is only a runtime policy allowance, not a registered action.
`RemediationActionEntry` is frozen and contains a static string command; the
catalog selects by trigger only and has no runtime target-binding facility.
The coordinator passes entry.command unchanged on its normal path. That does
not establish an enforced command authorization invariant.

Exact defect: RemediationRequest/Decision contain state, component and action,
but no command, incident ID, target snapshot or execution ID. The orchestrator
checks only action/component/state on a supplied decision. The gate accepts any
separately supplied command after ALLOW. The identity journal records that
command but does not prove catalog membership or that policy authorized it.
Thus the same action/component decision can execute a different command/target
on its first claim. Frozen catalog entries do not prevent this substitution.
`execution.py` executes the string with shell=True and no timeout.

Required future invariant: one immutable catalog-owned effect specification,
including exact executable/argv, bounded environment and working directory,
target snapshot, catalog version/digest and preconditions, must be bound by the
policy decision to the incident and one preallocated execution ID. The existing
gate/identity boundary must reject any mismatch before effect, without duplicate
policy evaluation or a second executor. Use a bounded argv mode within the
canonical ExecutionBoundary; no arbitrary shell or command interpolation.
Validate executable provenance and TMUX's own command parsing, not just Python
shell=False. Catalog remains the only command owner.

Candidate operation is respawn-pane on the exact retained dead pane, without
`-k`, with an explicitly approved bounded inert workload instead of replaying an
unknown original command. Exact argv/workload is deliberately NOT selected:
identity and binding blockers prevent an acceptable concrete effect today.
The dead pane must survive workload exit; deliberate stimulus is workload exit,
not pane/session destruction. Any remain-on-exit setup is limited to the future
test resource and requires later approval.

TMUX documentation: respawn-pane without -k requires an inactive pane; omitting
the workload reuses its previous command. list-panes -a ignores the target and
lists the server's panes. The current parser uses -a with -t, so target_session
is not an isolation boundary. See the [TMUX manual](https://man.openbsd.org/tmux).
Local binary reports tmux 3.6; installed-version behavior and race guarantees
must be checked in later isolated validation, not inferred from the online manual.

## 4. Authorization and semantic scope

CommanderSemanticPolicy.assess accepts only a trigger string; there is no
resource predicate. RemediationPolicy allows by action membership only; state
and component are copied, not constrained. It cannot allowlist trigger, exact
component, incident, command or target incarnation. A unique action name alone
does not prove the triggering incident belongs to its target.

Minimum additive contract: semantic matching of PANE_DEAD AND the enrolled exact
target/run using canonical facts; unknown/missing/stale/mismatched identities
remain commander-required. Semantic policy still owns only semantic facts.
RemediationPolicy must independently constrain one action/effect, that target,
incident, established evidence references, validity window and execution ID.
Exactly one rule, one catalog entry/trigger mapping, one policy allowance and
one run permit may exist in the isolated composition. No prefix, wildcard,
default/current-session target, inferred identity or broad dead-pane allowance.

## 5. Independent verification

Existing TmuxRemediationVerifier independently queries pane_dead via subprocess
argv; it does not use the remediation return code. However, it queries only a
pane ID on the default server, has no timeout, generation/session/window check
or observation timestamp. A recycled or unrelated live pane can pass. The
autonomous coordinator does not install this verifier by default; the separate
runtime.remediate wrapper installs it, but must not become an alternate live path.

Require one bounded canonical verification invocation after successful new
execution, with fresh observation time later than execution.finished_at. It must
prove same server generation, session/name, window and retained pane, enrolled
run ownership, pane_dead=False and expected bounded workload. Missing/ambiguous
identity, timeout or stale observation fails verification. Propose a total five
second observation budget, subject to later implementation validation. Capture
unrelated session/window topology before/after where available; that comparison
is supporting evidence, not a substitute for isolation or a claim that unrelated
user activity cannot occur. New pane ID means failure for Option A; no implicit
replacement/component remapping. Only FinalOutcomeMapper may infer RECOVERED,
and only IncidentManager.resolve may terminalize. Failure or missing verification
must not claim recovery. Replay performs no new verification.

## 6. Execution identity and one-run limit

The existing journal atomically publishes and fsyncs CLAIMED, then persists
RUNNING before gate execution. Same-ID replay on the same retained journal
cannot execute again, including terminal UNKNOWN. Interrupted nonterminal claims
fail closed/wait and need canonical recovery; they are not new attempts.
Different IDs may execute independently by the locked identity amendment.
Changing/deleting the journal defeats its scope; never clear it during teardown.
Replay currently returns the saved record without rejecting different supplied
binding fields: it prevents a second effect but does not prove request equality.

Require a durable, single-use controlled run permit bound to one execution ID
inside existing authorization/identity ownership, not a competing deduplicator.
Reject distinct-ID attempts under the same run, cross-target replay and modified
effect data. Allocate the ID once; never silently replace it on retry, crash,
timeout or UNKNOWN. Maximum one external action and one verification invocation.

## 7. Evidence and passive correlation

Existing surfaces: var/runtime/live_observations.jsonl and commander_decisions.jsonl;
InvestigationStore observations/hypotheses/diagnosis; canonical incident evidence
and in-memory terminal history; var/execution_identity/<id>/record.json.
The decision writer already adds PID/INVOCATION_ID and the coordinator supplies
incident, investigation, diagnosis, semantic facts, intent, policy decision,
execution_id (when available), and final disposition. Thus a normal successful
published decision can join the execution journal to the service invocation.
This is partial, not sufficient end-to-end live evidence: publication happens
after completion, writer failures are logged rather than fatal, target generation
is absent, and detailed verification remains in memory rather than the journal.

Minimum passive addition: extend existing evidence envelopes with validation
run ID, execution ID, effect/target digest and executor PID/invocation at the
pre-effect boundary; preserve links to the canonical evidence IDs. Append a
durable projection of canonical verification/outcome to the existing evidence
surface before one-shot disposal. Do not reevaluate policy, verify twice, invent
outcomes, create a parallel evidence authority or overload the identity journal
with lifecycle ownership. Preserve command/result/times and canonical policy
reason/action through references. Evidence readiness is a run precondition;
missing final evidence makes validation inconclusive, never successful.

## 8. Activation/deactivation concept — not an activation procedure

Current service composition is static Python. There is no live semantic/catalog
configuration API, environment loader or unregister API. Evidence-directory
environment variables do not activate policy. Worker unregister is unrelated.
Fresh production has empty semantic triggers and catalog actions/triggers, but
its policy contains legacy restart_test. Do not describe that allowance as empty.

Preferred future mechanism is a dedicated local one-shot validation composition
using the same complete canonical pipeline, external explicit test manifest,
separate evidence roots and exclusive target, with no persistent scheduler or
remote control plane. This is not implemented or approved. It would exercise
live host behavior in a separate process, not prove execution by the running
systemd invocation. Record the service PID/InvocationID as baseline context and
the actual one-shot PID/run ID as executor; never borrow the service invocation.
If running-service execution is mandatory, activation remains unresolved and
requires later approval of a minimal mechanism; no restart is assumed authorized.

Before: prove fresh defaults and running-service baseline, then satisfy all
repairs and obtain Commander approval of concrete preflight artifacts. Later
isolated configuration would be local to the one-shot instance only. After:
revoke/consume the permit, prevent further submissions, retain evidence and
discard the entire one-shot composition. Construct a fresh non-started production
composition to prove both registries empty and no controlled allowance leaked.
Instance disposal avoids nonexistent unregister APIs; it does not remove rules
from a still-running configured service. Service activation/removal is blocked.
No restart is needed for the proposed separate process; existing service static
activation would require a separately approved reload/restart mechanism.

## 9. Cleanup, abort and containment

Future Commander-approved teardown is outside remediation and never registered
as a second action. After revocation and evidence retention, validate the exact
enrolled server generation/session ID/name/nonce and exclusive topology, then
remove only that controlled test session. Absence is already clean; identity
mismatch stops cleanup for Commander inspection. No wildcard, kill-server,
default target, PID kill/pkill, shared window removal or recursive deletion.
Preserve journals and canonical records. Exact cleanup command is blocked on the
same target binding repair; no executable teardown helper is supplied here.

Abort on any missing criterion A–M; unexpected client/window/hook, identity reuse,
stale diagnosis, target alive before effect, catalog/command mismatch, expired
permit, second incident/ID, evidence failure, unexpected host change, timeout,
execution failure or failed verification. UNKNOWN never retries automatically.
Containment is permit revocation and bounded test-session teardown, not a
compensating production action. If teardown identity is uncertain, leave the
resource for Commander review. No service rollback/restart or configuration edit.

Forbidden: systemd/service mutation (including Sentinel restart), networking,
firewall, SSH, users, permissions, packages, kernel/sysctl, disks/mounts/databases,
repository or production configuration mutation by the live action, boot/desktop
or power changes, reboot/shutdown/sudo, unrelated process signals, arbitrary shell
execution, persistent autonomous rules. Evidence writes and repository-only
design/tests are distinct from the candidate host effect.

Unrelated-resource safety cannot yet be certified. Future isolation, exact
incarnation binding, no shared windows/hooks, bounded workload and exact teardown
must make unrelated TMUX effects unreachable. Such an action would have no SSH
or Sentinel control capability; resource exhaustion must also be bounded. Merely
asserting a test session name does not prove safety. No live risk was exercised
in Phase 2.13C.

## 10. Acceptance and Commander approval gates

| Criteria | Current assessment |
| --- | --- |
| A, B, C, D, E | Test-only/non-root isolation is a candidate; containment not proven. |
| F, G | BLOCKED: incarnation identity, resource policy and command binding absent. |
| H, I | Same retained journal/ID protection exists; one-run distinct-ID cap absent. |
| J | Existing verifier independently observes state. |
| K | BLOCKED: pane-ID-only verification cannot prove intended incarnation recovery. |
| L | BLOCKED: exact identity-safe teardown not implemented. |
| M | Fresh defaults disabled; running-instance removal absent. |

Before Commander may approve execution: demonstrate identity propagation and
race-safe effect targeting; immutable policy/catalog/command binding with tamper
rejection; one-run durable permit and replay/crash/concurrency tests; bounded
independent identity verification; complete durable evidence correlation; exact
reviewed workload/argv and teardown; isolated activation/disposal; empty production
defaults before/after; no shared-resource or forbidden effects; passing focused
and full regression; and explicit approval of the chosen execution process model.

Phase 2.13C tests characterize actual limitations using inert tokens and mocked
external observations, alongside existing 2.13A/B safety tests. Passing those
tests is evidence of findings, NOT proof that blocked criteria now pass. No
preflight script, live rule, action, activation entrypoint or repair is implemented.

Next milestone: **Phase 2.13C.1 — Live Remediation Safety Boundary Repair**.
Do not implement it under this design task.
