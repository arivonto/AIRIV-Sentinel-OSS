# AIRIV Sentinel

> **Clean open-source distribution.** This repository is the curated public source domain. Canonical private Git ancestry, private host evidence, private host-control material, credentials, authorization material, and internal release provenance are intentionally excluded.

A Linux-first Autonomous Multi-AI Engineering Desktop with a deterministic, queue-driven execution core and configurable local and Ollama executor adapters.

```text
One Mission.
Any AI.
Linux First.
```

Canonical precedence: `Contract > Implementation > Local Preference`.

See the [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md) for the repository roadmap and status context.

## Project Overview

AIRIV Sentinel is a Python repository for bounded engineering task execution. Its current core loads a YAML queue, selects an executable task, dispatches one task through a configured executor, verifies the result, and persists the updated queue. The repository also contains broader contracts and implementation surfaces under `sentinel/`, but this README describes only the verified queue-driven core.

## Current Status

The repository has achieved:

- Proof of Life: a CLI can execute one queue cycle and report the result.
- CI: GitHub Actions runs the configured kernel and integration test suites on Python 3.12.
- Deterministic Core Runtime: queue loading, scheduling, worker dispatch, executor selection, execution results, verification, and queue persistence are implemented as explicit components.

This repository does not claim full autonomy.

## Core Architecture

```text
Queue
  |
  v
Scheduler
  |
  v
Worker
  |
  v
Executor Factory
  |
  +--> Local Executor
  |
  +--> Ollama Executor
  |
  v
Verifier
  |
  v
Queue Updated
```

`Runtime` coordinates one cycle. `ExecutorFactory` selects `local`, `roo`, or `ollama` from configuration. The Ollama adapter targets the local `http://localhost:11434` endpoint by default and uses the configurable `qwen3:4b` model default.

## Current Features

- Canonical YAML queue loading with mission and task validation.
- Explicit task identifiers, types, dependencies, status, success conditions, allowed files, and evidence fields.
- Deterministic task selection through the scheduler.
- Single-task worker dispatch and result collection.
- Executor selection for local, Roo, and Ollama adapters.
- Local Ollama HTTP generation requests with configurable endpoint and model.
- Structured execution and verification results.
- Queue status persistence after completion or failure.
- One-cycle command-line execution through `runtime_cli.py`.
- Focused unit and integration tests.
- GitHub Actions kernel and integration test verification with fail-fast pytest execution.

## Repository Structure

- `contracts/`: canonical project contracts and authority boundaries.
- `constitution/`: active constitution and policy documents.
- `sentinel/`: the broader Sentinel implementation packages.
- `tests/`: unit, integration, contract, and architecture tests.
- `.github/workflows/`: GitHub Actions workflows.
- `queue.py`, `scheduler.py`, `worker.py`, `executor.py`, `executor_factory.py`, `local_executor.py`, `ollama_executor.py`, and `verifier.py`: deterministic core components.
- `demo_queue.yaml` and `queue_schema.yaml`: queue example and canonical schema.
- `config/`: repository configuration examples and identity mappings.
- `docs/`: architecture and operational documentation.

## Quick Start

Create or activate a Python virtual environment, then install development dependencies:

```bash
python3 -m venv venv
./venv/bin/python -m pip install -r requirements-dev.txt
```

Run one runtime cycle against the demo queue:

```bash
./venv/bin/python runtime_cli.py demo_queue.yaml
```

The CLI prints a concise status line and returns `0` for a successful cycle or `1` for a failed or empty cycle.

## Testing

Run the focused kernel and integration tests locally:

```bash
PYTHONPATH=. ./venv/bin/pytest -q -x \
  tests/test_queue_loader_canonical_v1.py \
  tests/test_worker_v1.py \
  tests/test_verifier_v1.py \
  tests/test_executor_v1.py \
  tests/test_runtime_cli_v1.py \
  tests/test_local_executor_v1.py \
  tests/test_handler_registry_v1.py \
  tests/test_echo_handler_v1.py \
  tests/test_safety_gate_v1.py \
  tests/test_roo_executor_v1.py \
  tests/test_ollama_executor_v1.py \
  tests/test_executor_factory_v1.py \
  tests/test_runtime_executor_factory_v1.py

PYTHONPATH=. ./venv/bin/pytest -q -x tests/test_*integration*.py
```

## CI

The `Sentinel Kernel CI` workflow runs on pushes to `main` and pull requests. It installs the development dependencies with Python 3.12, runs the configured kernel tests, and then runs integration tests. Each pytest command uses `-x`, and any nonzero test result fails the workflow and therefore blocks a pull request from passing its CI check.

## Roadmap

### Implemented

- Canonical queue schema and loader.
- Deterministic scheduler, worker, verifier, and runtime cycle.
- Configurable local, Roo, and Ollama executor adapters.
- Executor factory wiring in Runtime.
- Runtime CLI and focused CI coverage.

### In Progress

- Aligning legacy tests and callers with the canonical queue schema.
- Expanding integration coverage for provider-configured execution paths.

### Planned

- Additional bounded task handlers and explicitly tested configuration flows.
- Further documentation of the canonical contracts and operational boundaries.

## Documentation

- [ARCHITECTURE.md](docs/AIRIV_SENTINEL_V1_ARCHITECTURE.md)
- [QUICKSTART.md](README.md#quick-start)
- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](https://github.com/arivonto/AIRIV-Sentinel-OSS/blob/main/CODE_OF_CONDUCT.md)

## License

AIRIV Sentinel is distributed under the [Apache License 2.0](LICENSE).
