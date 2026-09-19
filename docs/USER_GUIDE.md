# AIRIV Sentinel — User Guide

This guide covers normal operation of AIRIV Sentinel after installation.

## Prerequisites

- Linux system with systemd
- Python >= 3.12
- Git

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel-OSS.git
cd AIRIV-Sentinel-OSS
python3 -m venv venv
./venv/bin/python -m pip install -r requirements-dev.txt
```

## Quick Start

Run one runtime cycle against the demo queue:

```bash
./venv/bin/python runtime_cli.py demo_queue.yaml
```

Expected output: a concise status line and exit code `0` for success or `1` for failure.

## Verifying Sentinel Works

Run the test suite:

```bash
PYTHONPATH=. ./venv/bin/pytest -q -x tests/
```

All tests should pass.

## Basic Usage

### Running the Runtime CLI

The `runtime_cli.py` entry point executes one queue cycle:

```bash
./venv/bin/python runtime_cli.py <queue_file.yaml>
```

### Queue Files

Queue files define missions and tasks in YAML format. See `demo_queue.yaml` for an example and `queue_schema.yaml` for the canonical schema.

### Executor Adapters

Sentinel supports multiple executor backends:

- **Local** — execute commands directly on the host
- **Ollama** — generate responses via a local Ollama endpoint (default: `http://localhost:11434`)
- **Roo** — execute via the Roo adapter

Configure executors in your queue file or configuration.

## Checking Status

### Test Suite

```bash
PYTHONPATH=. ./venv/bin/pytest -q -x tests/test_*integration*.py
```

### CI

GitHub Actions runs the configured kernel and integration tests on pushes to `main` and pull requests. See the `Sentinel Kernel CI` workflow.

## Project Status

### Available Now

- Deterministic queue-driven task execution
- Local, Roo, and Ollama executor adapters
- Incident lifecycle management
- Remediation policy with fail-closed defaults
- Independent verification of consequential effects
- Durable execution identity with replay protection
- Evidence collection and preservation
- CI/CD with GitHub Actions

### In Development

- SLO enforcement (observation and classification complete; production integration planned)
- Expanded executor coverage
- Additional bounded task handlers

### Intentionally Not Available

- Unrestricted autonomous remediation
- Automatic retry of indeterminate effects
- Production activation without explicit Commander authority
- Cloud-dependent operation

## Safety Boundaries

AIRIV Sentinel is designed around these principles:

- **Fail closed.** Unknown or unauthorized state defaults to denial.
- **Commander authority.** Production-effect boundaries require explicit authorization.
- **No blind retry.** Indeterminate execution outcomes are terminal.
- **Bounded automation.** AI assists but does not replace policy or authority.

## Troubleshooting

### Common First-Run Issues

**"Python version not supported"**: Ensure Python >= 3.12 is installed.

**"Module not found"**: Run with `PYTHONPATH=.` or install dependencies from `requirements-dev.txt`.

**"Demo queue fails"**: Check that the queue file matches the schema in `queue_schema.yaml`.

## Reporting Issues

- Bug reports and feature requests: GitHub Issues
- Security vulnerabilities: See [SECURITY.md](SECURITY.md) — do not open public issues for security concerns

## Further Documentation

- [Architecture](docs/AIRIV_SENTINEL_V1_ARCHITECTURE.md)
- [Why AIRIV Sentinel](docs/WHY_AIRIV_SENTINEL.md)
- [Roadmap](AIRIV_SENTINEL_ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)
