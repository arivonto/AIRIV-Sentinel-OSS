# AIRIV Sentinel

> **Clean open-source distribution.** Canonical operational provenance, private host evidence, private host-control material, and internal release-management history are intentionally excluded.

> **Fail-closed Autonomous Commander for the AIRIV development and runtime ecosystem.**

[![AIRIV Sentinel CI](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Platform Linux](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=000000)
![Runtime systemd](https://img.shields.io/badge/Runtime-systemd-5C2D91?logo=linux&logoColor=white)
![Safety Fail Closed](https://img.shields.io/badge/Safety-Fail--Closed-critical)
![Autonomy Bounded](https://img.shields.io/badge/Autonomy-Bounded-orange)
![Status Pre-release](https://img.shields.io/badge/Status-Pre--release-yellow)

## Project description

AIRIV Sentinel is a security-first autonomous operations commander for monitoring, incident management, policy-controlled remediation, independent verification, and auditable evidence. It is designed for continuous Linux operation and may execute consequential effects only inside explicit authority and safety boundaries.

**Repository status:** public source distribution / pre-release. This repository is synchronized through reviewed public snapshots and normal public commits; it does not mirror the private canonical engineering/operations history.

---

## Project lock and roadmap context

The project-level concept lock used to build **AIRIV Sentinel Roadmap** establishes these foundations:

- AIRIV Sentinel is the **Autonomous Commander** for the AIRIV development and runtime ecosystem.
- The human Commander retains final strategic authority.
- Safety is fail-closed / default-deny.
- Execution success alone is never recovery.
- Consequential recovery claims require independent verification and evidence.
- AI agents are execution resources; AI output is not semantic authority.
- Execution identity and replay protection are mandatory for consequential remediation.
- Production autonomy expands only through explicit bounded target/action contracts.
- GitHub Actions does not inherit general host/root authority.
- Sentinel remains external to AIRIV Server and does not replace its API, database authority, Event Bus, Job Worker, or business modules.

Canonical engineering rule:

> **Contract > Implementation > Local Preference**

Normative architecture and safety semantics are defined under [`contracts/`](contracts/).

---

## Core capabilities

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

---

## Authority and workflow

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

Repository-level operational pipeline:

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

Key invariants:

- `RemediationPolicy` owns canonical remediation ALLOW/DENY decisions.
- `ExecutionBoundary` is the sole command executor.
- `IncidentManager.resolve()` is the sole terminal lifecycle mutation authority.
- Unknown, stale, malformed, mismatched, exhausted, unsupported, concurrent, or unauthorized states fail closed.
- Sentinel must not manufacture Commander approval or broaden an exact target into wildcard authority.
- Uncertain execution outcomes must not be blindly replayed.

---

## Incident and execution identity

Canonical incident progression:

```text
OPEN → INVESTIGATING → RESOLVED
```

Consequential execution identity:

```text
CLAIMED → RUNNING → SUCCEEDED / FAILED / UNKNOWN
```

`UNKNOWN` is terminal. A normal observation does not silently erase an incident, and a successful command does not by itself prove recovery.

---

## Bounded production autonomy

AIRIV Sentinel supports bounded autonomous remediation under the applicable production-remediation contract. Public documentation intentionally describes the safety semantics without publishing private host enablement locations, runner identities, bridge/state directories, command-trigger refs, or production evidence locations.

A bounded autonomous profile requires, at minimum:

- exact target/action binding;
- positive cooldown;
- finite retry window;
- bounded attempts per window;
- bounded concurrency/blast radius;
- durable attempt accounting;
- execution identity and replay protection;
- independent post-effect verification;
- fail-closed behavior for unknown or indeterminate states.

There is no general “autonomous root” switch.

See [`contracts/SYSTEMD_PRODUCTION_BOUNDED_AUTONOMOUS_REMEDIATION_CONTRACT.md`](contracts/SYSTEMD_PRODUCTION_BOUNDED_AUTONOMOUS_REMEDIATION_CONTRACT.md).

---

## Runtime specification

| Property | Value |
| --- | --- |
| Service | `airiv-sentinel.service` |
| Entrypoint | `$REPO/venv/bin/python -m sentinel` |
| Worker ID | `sentinel.runtime` |
| Runtime cycle | `1.0` second |
| Health stale threshold | `30.0` seconds |
| Process manager | systemd |
| Restart model | on failure |
| Logging | systemd journal |
| Service umask | `0027` |

Standard service template: [`deployment/systemd/airiv-sentinel.service.in`](deployment/systemd/airiv-sentinel.service.in).

---

## Requirements

- Linux with systemd
- Git
- Python **3.14** with `venv` support
- non-root service account
- `sudo` only for explicitly reviewed service installation/administration

Development dependencies are in [`requirements-dev.txt`](requirements-dev.txt).

---

## Installation guide

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

### 4. Optional foreground run

```bash
PYTHONPATH=. venv/bin/python -m sentinel
```

Stop with `Ctrl+C` after confirming startup behavior.

### 5. Dry-run systemd installation

```bash
./scripts/install_systemd_service.sh \
  --repo "$PWD" \
  --python "$PWD/venv/bin/python"
```

### 6. Install and activate

After reviewing the dry run:

```bash
sudo ./scripts/install_systemd_service.sh \
  --apply \
  --user "$USER" \
  --repo "$PWD" \
  --python "$PWD/venv/bin/python"

sudo systemctl enable --now airiv-sentinel.service
systemctl status airiv-sentinel.service --no-pager
journalctl -u airiv-sentinel.service -f
```

### Safety default

Standard installation does **not** grant production-remediation authority. Do not create or copy production enablement/authorization material merely to turn autonomy on. Production enablement is a separate reviewed operational-security milestone.

---

## Validation

Public CI validates:

- tracked secret-bearing filename hygiene;
- reachable-history high-confidence credential patterns;
- patch hygiene;
- project documentation links and disclosure boundary;
- Python compilation;
- focused production Commander-boundary regression;
- full pytest regression.

CI success is strong evidence for tested behavior, but it is not a mathematical guarantee that no future defect or vulnerability can exist.

---

## Security and disclosure boundary

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability.

Never commit or publish credentials, API keys, access tokens, private keys, passwords, machine-specific secret configuration, host-local authorization state, or sensitive runtime evidence.

Public documentation intentionally avoids unnecessary disclosure of private host identities, user-specific absolute home paths, internal host-control state locations, internal command-trigger refs, and private infrastructure topology.

Security-sensitive reports must use private vulnerability reporting rather than public issues.

---

## Public distribution boundary

This repository contains source, contracts, standard deployment material, tests, and public engineering documentation. It intentionally excludes private canonical Git ancestry, private host-control/provenance material, production evidence, host-local configuration, and internal release-management history.

Publishing source code does not grant runtime, host, Commander, or production-remediation authority.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md).

Before proposing a change:

1. identify the applicable contract;
2. preserve authority boundaries and fail-closed behavior;
3. add focused behavioral coverage;
4. run the affected integration/regression tests;
5. run the full regression and security scan;
6. do not include secrets or private host data in issues, PRs, logs, screenshots, or fixtures.

---

## License

Copyright 2026 Boedi Arivianto Ontowiryo.

Licensed under the [Apache License 2.0](LICENSE).

---

**AIRIV Sentinel — observe, authorize, execute, verify, preserve evidence.**
