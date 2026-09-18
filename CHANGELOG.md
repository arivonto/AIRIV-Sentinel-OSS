# Changelog

All notable changes to AIRIV Sentinel are documented in this file.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

Reserved for future development.

## [0.1.0-rc1]

### Added

- Canonical YAML queue schema and validated queue loader.
- Deterministic queue, scheduler, worker, executor, verifier, and runtime components.
- Runtime CLI for executing exactly one queue cycle.
- Local executor and handler registry.
- Roo executor adapter.
- Ollama executor adapter with configurable local endpoint and model.
- Executor factory supporting local, Roo, and Ollama executors.
- Focused unit and integration tests for the deterministic kernel.
- Public repository documentation, security policy, contribution guide, code of conduct, quick start, and architecture documentation.

### Changed

- Migrated the active runtime provider identity and configuration to Ollama-only support.
- Wired Runtime executor construction through ExecutorFactory.
- Added Python 3.12 GitHub Actions kernel and integration verification with fail-fast pytest execution.
- Documented the implemented runtime architecture, queue model, verified commands, and current limitations.

### Verified

- Proof of Life: `./venv/bin/python runtime_cli.py demo_queue.yaml` returns `STATUS=PASS` for the demo task.
- CI Green: the configured kernel and integration test commands pass locally and are configured as GitHub Actions checks.
- Zero Failing Tests: the verified kernel and integration test suites pass in the current validation run.

### Known Limitations

- Runtime executes one `run_once()` cycle per caller invocation; it is not a daemon or continuous loop.
- Planner logic and mission resume are not implemented in the deterministic runtime path.
- Ollama execution requires an available local Ollama endpoint for live requests.
- The canonical queue loader rejects legacy `id` and `name` task fields.
