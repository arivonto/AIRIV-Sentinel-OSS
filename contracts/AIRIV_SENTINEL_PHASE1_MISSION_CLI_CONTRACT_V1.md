# AIRIV Sentinel Phase 1 Mission CLI Contract V1

**Status:** LOCKED
**Authority:** Blueprint v2.0
**Production effect:** NONE

## Purpose

The Phase 1 Mission CLI is the text command surface for AIRIV Sentinel Core.

It must accept:

```text
sentinel mission "Fix this repository until all tests pass."
```

The command routes into Sentinel-owned Mission Core.

## Current Scope

This contract covers the initial runnable command foundation only.

The command:

- creates a Sentinel mission request;
- performs read-only workspace observation;
- runs the full Mission Core lifecycle;
- emits mission id, status, stage, workspace, event count, and effect evidence;
- exits successfully only when Mission Core reports complete.

## Current Boundary

The initial command is side-effect-free.

It does not:

- call an AI provider;
- mutate the repository;
- run tests;
- execute mutating shell commands;
- restart services;
- change production;
- grant provider authority.

Execution, repository repair, unattended retry, and durable mission memory remain
future Phase 1 Core work under separate contracts and verification.
