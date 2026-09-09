# AIRIV Sentinel

> **Clean open-source distribution.** This repository is the curated public source domain. Canonical private Git ancestry, private host evidence, private host-control material, credentials, authorization material, and internal release provenance are intentionally excluded.

> **Fail-closed Autonomous Commander for the AIRIV development and runtime ecosystem.**

[![AIRIV Sentinel CI](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Platform Linux](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=000000)
![Runtime systemd](https://img.shields.io/badge/Runtime-systemd-5C2D91?logo=linux&logoColor=white)
![Safety Fail Closed](https://img.shields.io/badge/Safety-Fail--Closed-critical)
![Autonomy Bounded](https://img.shields.io/badge/Autonomy-Bounded-orange)
![Canonical Regression](https://img.shields.io/badge/Canonical%20Regression-2154%20passed-success)
![Public Regression](https://img.shields.io/badge/Public%20Regression-2138%20passed-success)
![Status Pre-release](https://img.shields.io/badge/Status-Pre--release-yellow)

## Project description

AIRIV Sentinel is a security-first autonomous operations commander for AIRIV development and runtime systems. It observes runtime state, manages incidents, preserves auditable evidence, executes only explicitly authorized effects, independently verifies consequential outcomes, and performs autonomous remediation only inside bounded policy and safety contracts.

**Project state:** active V1 / pre-release. The V1 architecture is frozen and change-controlled. Post-freeze capabilities are accepted only when canonical authority, evidence, replay, verification, lifecycle, and disclosure boundaries remain intact.

**Canonical precedence:** `Contract > Implementation > Local Preference`.

## Repository topology — LOCKED

| Domain | Access | Role | Boundary |
| --- | --- | --- | --- |
| `AIRIV-Sentinel` | Private | Canonical source | Authoritative contracts, implementation, tests, private operational provenance, host/deployment control material, release tooling |
| `AIRIV-Sentinel-OSS` | Public | Curated open-source distribution | Explicitly allowlisted reviewed source, public contracts/docs/tests, standard deployment material, `README.md`, `index.html` |

The public project is **not** a mirror of private Git history. Publication is allowlist-based, secret-scanned, disclosure-validated, and fail-closed. Publishing source grants no runtime, production, Commander, or remediation authority.

## Current project lock — 2026-09-09

- **Target capability:** Autonomous Commander
- **Primary runtime:** Linux + systemd
- **Primary language:** Python 3.14
- **Canonical validation:** **225 focused + 2,154 full regression tests**
- **Curated OSS validation:** **225 focused + 2,138 full regression tests**
- **Canonical source head validated before this documentation closeout:** `20345b9ca323ca0527e12d680a627d1c750d13ea`
- **Curated OSS source head validated:** `ce4412d9082025fb0858979a60d75607a2d0122d`

| Area | Current state |
| --- | --- |
| Mission | **LOCKED** — AIRIV Sentinel is the Autonomous Commander |
| Strategic authority | **LOCKED** — human Commander retains final strategic authority |
| Safety | **LOCKED** — fail-closed / default-deny |
| V1 architecture | **FROZEN** and change-controlled |
| Incident lifecycle | Centralized, monotonic, evidence-driven |
| Execution | Exact authorized effect only |
| Verification | Independent; execution success alone is never recovery |
| Operational Evidence & Commander UX | **CORE COMPLETE** |
| Commander Delivery Transport Foundation | **COMPLETE** — non-network dry-run proof, default transport disabled |
| External email/webhook delivery | **DECISION-GATED / DISABLED** |
| Verified AI Agent Operations | **ACTIVE** — provider-neutral foundation next |
| Gate 3 | **PASSED / LOCKED** |
| Gate 4 | **BOUNDED** autonomous production-remediation profile |
| Distribution | Private canonical + curated public source; no private-history mirroring |
| Release | Pre-release; stable release/tag remains separate |

See the implementation sequence in [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md).

## Mission and authority

Canonical mission: [AIRIV Sentinel Mission Contract V1](contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md).

Authority chain:

```text
COMMANDER
  -> SENTINEL AUTHORITY POLICY
  -> AUTHORIZED EXACT EFFECT
  -> EXECUTION
  -> INDEPENDENT VERIFICATION
  -> EVIDENCE
  -> INCIDENT OUTCOME
```

Core rules:

- Human Commander retains final strategic authority.
- `RemediationPolicy` is the canonical remediation ALLOW/DENY authority.
- `ExecutionBoundary` is the sole command-execution boundary.
- Independent verification is required for consequential success claims.
- `IncidentManager.resolve()` is the sole terminal incident lifecycle mutation boundary.
- AI output is an execution/intelligence resource, never semantic authority by itself.
- Unknown, malformed, stale, mismatched, unauthorized, exhausted, or indeterminate effects fail closed.
- Terminal uncertain outcomes are not blindly retried.

## Canonical engineering flow

```text
Observation
-> Investigation
-> Diagnosis
-> CommanderSemanticPolicy
-> CommanderIntentAssessment
-> CommanderIntentDecider
-> RemediationPolicy
-> RemediationActionCatalog
-> Execution
-> Verification
-> FinalOutcomeMapper
-> IncidentManager.resolve()
```

No duplicate policy evaluation, execution, verification, or terminal lifecycle mutation is permitted.

## Runtime specification

Canonical entrypoint:

```text
$REPO/venv/bin/python -m sentinel
```

| Property | Value |
| --- | --- |
| Worker ID | `sentinel.runtime` |
| Worker name | `Sentinel runtime` |
| Worker version | `1` |
| Daemon cycle | `1.0` second |
| Health stale threshold | `30.0` seconds |
| Process manager | systemd |
| Service restart | `Restart=on-failure`, `RestartSec=5` |
| Logging | systemd journal |
| Standard umask | `0027` |

Standard template: [airiv-sentinel.service.in](deployment/systemd/airiv-sentinel.service.in).

## Operational Evidence & Commander UX — CORE COMPLETE

The unattended reporting stack now forms a read-only, derived operational surface:

```text
IncidentManager
-> IncidentReportBuilder
-> IncidentReportStore
-> IncidentReportRecorder
-> bounded runtime reconciliation
-> UnattendedIncidentRollup
-> CommanderAttentionQueue
-> CommanderDeliveryProjection
```

Locked behavior:

- active and terminal incidents are reportable without lifecycle mutation;
- reports are atomically persisted with integrity metadata;
- unsafe report identities and corrupt persisted state fail closed;
- reconciliation is idempotent and append-retentive;
- runtime reconciliation occurs immediately once, then at most once every 60 seconds;
- reporting errors are visible but cannot disable monitoring/remediation;
- Commander Attention Queue contains only canonical facts explicitly marked for Commander attention;
- delivery projection uses an exact-field disclosure allowlist;
- raw evidence snapshots, command/output details, credentials, tokens, and unreviewed future schema fields do not cross the delivery projection boundary.

## Commander Delivery Transport Foundation — COMPLETE

The delivery foundation proves the entire side-effect lifecycle without contacting an external recipient:

```text
CommanderDeliveryProjection
-> delivery identity claim
-> bound destination + transport continuity
-> RUNNING
-> transport
-> SUCCEEDED / FAILED / UNKNOWN
-> durable replay-safe outcome
```

Implemented guarantees:

- transport interface is explicit;
- production default is disabled/no-send;
- delivery identities are durable and replay-safe;
- projection digest + destination + transport identity are bound together;
- terminal `FAILED` and `UNKNOWN` states are not blindly retried;
- transport exceptions store exception type only, not exception text;
- delivery ledger does not persist subject/body/raw incident evidence/credentials;
- deterministic local file dry-run proves end-to-end orchestration without network access;
- dry-run artifacts are atomic and never overwritten;
- `SentinelRuntime.deliver_commander_brief()` is explicit;
- daemon `run_once()` does **not** auto-send.

**External network delivery is not enabled.** Email/webhook adapters require an explicit channel, exact destination/recipient, credential handling, retry/failure semantics, privacy rules, and a separately controlled live proof.

## Verified AI Agent Operations — ACTIVE

The governing [AI Agent Execution Contract V1](contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md) is locked and provider-neutral.

Immediate implementation target:

```text
AgentRequest
-> provider-neutral AgentExecutionBoundary
-> AI execution resource
-> raw AgentResult
-> independent Sentinel verification
-> evidence
-> accepted/rejected result
```

Required properties:

- explicit request, agent, and task identities;
- bounded time/retry/resource budgets;
- provider-neutral adapter boundary;
- failure/timeout/cancellation remain observable;
- result verification is independent from model output;
- AI-proposed consequential actions still pass through canonical policy, execution, and verification boundaries;
- no provider credential or live-provider activation is implied by the foundation work.

## Remediation levels

| Level | Meaning |
| --- | --- |
| L0 — OBSERVE | Read-only observation |
| L1 — DIAGNOSE | Investigation and evidence collection |
| L2 — AUTONOMOUS REMEDIATION | Explicit policy-controlled effect inside bounded capability |
| L3 — COMMANDER REQUIRED | Consequential effect requires Commander authority |

Gate 3 is **PASSED / LOCKED**. Gate 4 remains **BOUNDED** and does not create wildcard targets, general root automation, fabricated approval, or blind retry of indeterminate effects.

## GitHub Actions and host authority

Repository validation and privileged host effects are separate trust domains:

```text
Repository change
-> GitHub Actions validation
-> CI PASS
-> canonical main
-> separately authorized host/live workflow when required
-> trusted host boundary
-> independent verification
-> evidence
```

An ordinary push does not itself authorize a production effect.

## Installation guide

Standard installation preserves fail-closed defaults. It does **not** enable autonomous production remediation or external Commander delivery.

### Clone

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel-OSS.git "$HOME/airiv/airiv-sentinel"
cd "$HOME/airiv/airiv-sentinel"
```

The curated public distribution transforms this repository reference to `AIRIV-Sentinel-OSS`.

### Environment

```bash
python3.14 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-dev.txt
```

Dependencies are defined in [requirements-dev.txt](requirements-dev.txt).

### Validate

```bash
PYTHONPATH=. venv/bin/python -m compileall -q sentinel tests
python scripts/validate_project_docs.py
PYTHONPATH=. venv/bin/python -m pytest -q -p no:cacheprovider
bash scripts/public_release_secret_scan.sh
```

### Foreground smoke run

```bash
PYTHONPATH=. venv/bin/python -m sentinel
```

### systemd

Use the reviewed standard service template and deployment tooling for the target host. Production remediation and any future external-delivery enablement remain separate reviewed operations.

## Security boundary

See [SECURITY.md](SECURITY.md).

AIRIV Sentinel assumes that credentials, authorization state, production evidence, private host topology, and private release/deployment provenance are not public documentation. CI and curated-public validation guard against accidental disclosure.

## Roadmap lock

The [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md) is change-controlled. The following remain non-negotiable:

1. Commander is final strategic authority.
2. Fail-closed/default-deny behavior is mandatory.
3. Policy, execution, verification, outcome mapping, and lifecycle mutation remain exclusive boundaries.
4. Evidence and replay identity are mandatory for consequential effects.
5. AI output is never authority by itself.
6. Autonomous remediation expands only through explicit bounded contracts.
7. External delivery is disabled until an adapter and exact destination are explicitly reviewed.
8. Sentinel must not create a parallel AIRIV Event Bus or Job Worker.
9. Public distribution remains curated, not a private-history mirror.

## License

Apache License 2.0. See [LICENSE](LICENSE).
