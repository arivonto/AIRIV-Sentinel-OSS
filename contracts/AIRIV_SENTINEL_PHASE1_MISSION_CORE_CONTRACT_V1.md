# AIRIV Sentinel Phase 1 Mission Core Contract V1

**Status:** LOCKED
**Authority:** Blueprint v2.0 / Engineering Constitution
**Production effect:** NONE

## Purpose

Phase 1 Mission Core is the Sentinel-owned lifecycle boundary for a single
engineering mission.

It implements:

```text
Observe -> Understand -> Plan -> Execute -> Verify -> Retry -> Complete -> Learn
```

## Ownership

Sentinel owns:

- Mission identity;
- lifecycle ordering;
- evidence requirements;
- verification outcome;
- completion status;
- learned mission record.

AI providers may supply only:

- reasoning;
- analysis;
- explanation.

Provider output is never mission authority.

## Phase Boundary

Mission Core is Phase 1 Core software.

It must reject mission execution when the requested target is Phase 2 Desktop,
Phase 3 Remote, or Phase 4 Web.

## Fail-Closed Rules

Mission Core fails closed when:

- the request lacks mission id, objective, or provider identity;
- the implementation does not provide every lifecycle handler;
- any lifecycle stage lacks evidence;
- any lifecycle stage reports unverified evidence;
- the requested work violates Linux-first, AI-independence, Mission ownership,
  Engineering Brain ownership, or no-vendor-lock-in requirements.

## Effect Boundary

Mission Core is in-memory and side-effect-free by default.

It does not:

- call an AI provider;
- execute shell commands;
- restart services;
- mutate production;
- grant provider authority;
- bypass Commander escalation rules.

Concrete execution remains owned by existing execution, remediation, and
Commander boundaries.
