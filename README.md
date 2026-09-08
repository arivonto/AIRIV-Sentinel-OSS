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
![Canonical Regression](https://img.shields.io/badge/Canonical%20Regression-2083%20passed-success)
![Public Regression](https://img.shields.io/badge/Public%20Regression-2067%20passed-success)
![Status Pre-release](https://img.shields.io/badge/Status-Pre--release-yellow)

## Project description

AIRIV Sentinel is a security-first autonomous operations commander for the AIRIV development and runtime ecosystem. It continuously observes system and workflow state, executes authorized actions, supervises AI-agent execution, verifies behavior against canonical contracts, manages incidents, preserves auditable evidence, operates as a 24/7 daemon, and performs autonomous remediation only inside explicit authority and safety boundaries.

**GitHub project description**

`Fail-closed autonomous operations commander for monitoring, incident management, policy-controlled remediation, verification, and auditable evidence.`

**Project state:** active V1 / pre-release. The V1 architecture is frozen and change-controlled. Post-freeze capability changes are valid only when they preserve canonical authority, safety, verification, evidence, and lifecycle boundaries.

---

## Repository domain topology — LOCKED

AIRIV Sentinel intentionally uses two GitHub project domains:

| Project domain | Access | Role | Content boundary |
| --- | --- | --- | --- |
| `AIRIV-Sentinel` | **Private** | **Canonical source** | Authoritative engineering source, canonical contracts, implementation, tests, private operational provenance, internal release/deployment material, and curated-distribution tooling |
| `AIRIV-Sentinel-OSS` | **Public** | **Curated open-source distribution** | Reviewed source, public contracts/docs, tests, standard deployment material, `README.md`, `index.html`, security/contribution files, and explicitly allowlisted content |

Locked publication rules:

1. `AIRIV-Sentinel` remains private and authoritative.
2. `AIRIV-Sentinel-OSS` is never produced by changing the canonical repository visibility.
3. Canonical private Git ancestry, private refs/tags, host-control material, private runtime evidence, credentials, authorization files, and private release provenance are not mirrored into this public domain.
4. Public synchronization is **allowlist-based and fail-closed**.
5. Both domains carry synchronized project-level `README.md` and `index.html`; this public copy is curated for the public security boundary.
6. Publishing source never grants runtime, production, host, Commander, or remediation authority.

This two-domain model is a locked input to **AIRIV Sentinel Roadmap**.

---

## Current project lock

- **Documentation lock date:** 2026-09-09
- **Target capability:** Autonomous Commander
- **Canonical domain:** `AIRIV-Sentinel` — Private / canonical source
- **Public domain:** `AIRIV-Sentinel-OSS` — Public / curated open-source distribution
- **License:** Apache License 2.0
- **Primary implementation language:** Python 3.14
- **Primary runtime platform:** Linux + systemd
- **Canonical validation:** 225 focused production-boundary tests + **2,083** full regression tests
- **Curated OSS validation:** 225 focused production-boundary tests + **2,067** public regression tests

| Area | Locked/current state |
| --- | --- |
| Mission | **LOCKED** — AIRIV Sentinel is the Autonomous Commander |
| Strategic authority | **LOCKED** — human Commander retains final strategic authority |
| Safety | **LOCKED** — fail-closed / default-deny |
| V1 architecture | **FROZEN** and change-controlled |
| Incident lifecycle | Centralized, monotonic, evidence-driven |
| Execution | Exact authorized effect only |
| Verification | Independent; execution success alone is never recovery |
| Evidence | Consequential facts remain observable and auditable |
| Gate 3 | **PASSED / LOCKED** controlled Commander-authorized production proof |
| Gate 4 | **BOUNDED** autonomous production-remediation profile |
| Host automation | Narrow trusted-host control plane; no general CI root authority |
| Distribution | Private canonical source + curated public source; no private-history mirroring |
| Release | Pre-release; stable public release/tag remains a separate milestone |

`README.md` and `index.html` are synchronized project-lock summaries used to prepare **AIRIV Sentinel Roadmap**. Normative authority remains in `contracts/`, frozen baseline records, implementation invariants, and verified evidence.

---

## Source-of-truth precedence

```text
Canonical contracts
    ↓
Frozen baseline / explicit change-control records
    ↓
Current implementation + behavioral tests + CI evidence
    ↓
README.md / index.html project summaries
    ↓
Local preference
```

> **Contract > Implementation > Local Preference**

If a project summary conflicts with a canonical contract, implementation invariant, or verified evidence, the summary must be corrected. A conflict must never be silently normalized.

---

## Concept evolution — initial agreement to current lock

AIRIV Sentinel evolved from continuous supervision into an Autonomous Commander by adding authority separation, verification, execution identity, evidence, replay protection, bounded production autonomy, and a clean public-distribution boundary. It did **not** evolve into unrestricted automation.

| Evolution stage | Agreed / changed | Current interpretation |
| --- | --- | --- |
| Initial supervisor concept | Continuous observation of AIRIV development activity, terminal/tmux state, failures, and unattended operation | Retained as monitoring foundation |
| 24/7 daemon foundation | systemd-backed continuous runtime, health, restart behavior, and persistent supervision | Retained and operationalized |
| Incident + evidence foundation | Incidents, diagnosis, actions, verification, and unattended timelines must be reconstructable | Evidence is operational truth |
| Remediation boundary | Remediation became deny-by-default, policy-controlled, verification-backed, and evidence-producing | Capability does not equal authority |
| Authority consolidation | Commander remains strategic authority; ChatGPT became AIRIV architecture + implementation authority; Gemini ceased to be a required development authority | Development flow no longer depends on Gemini |
| Autonomous Commander mission | System execution, workflow execution, AI-agent execution, contract verification, incident lifecycle, terminal access, and autonomous remediation became the target mission | **LOCKED target capability** |
| Commander orchestration | Semantic policy, intent, remediation policy, execution, verification, final outcome, and lifecycle mutation were separated into explicit authorities | Prevents duplicated/hidden authority |
| Execution identity | Consequential attempts gained durable identity, replay protection, and terminal uncertain-outcome semantics | Blind replay is prohibited |
| Gate 3 | Controlled real production remediation was proven through exact Commander authorization and independent verification | **PASSED / LOCKED** |
| Gate 4 | Autonomous production remediation was introduced only inside a deliberately narrow safety profile | **BOUNDED**, not general root autonomy |
| Trusted-host automation | GitHub coordination was separated from privileged host authority | CI does not inherit production authority |
| Two-domain distribution | Private canonical source and clean curated OSS distribution were separated | **LOCKED publication topology** |
| Documentation/security hardening | Public docs minimize unnecessary host topology and CI guards detect regression | Required for roadmap/release work |
| Dual-format synchronization | `README.md` and `index.html` are maintained in canonical source and curated for public distribution | **LOCKED documentation surface** |

---

## Mission and authority

Canonical mission contract: [`contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md).

### Core capabilities

1. System Monitoring
2. System Execution
3. Workflow Execution
4. AI Agent Execution
5. Contract Verification
6. Incident Lifecycle Management
7. Evidence Trail
8. 24/7 Daemon Operation
9. Full System Terminal Access
10. Authorized Autonomous Remediation

### Authority chain

```text
COMMANDER
    ↓
SENTINEL AUTHORITY POLICY
    ↓
AUTHORIZED EXACT EFFECT
    ↓
EXECUTION
    ↓
INDEPENDENT VERIFICATION
    ↓
EVIDENCE
    ↓
INCIDENT OUTCOME
```

The human Commander retains final strategic authority. Sentinel may act autonomously only inside an explicitly permitted policy and safety envelope. Technical access to shell, systemd, Git, filesystems, containers, databases, or other resources never grants semantic authority by itself.

---

## Locked architecture and workflow

```text
Observation
→ Investigation
→ Diagnosis
→ CommanderSemanticPolicy
→ CommanderIntentAssessment
→ CommanderIntentDecider
→ RemediationPolicy
→ RemediationActionCatalog
→ Execution
→ Verification
→ FinalOutcomeMapper
→ IncidentManager.resolve()
```

### Exclusive authority boundaries

| Boundary | Exclusive responsibility |
| --- | --- |
| Investigation | Incident investigation lifecycle |
| DiagnosisEvaluator | Diagnosis evaluation |
| CommanderSemanticPolicy | Semantic remediation facts |
| CommanderIntentDecider | Commander intent decision |
| RemediationPolicy | Canonical remediation **ALLOW / DENY** authority |
| RemediationActionCatalog | Action availability and command metadata only |
| ExecutionBoundary | Sole command executor |
| Verification | Independent post-effect proof |
| FinalOutcomeMapper | Sole final-outcome mapping |
| IncidentManager.resolve() | Sole terminal lifecycle mutation authority |
| CommanderHandoff | Context/handoff only; no policy, execution, or terminal lifecycle authority |

No duplicate policy evaluation, execution, verification, or terminal lifecycle mutation is permitted.

### Non-negotiable invariants

- Unknown, malformed, stale, mismatched, unauthorized, concurrent, exhausted, or unsupported conditions fail closed.
- Execution success is not equivalent to recovery.
- AI-agent output is untrusted execution input until independently verified.
- Evidence is operational truth, not optional logging.
- Sentinel must never manufacture Commander approval.
- Exact targets must never silently broaden into wildcard authority.
- Uncertain execution outcomes must not be blindly replayed.
- Sentinel remains external to AIRIV Server and must not replace its API, database authority, Event Bus, Job Worker, or business modules.

---

## Runtime specification

Canonical service: `airiv-sentinel.service`

Canonical package entrypoint:

```text
$REPO/venv/bin/python -m sentinel
```

| Runtime property | Current value |
| --- | --- |
| Worker ID | `sentinel.runtime` |
| Worker name | `Sentinel runtime` |
| Worker version | `1` |
| Daemon cycle interval | `1.0` second |
| Health stale threshold | `30.0` seconds |
| Process manager | systemd |
| Service restart | `Restart=on-failure`, `RestartSec=5` |
| Shutdown | `SIGTERM`, bounded stop timeout |
| Logging | systemd journal |
| Service umask | `0027` |
| V1 CLI surface | No broad runtime options; composition is explicit |

Standard service template: [`deployment/systemd/airiv-sentinel.service.in`](deployment/systemd/airiv-sentinel.service.in).

---

## Incident lifecycle, evidence, and execution identity

Canonical incident progression is monotonic:

```text
OPEN → INVESTIGATING → RESOLVED
```

Operational outcomes may include `RECOVERED`, `UNRESOLVED`, `ESCALATED`, or `INSUFFICIENT_EVIDENCE` according to the applicable boundary. A normal observation must never silently erase an existing incident.

For unattended operation, evidence must be sufficient to reconstruct incident identity/timing, observations, investigation, diagnosis, authorization, remediation actions, independent verification, Commander-required decisions, and final operational status.

Consequential execution identity follows durable replay-safe semantics:

```text
CLAIMED → RUNNING → SUCCEEDED / FAILED / UNKNOWN
```

`UNKNOWN` is terminal. An indeterminate effect is not automatically retried merely because a clean response was not observed.

---

## Remediation levels

| Level | Meaning |
| --- | --- |
| **L0 — OBSERVE** | Read-only observation |
| **L1 — DIAGNOSE** | Investigation and evidence collection |
| **L2 — AUTONOMOUS REMEDIATION** | Policy-controlled effect inside an explicit bounded capability |
| **L3 — COMMANDER REQUIRED** | Consequential effect requires explicit Commander authority |

### Gate 3 — controlled production proof

Gate 3 is **PASSED / LOCKED**. It proved a real dedicated production-remediation probe through exact Commander authorization, single-use continuity, execution, independent verification, evidence, and incident recovery.

### Gate 4 — bounded autonomous remediation

Gate 4 extends autonomy only through a narrow production-remediation profile enforcing exact target/action binding, cooldown, retry budget, bounded attempts/concurrency, durable accounting, replay protection, independent verification, and fail-closed behavior for unknown or indeterminate states.

Gate 4 does **not** create general root automation, wildcard targets, alternate effect verbs, fabricated Commander approval, or automatic retry of uncertain outcomes.

Private host enablement locations, dedicated runner identities, bridge/state paths, command-trigger refs, and production evidence locations are intentionally omitted from this public documentation.

---

## Requirements

- Linux with systemd
- Git
- Python **3.14** with `venv` support
- non-root service account
- `sudo` only for explicitly reviewed service installation/administration

Development dependencies are defined in [`requirements-dev.txt`](requirements-dev.txt).

---

## Installation guide

Standard installation preserves fail-closed defaults and does **not** enable production autonomous remediation.

### 1. Clone

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel-OSS.git "$HOME/airiv/airiv-sentinel"
cd "$HOME/airiv/airiv-sentinel"
```

### 2. Create the Python environment

```bash
python3.14 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-dev.txt
```

### 3. Validate the checkout

```bash
PYTHONPATH=. venv/bin/python -m compileall -q sentinel tests
python scripts/validate_project_docs.py
PYTHONPATH=. venv/bin/python -m pytest -q -p no:cacheprovider
bash scripts/public_release_secret_scan.sh
```

### 4. Optional foreground validation

```bash
PYTHONPATH=. venv/bin/python -m sentinel
```

Stop with `Ctrl+C` after confirming startup behavior.

### 5. Dry-run the systemd installation

```bash
./scripts/install_systemd_service.sh \
  --repo "$PWD" \
  --python "$PWD/venv/bin/python"
```

### 6. Install the service

After reviewing the dry run:

```bash
sudo ./scripts/install_systemd_service.sh \
  --apply \
  --user "$USER" \
  --repo "$PWD" \
  --python "$PWD/venv/bin/python"
```

### 7. Activate and verify

```bash
sudo systemctl enable --now airiv-sentinel.service
systemctl status airiv-sentinel.service --no-pager
journalctl -u airiv-sentinel.service -f
```

Do not create or enable production-remediation authorization/configuration merely to “turn autonomy on.” Production enablement is an explicit operational-security milestone governed by the applicable approved contract/runbook.

---

## Development and verification workflow

```text
Contract / architecture decision
        ↓
engineering/** branch
        ↓
small complete implementation slice
        ↓
focused behavioral tests
        ↓
integration / affected-boundary regression
        ↓
full regression + security/history scan + documentation guard
        ↓
canonical GitHub Actions PASS
        ↓
canonical main
        ↓
curated public snapshot validation
        ↓
AIRIV-Sentinel-OSS promotion
        ↓
public GitHub Actions PASS
        ↓
separately authorized host deployment/live validation when required
        ↓
runtime verification + evidence
```

### CI gates

| Surface | Focused tests | Full regression | Additional gates |
| --- | ---: | ---: | --- |
| `AIRIV-Sentinel` canonical | 225 | **2,083** | secret/history, docs, compile, curated-distribution packaging |
| `AIRIV-Sentinel-OSS` curated | 225 | **2,067** | secret/history, docs, compile |

CI passing is strong evidence for the tested boundaries; it is **not a mathematical guarantee that no future defect or vulnerability can exist**. Security-sensitive findings must be reported privately under [`SECURITY.md`](SECURITY.md).

---

## Repository layout

```text
AIRIV-Sentinel-OSS/
├── .github/                # Public CI and contribution templates
├── baseline/               # Public frozen V1 baseline records
├── config/                 # Non-secret repository configuration
├── contracts/              # Public canonical architecture/authority contracts
├── deployment/systemd/     # Standard Sentinel service template
├── docs/                   # Public architecture and operations docs
├── scripts/                # Public validation/install/security scripts
├── sentinel/               # Runtime implementation
├── tests/                  # Curated regression suite
├── AGENTS.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── index.html              # Curated visual project lock report
├── LICENSE
├── README.md               # Curated project and roadmap lock summary
├── SECURITY.md
└── requirements-dev.txt
```

Private operational/release-control material is deliberately absent from this curated distribution.

---

## AIRIV Sentinel Roadmap handoff — locked inputs

The future **AIRIV Sentinel Roadmap** must treat these as settled foundation unless an explicit strategic architecture decision changes them:

1. Sentinel is the AIRIV Autonomous Commander and remains external to AIRIV Server.
2. Commander retains final strategic authority.
3. Safety remains fail-closed / default-deny.
4. `RemediationPolicy` remains canonical remediation ALLOW/DENY authority.
5. `ExecutionBoundary` remains the sole command executor.
6. Terminal incident mutation remains centralized in `IncidentManager.resolve()`.
7. Consequential recovery claims require independent post-effect verification.
8. Evidence remains observable, durable, reconstructable, and auditable.
9. AI agents are execution resources; AI output is not semantic authority.
10. Execution identity, replay protection, and terminal uncertain-outcome handling are mandatory.
11. Autonomy expands only through explicit bounded target/action contracts, never wildcard authority.
12. Gate 4 production autonomy remains deliberately narrow until an explicit safety/architecture decision expands it.
13. CI/self-hosted automation crosses a narrow trusted-host boundary for privileged effects; runners do not gain general root authority.
14. Deployment remains clean-worktree, fast-forward-only, exact-main, verified, and evidence-producing.
15. Sentinel may integrate with the canonical AIRIV Event + Job Foundation but must not invent a parallel Event Bus or domain authority.
16. `AIRIV-Sentinel` remains the **Private canonical source** domain.
17. `AIRIV-Sentinel-OSS` remains the **Public curated open-source distribution** domain with independent public history.
18. Public synchronization remains fail-closed and allowlisted; no broad cross-repository write credential is introduced merely for convenience.
19. Both domains maintain synchronized `README.md` and `index.html`, with public-safe transformations and disclosure validation.
20. Public documentation minimizes private topology and operational details not required for safe use.

### Roadmap candidates — not yet commitments

- additional production targets only with explicit per-target safety profiles;
- richer durable evidence indexing, retention, querying, and unattended timelines;
- improved Commander handoff and unattended-incident summaries;
- verified AI-agent/provider integrations without granting semantic authority;
- canonical AIRIV Event + Job adapter integration after its contract boundary is ready;
- hardened packaging, installation, upgrade, rollback, and release automation;
- controlled promotion of validated curated public snapshots;
- fleet/multi-host support only after host identity, authority, and evidence semantics are contracted;
- improved metrics, health, observability, and recovery without weakening lifecycle authority.

---

## Security

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability.

Never place credentials, API keys, tokens, private keys, passwords, confidential host data, private host topology, production evidence, exploit instructions, or authorization material in public issues, pull requests, documentation, screenshots, logs, examples, or test fixtures.

Repository security controls include:

- fail-closed remediation architecture;
- minimal GitHub Actions permissions;
- history-aware high-confidence secret scanning;
- secret-bearing filename rejection;
- curated public-distribution allowlisting;
- Markdown/HTML documentation validation;
- public disclosure guard;
- independent private/public Git histories;
- narrow trusted-host privilege boundaries;
- exact-effect authorization, replay protection, and independent verification.

> **What the system claims happened must be supported by observable evidence and conform to the applicable canonical contract.**

---

## License

Copyright 2026 Boedi Arivianto Ontowiryo.

Licensed under the [Apache License 2.0](LICENSE).

---

**AIRIV Sentinel — observe, authorize, execute, verify, preserve evidence.**
