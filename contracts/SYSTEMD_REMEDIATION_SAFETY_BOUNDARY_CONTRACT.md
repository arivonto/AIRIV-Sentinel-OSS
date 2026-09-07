# AIRIV Sentinel — Systemd Remediation Safety Boundary

## Purpose

Define the strong resource identity and immutable action scope required
before AIRIV Sentinel may remediate a real systemd service.

This phase does not authorize or execute any systemd mutation.

## Canonical Resource Identity

A live-eligible systemd target must bind:

- system manager boot ID;
- system manager PID;
- manager process start identity;
- exact canonical unit name;
- exact FragmentPath;
- SHA-256 of the fragment;
- fragment device/inode identity;
- fragment owner UID/GID.

Runtime state such as MainPID is observation state, not permanent resource
identity.

## Supported Initial Operation

The first supported production-remediation operation is:

`RESTART`

START and STOP are intentionally outside the initial production action
surface.

## Immutable Command

Canonical restart argv:

`<absolute-systemctl> --no-ask-password restart <exact-unit-name>`

Requirements:

- argv tuple is immutable;
- no shell;
- no sudo;
- no pkexec;
- no interactive password request;
- no caller-supplied alternate unit after scope construction.

## Verification

Restart verification must independently prove:

- same manager generation;
- same exact unit identity;
- same fragment fingerprint;
- LoadState remains loaded;
- ActiveState becomes active;
- invocation identity changes when required.

Verification is read-only.

## Policy / Activation

Production RemediationPolicy and RemediationActionCatalog remain EMPTY by
default.

Future systemd live authorization must use explicit temporary activation
and exact bound effect semantics. No permanent production action is
registered by this phase.

## Safety

D2 performs no:

- systemctl restart/start/stop;
- sudo;
- pkexec;
- policy activation;
- catalog activation;
- permit claim;
- systemd mutation;
- production service mutation.
