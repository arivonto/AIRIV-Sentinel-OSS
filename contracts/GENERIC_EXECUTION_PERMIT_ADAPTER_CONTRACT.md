# AIRIV Sentinel — Generic Execution / Permit Adapter Contract

## Purpose

Extend the already-proven durable live-run permit and execution-identity
authority to generic resource-bound effects without creating a second
permit, execution, or authorization authority.

## Authority

RemediationPolicy remains the sole ALLOW/DENY authority.

RemediationExecutionIdentityJournal remains the sole durable:
- live-run permit authority;
- execution identity authority.

RemediationExecutionIdentityBoundary remains the canonical ordering
boundary:

authorization
→ durable one-run permit
→ execution identity claim
→ RUNNING
→ execution gate
→ terminal execution identity.

## Generic Effect Compatibility

The execution path consumes the shared nominal
BoundRemediationEffectContract.

It must not depend on TMUX-specific:
- target.run_id;
- target fingerprint layout;
- pane/session semantics.

Canonical abstractions:
- `effect.policy_run_id`
- canonical target fingerprint
- immutable `effect.argv`
- exact execution ID
- exact permit ID
- exact effect fingerprint.

## ResourceBoundPermitBinding

GenericResourceExecutionPermitAdapter requires the D3
ResourceBoundPermitBinding to match the exact effect before delegation.

This binds resource/action scope into the effect fingerprint before the
durable permit authority is entered.

## Replay

Exact completed replay:
- returns durable prior execution result;
- does not execute again.

Permit-without-execution-identity replay:
- fails closed;
- MUST NOT execute.

Changed effect under the same run:
- durable permit conflict;
- MUST NOT execute.

## Safety

D4B uses only a fake executor.

D4B performs no:
- subprocess execution from the generic adapter test path;
- systemctl restart/start/stop;
- sudo;
- pkexec;
- shell;
- production permit claim;
- production service mutation.
