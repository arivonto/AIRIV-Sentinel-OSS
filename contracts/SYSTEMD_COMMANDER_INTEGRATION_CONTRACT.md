# AIRIV Sentinel — Systemd Commander Integration Contract

## Purpose

Compose the generic systemd remediation path through the canonical
Commander-owned remediation authorities without performing a real
systemd restart.

## Canonical Flow

BoundSystemdRemediationPlan
→ Commander-owned RemediationPolicy
→ BoundRemediationAuthorization
→ ResourceBoundPermitBinding
→ GenericResourceExecutionPermitAdapter
→ existing durable one-run permit
→ existing execution identity journal
→ existing remediation execution gate
→ fake argv executor
→ independent post-effect snapshot
→ SystemdRestartVerifier

## Authority

This integration introduces no new authorization authority.

- RemediationPolicy remains sole ALLOW/DENY authority.
- existing execution identity journal remains sole durable permit authority.
- existing execution identity journal remains sole execution identity authority.
- GenericResourceExecutionPermitAdapter remains a thin delegation surface.
- SystemdRestartVerifier owns systemd restart verification semantics.

## Verification Requirements

Successful recovery verification requires:

- execution succeeded;
- post-effect snapshot independently captured;
- exact target identity unchanged;
- unit remains loaded;
- post-state is active;
- InvocationID changed when required.

Execution success alone is not recovery.

## DENY

DENY must produce:

- no permit claim;
- no execution identity;
- no executor call;
- no verification probe.

## Execution Failure

Execution failure must produce:

- durable execution result;
- no verification probe;
- no false recovery result.

## Safety

D5B uses:

- synthetic SystemdUnitSnapshot objects;
- fake argv executor;
- temporary test-local execution journal.

D5B performs no:

- `systemctl restart`;
- `systemctl start`;
- `systemctl stop`;
- sudo;
- pkexec;
- shell execution;
- production permit claim;
- production policy activation;
- production service mutation.
