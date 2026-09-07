# AIRIV Sentinel — Durable Production Activation Consumption Contract V1

## Phase

2.13D.D8.10B

## Purpose

Make a D8.10A activation grant durably single-use before any future
production remediation delegation can occur.

D8.10B is persistence only.

It does not activate the runtime execution path.

## Canonical State Root

Default:

`~/.local/state/airiv-sentinel-secure/systemd_production_activation`

The default is intentionally outside both the source repository and the
existing group-writable `~/.local/state/airiv-sentinel` tree. Its new
`airiv-sentinel-secure` ancestor is created by the canonical secure
production-state traversal with owner-only mode `0700`.

Test/runtime override:

`AIRIV_SENTINEL_SYSTEMD_PRODUCTION_ACTIVATION_DIR`

The activation-consumption state is separate from:

- execution identity journal;
- production attempt ledger;
- trusted systemd evidence store.

## Security

The store reuses the canonical secure production-state directory
boundary:

- descriptor-based directory traversal;
- no symlink following;
- private owner-only directory;
- private owner-only regular files.

## Single-Use Key

`activation_id` is the durable single-use namespace key.

The canonical filename is derived from SHA-256 of the exact
`activation_id`.

A previously consumed `activation_id` MUST NOT be reusable with:

- the same grant;
- a modified grant;
- another approval ID;
- another incident;
- another component;
- another execution;
- another effect fingerprint.

## Pre-Consumption Validation

Before durable reservation, D8.10B must invoke the canonical D8.10A
`SystemdProductionActivationBoundary.assess()`.

Only `eligible=True` may proceed to durable consumption.

Expired, not-yet-active, or mismatched grants produce no consumption
record.

## Durable Reservation

Consumption uses:

- canonical final filename;
- `O_CREAT | O_EXCL | O_NOFOLLOW`;
- mode `0600`.

The containing directory is fsynced immediately after the exclusive
file reservation.

The record body is then written, flushed and fsynced.

The directory is fsynced again after the complete record write.

## Crash Semantics

The reservation itself consumes the activation conservatively.

If the process crashes after `O_EXCL` reservation but before a complete
record is durable, the partial file MUST remain.

Partial or malformed published consumption state MUST fail closed.

It MUST NOT be ignored, repaired automatically, overwritten, or
retried as if unused.

## Corruption

Before creating a new consumption record, all existing published
consumption state must validate canonically.

No append may occur past corrupt state.

## Canonical Record

A durable record contains:

- activation ID;
- approval ID;
- incident ID;
- component ID;
- execution ID;
- effect fingerprint;
- D8.10A grant fingerprint;
- consumed timestamp.

## Semantics

A successful D8.10B consume means only:

> this exact activation ID has been durably and irreversibly consumed
> for the validated effect identity.

It does NOT mean:

- RemediationPolicy ALLOW;
- runtime bridge enabled;
- runtime invocation enabled;
- dispatch gate enabled;
- production target allowlisted;
- permit claimed;
- attempt persisted;
- effect executed;
- verification completed.

## Runtime

`SentinelRuntime` MUST NOT own the D8.10B consumption store in this
phase.

`SentinelRuntime.run_once()` MUST NOT consume activation grants.

D8.9D, D8.9C and D8.9A remain disabled.

## Authority Separation

D8.10B MUST NOT call:

- production target policy;
- RemediationPolicy;
- production runtime guard;
- D8.9D runtime bridge;
- D8.9B delegation;
- permit adapter;
- execution boundary;
- verifier;
- final outcome mapper;
- IncidentManager.resolve.

## Host State

No systemd operation, D-Bus call, polkit modification or service
restart is permitted.

## Future Handoff

A later phase may bind a valid durable consumption record to the exact
prepared effect before an explicit runtime bridge is permitted to
proceed.

Actual production activation remains separately Commander-gated.
