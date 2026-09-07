# AIRIV Sentinel — Generic Resource-Bound Remediation Contract

## Purpose

Generalize the strong binding model proven by controlled TMUX
remediation so future remediation targets are not implicitly tied to
TMUX identity semantics.

The existing TMUX controlled-live contract remains unchanged.

## Canonical Separation

Resource Identity
→ Resource Action Scope
→ Generic Bound Effect
→ Policy Authorization
→ Permit Binding
→ Execution
→ Independent Verification

D3 stops before execution.

## Generic Bound Effect

Every resource-bound remediation effect MUST immutably bind:

- remediation run ID;
- incident ID;
- component ID;
- resource kind;
- exact target identity fingerprint;
- exact action-scope fingerprint;
- action;
- immutable argv;
- execution ID;
- permit ID.

The effect fingerprint MUST change if any bound field changes.

## Permit Binding

Before an execution permit can later be claimed, the permit envelope
MUST bind:

- run ID;
- incident ID;
- component ID;
- action;
- execution ID;
- permit ID;
- target fingerprint;
- scope fingerprint;
- effect fingerprint.

Permit binding creation alone does not grant execution authority and
does not execute an effect.

## Systemd Integration

For systemd restart:

- resource kind is `systemd.service`;
- component ID is `systemd:<exact-unit>`;
- target is the strong SystemdUnitIdentity;
- scope is BoundSystemdActionScope;
- argv comes only from the immutable scope;
- initial operation surface remains RESTART only.

## Compatibility

RemediationPolicy remains the sole ALLOW/DENY authority.

D3 must prove that the generic systemd-bound effect can participate in
the current bound-policy semantics without changing or weakening the
existing TMUX path.

## Safety

D3 performs no:

- systemctl restart/start/stop;
- sudo;
- pkexec;
- shell execution;
- live execution permit claim;
- production policy activation;
- production catalog activation;
- production service mutation.
