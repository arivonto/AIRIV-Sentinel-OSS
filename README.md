# AIRIV Sentinel

> **Clean open-source distribution.** Canonical operational provenance, private host evidence, and internal release-management history are intentionally excluded from this repository.

> **Fail-closed Autonomous Commander for the AIRIV development and runtime ecosystem.**

[![AIRIV Sentinel CI](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Platform Linux](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=000000)
![Runtime systemd](https://img.shields.io/badge/Runtime-systemd-5C2D91?logo=linux&logoColor=white)
![Safety Fail Closed](https://img.shields.io/badge/Safety-Fail--Closed-critical)
![Remediation Bounded Autonomy](https://img.shields.io/badge/Remediation-Bounded%20Autonomy-orange)
![Status Pre-release](https://img.shields.io/badge/Status-Pre--release-yellow)

AIRIV Sentinel continuously observes the AIRIV environment, executes approved workflows and system actions, supervises AI-agent execution, verifies behavior against canonical contracts, manages incidents, preserves evidence, operates as a 24/7 daemon, and supports policy-controlled autonomous remediation.

Sentinel is intentionally **fail-closed**. Runtime capability does not equal authority: consequential effects must pass the applicable policy, exact binding, execution, independent verification, evidence, and incident-lifecycle boundaries.

## Project status

AIRIV Sentinel is under active V1 development. Repository CI validates the codebase, architecture boundaries, production Commander path, full regression suite, repository hygiene, and high-confidence reachable-history secret patterns. A stable public release tag has not yet been published.

## Badge details

| Badge | Meaning |
| --- | --- |
| **AIRIV Sentinel CI** | Live GitHub Actions status for `.github/workflows/ci.yml` on `main`. |
| **Apache-2.0** | Source is licensed under the Apache License 2.0. |
| **Python 3.14** | Canonical CI/runtime Python generation. |
| **Linux** | Sentinel targets Linux host environments. |
| **systemd** | Production daemon deployment uses systemd. |
| **Fail-Closed** | Unknown, malformed, stale, mismatched, unauthorized, or exhausted conditions deny consequential effects. |
| **Bounded Autonomy** | Autonomous production remediation is constrained by exact target/action binding, policy, cooldown, retry budget, blast radius, and independent verification. |
| **Pre-release** | No stable public version tag has been published yet. |

## Mission

The canonical mission is defined in [`contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md).

Core capabilities:

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

Commander retains final strategic authority. Autonomous behavior is valid only inside explicitly authorized policy boundaries.

### Canonical authority chain

```text
COMMANDER
    ↓
SENTINEL AUTHORITY POLICY
    ↓
AUTHORIZED ACTION
    ↓
EXECUTION
    ↓
VERIFICATION
    ↓
EVIDENCE
```

For remediation:

```text
COMMANDER
    ↓
SENTINEL AUTHORITY POLICY
    ↓
OBSERVE → DETECT → DIAGNOSE → AUTHORIZE
    ↓
REMEDIATE → VERIFY → EVIDENCE
```

## Architecture overview

```text
┌──────────────────────────────────────────────────────────────┐
│                        Commander                             │
│               strategic / final authority                   │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    Sentinel Runtime                          │
│  monitoring • workflows • AI agents • incidents • evidence  │
└───────────────┬───────────────────────────────┬──────────────┘
                │                               │
                ▼                               ▼
        Observe / Diagnose               Contract / Policy
                │                               │
                └──────────────┬────────────────┘
                               ▼
                     Prepared Exact Effect
                               │
                               ▼
                     Execution Boundary
                               │
                               ▼
                  Independent Verification
                               │
                               ▼
                    Evidence + Incident
```

Key architectural rules:

- **Contract > Implementation > Local Preference**.
- `RemediationPolicy` is the canonical remediation ALLOW/DENY authority.
- Execution success alone is **not** recovery.
- Consequential operations must produce evidence.
- Failures must not be concealed or silently rewritten.
- AI-agent output is execution input, not semantic authority.
- Sentinel is external to AIRIV Server and does not replace its API, database authority, Event Bus, Job Worker, or business modules.

## Incident lifecycle

Canonical progression is monotonic:

```text
OPEN → INVESTIGATING → RESOLVED
```

Operational outcomes may additionally record recovered, unresolved, escalated, or insufficient-evidence states according to the applicable boundary. A normal observation does not silently erase an existing incident.

## Remediation levels

| Level | Meaning |
| --- | --- |
| **L0 — OBSERVE** | Read-only observation. |
| **L1 — DIAGNOSE** | Investigation and evidence collection. |
| **L2 — AUTONOMOUS REMEDIATION** | Policy-controlled autonomous effect within an explicit bounded capability. |
| **L3 — COMMANDER REQUIRED** | Effect requires explicit Commander authority. |

## Gate 4 — bounded autonomous production remediation

Canonical contract: [`contracts/SYSTEMD_PRODUCTION_BOUNDED_AUTONOMOUS_REMEDIATION_CONTRACT.md`](contracts/SYSTEMD_PRODUCTION_BOUNDED_AUTONOMOUS_REMEDIATION_CONTRACT.md).

### V1 exact boundary

| Property | Value |
| --- | --- |
| Target | `airiv-sentinel-production-remediation-probe.service` |
| Action | `RESTART` |
| Exact argv | `/usr/bin/systemctl --no-ask-password restart airiv-sentinel-production-remediation-probe.service` |
| Target mode | `AUTONOMOUS` |
| Cooldown | `3600` seconds |
| Retry window | `86400` seconds |
| Maximum attempts/window | `1` |
| Concurrent production effects | At most `1` |
| Verification | Unit loaded + active/running + InvocationID changed |

Gate 4 does **not** grant broad systemd autonomy. Wildcards, templates, aliases, alternate verbs, inferred dependencies, additional targets, and fake Commander approvals are prohibited.

### Trusted host enablement boundary

Repository defaults remain disabled unless the trusted host configuration exists at:

```text
/etc/airiv-sentinel/gate4-bounded-autonomous.json
```

The loader requires:

- parent directory root-owned, mode `0755`;
- config file root-owned, regular file, mode `0644`, one hardlink;
- byte-for-byte canonical JSON;
- exact target and exact bounded values.

Canonical payload:

```json
{"cooldown_seconds":3600.0,"enabled":true,"max_attempts_per_window":1,"retry_window_seconds":86400.0,"schema":"airiv-sentinel-gate4-bounded-autonomous-enablement","schema_version":1,"unit":"airiv-sentinel-production-remediation-probe.service"}
```

The file must match the canonical serialized form exactly, including **no trailing newline**. Basic installation must not create this file automatically.

## Requirements

### Host

- Linux with systemd
- Git
- Python **3.14** with `venv` support
- A non-root service account

### Python dependencies

Development/test dependencies are defined in [`requirements-dev.txt`](requirements-dev.txt):

- `pytest >= 8.4, < 9`
- `PyYAML >= 6.0, < 7`

## Installation

The following procedure installs Sentinel from source while preserving fail-closed defaults.

### 1. Clone

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel-OSS.git ~/airiv/airiv-sentinel
cd ~/airiv/airiv-sentinel
```

### 2. Create the Python environment

```bash
python3.14 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-dev.txt
```

The systemd renderer defaults to `repo/venv/bin/python`.

### 3. Validate the checkout

```bash
PYTHONPATH=. venv/bin/python -m compileall -q sentinel tests
PYTHONPATH=. venv/bin/python -m pytest -q -p no:cacheprovider
bash scripts/public_release_secret_scan.sh
```

### 4. Optional foreground run

```bash
PYTHONPATH=. venv/bin/python -m sentinel
```

Stop with `Ctrl+C` after validating startup.

### 5. Dry-run systemd installation

```bash
./scripts/install_systemd_service.sh \
  --repo "$PWD" \
  --python "$PWD/venv/bin/python"
```

The installer is dry-run by default and does not modify the host.

### 6. Install the systemd unit

After reviewing the dry run:

```bash
sudo ./scripts/install_systemd_service.sh \
  --apply \
  --user "$USER" \
  --repo "$PWD" \
  --python "$PWD/venv/bin/python"
```

This installs `/etc/systemd/system/airiv-sentinel.service` and reloads systemd definitions. Service activation is intentionally separate.

### 7. Inspect and activate

```bash
systemctl cat airiv-sentinel.service
sudo systemctl enable --now airiv-sentinel.service
systemctl status airiv-sentinel.service --no-pager
```

### 8. Logs

```bash
journalctl -u airiv-sentinel.service -f
```

### 9. Verify default remediation safety

A normal installation must not create the Gate 4 enablement file:

```bash
test ! -e /etc/airiv-sentinel/gate4-bounded-autonomous.json
```

Absence means bounded autonomous production remediation remains disabled.

## systemd deployment model

Canonical template: [`deployment/systemd/airiv-sentinel.service.in`](deployment/systemd/airiv-sentinel.service.in).

Key properties:

- `Type=simple`
- non-root `User=` / `Group=`
- repository-bound `WorkingDirectory=`
- `python -m sentinel`
- `Restart=on-failure`
- `RestartSec=5`
- `SIGTERM` shutdown
- journal stdout/stderr
- `PYTHONUNBUFFERED=1`
- `UMask=0027`

Use [`scripts/render_systemd_service.sh`](scripts/render_systemd_service.sh) to render without host modification and [`scripts/install_systemd_service.sh`](scripts/install_systemd_service.sh) for the guarded installation path.

## Development and CI

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

CI runs on pull requests to `main` and pushes to `main` or `engineering/**`.

The gate performs:

1. full-history checkout;
2. public-release repository hygiene and high-confidence secret/history scan;
3. Python 3.14 setup;
4. dependency installation;
5. patch-hygiene validation;
6. compile validation;
7. focused production Commander-boundary regression;
8. full pytest regression.

Recommended workflow:

```text
Contract / Architecture
        ↓
engineering/** branch
        ↓
Implementation + Tests
        ↓
GitHub Actions
        ↓
CI PASS
        ↓
main
        ↓
Exact-SHA Host Deployment
        ↓
Runtime Verification
```

Hosted CI proves repository behavior; it does not prove the state of a specific production host.

## Repository layout

```text
AIRIV-Sentinel/
├── .github/                # CI and contribution templates
├── baseline/               # Baseline/reference material
├── config/                 # Runtime identity/configuration data
├── contracts/              # Canonical architecture and authority contracts
├── deployment/systemd/     # systemd service template
├── docs/                   # Architecture, operations, release-readiness docs
├── release/                # Validation/release-candidate records
├── scripts/                # Validation, security, and deployment helpers
├── sentinel/               # Sentinel runtime implementation
├── tests/                  # Regression and architecture tests
├── AGENTS.md                # Public engineering guidance
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── SECURITY.md
└── requirements-dev.txt
```

## Canonical specifications

Start with:

- [`AIRIV_SENTINEL_MISSION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md) — mission, authority, capabilities, lifecycle, safety.
- [`AIRIV_SENTINEL_COMMANDER_ORCHESTRATION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_COMMANDER_ORCHESTRATION_CONTRACT_V1.md) — Commander orchestration boundary.
- [`AIRIV_SENTINEL_DIAGNOSTIC_ENGINE_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_DIAGNOSTIC_ENGINE_CONTRACT_V1.md) — diagnostic engine semantics.
- [`AIRIV_SENTINEL_EXECUTION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_EXECUTION_CONTRACT_V1.md) — execution boundary.
- [`AIRIV_SENTINEL_WORKFLOW_EXECUTION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_WORKFLOW_EXECUTION_CONTRACT_V1.md) — workflow execution.
- [`AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md) — AI-agent execution.
- [`AIRIV_SENTINEL_REMEDIATION_POLICY_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_REMEDIATION_POLICY_CONTRACT_V1.md) — remediation policy authority.
- [`AIRIV_SENTINEL_REMEDIATION_VERIFICATION_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_REMEDIATION_VERIFICATION_CONTRACT_V1.md) — post-effect verification.
- [`AIRIV_SENTINEL_SYSTEMD_CONTRACT_V1.md`](contracts/AIRIV_SENTINEL_SYSTEMD_CONTRACT_V1.md) — systemd boundary.
- [`SYSTEMD_PRODUCTION_BOUNDED_AUTONOMOUS_REMEDIATION_CONTRACT.md`](contracts/SYSTEMD_PRODUCTION_BOUNDED_AUTONOMOUS_REMEDIATION_CONTRACT.md) — Gate 4 bounded autonomy.

Contracts are normative. If a README summary conflicts with a canonical contract, the contract wins.

## Security

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability. Do not place vulnerability details, credentials, tokens, private keys, or confidential host information in public issues or pull requests.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Safety-sensitive changes must identify the affected contract/authority boundary and include behavioral verification.

## License

Copyright 2026 Boedi Arivianto Ontowiryo.

Licensed under the [Apache License 2.0](LICENSE).

The Apache license covers the source and documentation in this repository. It does not grant trademark rights beyond the license's customary origin-description provisions.

## Safety principles

AIRIV Sentinel must not:

- conceal failures;
- destroy or silently rewrite evidence;
- declare success without verification;
- silently change architecture or canonical contracts;
- grant itself additional authority;
- bypass Commander approval when Commander authority is required;
- broaden an exact remediation target into a wildcard capability;
- treat execution success as equivalent to verified recovery.

> **What the system claims happened must be supported by observable evidence and conform to the applicable canonical contract.**

## AIRIV boundary

AIRIV Sentinel is an operational commander/supervisor for the AIRIV ecosystem. It remains architecturally external to AIRIV Server and does not replace business-platform authority or domain infrastructure.

**AIRIV Sentinel — observe, authorize, execute, verify, preserve evidence.**
