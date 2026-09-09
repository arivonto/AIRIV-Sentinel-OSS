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
![Canonical Regression](https://img.shields.io/badge/Canonical%20Regression-2252%20passed-success)
![Public Regression](https://img.shields.io/badge/Public%20Regression-2236%20passed-success)
![Status Pre-release](https://img.shields.io/badge/Status-Pre--release-yellow)

## Project lock — 2026-09-09

AIRIV Sentinel is a security-first autonomous operations commander. It observes runtime state, manages incidents, preserves auditable evidence, executes only explicitly authorized effects, independently verifies consequential outcomes, and performs autonomous remediation only inside bounded policy and safety contracts.

**Canonical precedence:** `Contract > Implementation > Local Preference`. The roadmap sequences work beneath this precedence and cannot override a contract or verified implementation fact.

| Item | Locked / verified state |
| --- | --- |
| Target | **Autonomous Commander** |
| Strategic authority | Human Commander remains final strategic authority |
| Safety | **Fail closed / default deny** |
| V1 architecture | **FROZEN / change-controlled** |
| Runtime | Linux + systemd + Python 3.14 |
| Canonical regression | **225 focused + 2,252 full PASS** |
| Curated public regression | **225 focused + 2,236 full PASS** |
| Canonical-public regression delta | **16 private-only tests** |
| Operational Evidence & Commander UX | **CORE COMPLETE** |
| Commander Delivery Transport Foundation | **COMPLETE** |
| Provider-neutral AI execution & replay | **CORE COMPLETE** |
| Release planning / artifact provenance / post-upgrade verification | **CORE COMPLETE — READ ONLY** |
| Observability, SLO & Recovery Hardening | **PASSIVE FOUNDATION CORE ADVANCED** |
| External Commander delivery | **DECISION-GATED / DISABLED** |
| Live AI provider / credentials / outbound network | **DECISION-GATED / DISABLED** |
| Upgrade / rollback execution | **NOT AUTHORIZED** |
| Gate 3 | **PASSED / LOCKED** |
| Gate 4 | **BOUNDED** autonomous production-remediation profile |
| Release | Pre-release |

Validated implementation heads for this project lock:

- canonical: `8559fd14939f65d3647cd9d9fbfe33694162e738`;
- curated public: `0c0d121a074644080a159f6c4844ca693934e1fe`.

See [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md) and the [project dashboard](index.html).

## Repository topology — LOCKED

| Domain | Role | Boundary |
| --- | --- | --- |
| `AIRIV-Sentinel` | Private canonical source | contracts, implementation, tests, private operational/release/host provenance and release tooling |
| `AIRIV-Sentinel-OSS` | Curated public source | explicitly allowlisted reviewed source, contracts, docs, tests and standard deployment material |

The public repository is **not** a mirror of private Git ancestry. Publication is allowlist-based, secret-scanned, disclosure-validated and fail-closed. Publishing source grants no runtime, production, Commander or remediation authority.

## Mission and authority

Canonical mission: [AIRIV Sentinel Mission Contract V1](contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md).

```text
COMMANDER
  -> SENTINEL AUTHORITY POLICY
  -> AUTHORIZED EXACT EFFECT
  -> EXECUTION
  -> INDEPENDENT VERIFICATION
  -> EVIDENCE
  -> INCIDENT OUTCOME
```

Non-negotiable boundaries:

- `RemediationPolicy` is the canonical remediation ALLOW/DENY authority.
- `ExecutionBoundary` is the sole command-execution boundary.
- `IncidentManager.resolve()` is the sole terminal Incident lifecycle mutation boundary.
- independent verification is required for consequential success claims;
- AI output is an untrusted execution/intelligence resource, never semantic authority;
- observability is passive and cannot become policy, execution, recovery or lifecycle authority;
- release planning and release validation cannot authorize repository mutation, deployment, restart or rollback;
- incomplete post-upgrade observation remains `UNKNOWN` and cannot authorize rollback;
- malformed, stale, mismatched, unauthorized or indeterminate effects fail closed;
- terminal uncertainty is never blindly retried.

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

No duplicate policy evaluation, execution, verification or terminal lifecycle mutation is permitted.

## Runtime specification

Canonical foreground entrypoint:

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

Template: [airiv-sentinel.service.in](deployment/systemd/airiv-sentinel.service.in).

## Operational Evidence & Commander UX — CORE COMPLETE

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

The evidence/reporting lane is append-retentive, reconstructable and non-authoritative. Reporting failure cannot silently broaden policy or disable the canonical remediation pipeline.

## Commander Delivery Transport Foundation — COMPLETE

Delivery identity, destination/transport continuity, replay suppression, `SUCCEEDED / FAILED / UNKNOWN`, sanitized failures and deterministic no-network proof are established. Production default is disabled/no-send and daemon execution does not auto-send.

**External network delivery remains disabled.** A live adapter requires separate channel/destination, credential, disclosure, acknowledgement, duplicate-suppression and controlled-live-proof review.

## Verified AI Agent Operations — PROVIDER-NEUTRAL FOUNDATION CORE COMPLETE

Governing contract: [AI Agent Execution Contract V1](contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md).

```text
AgentRequest
-> AgentExecutionBoundary
-> replaceable AI execution resource
-> RawAgentResult
-> independent Sentinel verifier
-> append-oriented evidence
-> accepted / rejected result
```

The foundation provides durable `CLAIMED / RUNNING / SUCCEEDED / FAILED / UNKNOWN` identity, exact request binding, replay suppression, metadata-only persistence and deterministic local no-network proof. The AI resource owns **no** policy, lifecycle, contract, shell, Commander or remediation authority. Live provider activation remains decision-gated.

## Release / Upgrade / Rollback Planning & Verification — READ-ONLY CORE COMPLETE

Implementations:

- [release_planning.py](sentinel/release_planning.py)
- [release_artifact_validation.py](sentinel/release_artifact_validation.py)
- [upgrade_verification.py](sentinel/upgrade_verification.py)

```text
ReleaseArtifactManifest + UpgradeRepositoryFacts
-> UpgradePreflight
-> READY / NOT_READY
-> immutable UpgradePlan
-> rollback candidate = UNAUTHORIZED / non-executable

ReleaseArtifactManifest + exact observed artifact facts
-> ReleaseArtifactValidator
-> VERIFIED / REJECTED
-> immutable ReleaseArtifactProvenance

UpgradePlan + Manifest + Provenance + post-upgrade observation
-> PostUpgradeVerifier
-> VERIFIED / FAILED / UNKNOWN
-> rollback_authorized = false
```

The foundation performs no Git mutation, service restart, deployment or rollback. Existing trusted-host deployment remains a separate fast-forward-only authority boundary.

## Observability, SLO & Recovery Hardening — PASSIVE FOUNDATION CORE ADVANCED

Governing contracts:

- [Observability Foundation V1](contracts/AIRIV_SENTINEL_OBSERVABILITY_FOUNDATION_CONTRACT_V1.md)
- [Metrics & Reconciliation V1](contracts/AIRIV_SENTINEL_OBSERVABILITY_METRICS_RECONCILIATION_CONTRACT_V1.md)
- [Attention, Delivery & AI Health V1](contracts/AIRIV_SENTINEL_OBSERVABILITY_ATTENTION_DELIVERY_AI_HEALTH_CONTRACT_V1.md)
- [Release & Upgrade Health V1](contracts/AIRIV_SENTINEL_OBSERVABILITY_RELEASE_UPGRADE_HEALTH_CONTRACT_V1.md)

Completed passive slices:

1. worker liveness/staleness projection preserving `UNKNOWN / HEALTHY / UNHEALTHY / STALE`;
2. incident/remediation outcome metrics from existing facts;
3. reconciliation health without recovery or mutation;
4. Commander attention backlog projection;
5. delivery identity/backlog health projection;
6. AI execution identity/verifier health projection;
7. release-preflight readiness projection;
8. release-artifact validation health projection;
9. post-upgrade verification health projection;
10. explicit duplicate/missing/unknown accounting and rollback-authority-integrity detection.

Observability output is diagnostic only. `DEGRADED`, `STALE`, `FAILED`, `NOT_READY` or `UNKNOWN` **never** grants remediation, deployment, restart, provider, rollback or lifecycle authority.

Remaining safe work before normative SLOs:

- recovery/failure-injection evidence foundation;
- bounded resource-use measurements;
- restart/upgrade continuity evidence hardening;
- measurement trust/stability evaluation;
- non-enforcing SLO definitions only after the metrics are demonstrably trustworthy.

## Remediation levels

| Level | Meaning |
| --- | --- |
| L0 — OBSERVE | read-only observation |
| L1 — DIAGNOSE | investigation and evidence collection |
| L2 — AUTONOMOUS REMEDIATION | explicitly bounded policy-controlled effect |
| L3 — COMMANDER REQUIRED | consequential effect requiring Commander authority |

Gate 3 is **PASSED / LOCKED**. Gate 4 remains **BOUNDED**; it creates no wildcard targets, general root automation, fabricated approval or blind retry of uncertain effects.

## GitHub Actions and host authority

```text
Repository change
-> GitHub Actions validation
-> CI PASS
-> canonical maik
-> separately authorized host/live workflow when required
-> trusted host boundary
-> independent verification
-> evidence
```

An ordinary push does not authorize a production effect. Documentation, observability and curated-source promotions do not themselves restart the Sentinel host.

## Installation guide

Standard installation preserves fail-closed defaults. It does not enable autonomous production remediation, external Commander delivery, a live AI provider, or upgrade/rollback execution.

### Clone

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel-OSS.git "$HOME/airiv/airiv-sentinel"
cd "$HOME/airiv/airiv-sentinel"
```

The curated public distribution transforms the repository reference to `AIRIV-Sentinel-OSS`.

### Environment

```bash
python3.14 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-dev.txt
```

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

Use the reviewed standard systemd template for service installation. Production remediation, external delivery, live AI-provider enablement and any future rollback execution remain separate reviewed operations.

## Security boundary

See [SECURITY.md](SECURITY.md).

Credentials, authorization state, production evidence, private host topology and private release/deployment provenance are excluded from public documentation. CI and curated-public validation guard the disclosure boundary.

## Roadmap lock

The [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md) is change-controlled. These remain non-negotiable:

1. Commander is final strategic authority.
2. Fail-closed/default-deny behavior is mandatory.
3. Policy, execution, verification, outcome mapping and lifecycle mutation remain exclusive boundaries.
4. Evidence and replay identity are mandatory for consequential effects.
5. AI output is never authority by itself.
6. Observability is never effect authority.
7. Autonomous remediation expands only through explicit bounded contracts.
8. External delivery and live AI providers remain disabled until explicitly reviewed.
9. Release planning, artifact validation and post-upgrade verification never imply upgrade or rollback execution authorization.
10. Incomplete post-upgrade observation remains `UNKNOWN`; it never authorizes blind retry or rollback.
11. Sentinel must not create a parallel AIRIV Event Bus or Job Worker.
12. Public distribution remains curated, not a private-history mirror.

## License

Apache License 2.0. See [LICENSE](LICENSE).
