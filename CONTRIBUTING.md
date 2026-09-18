# Contributing to AIRIV Sentinel

## Welcome

Thank you for helping improve AIRIV Sentinel. Contributions should preserve the repository's canonical contracts, safety boundaries, and fail-closed behavior.

## Development Environment

Use a supported Python environment and install the development dependencies:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements-dev.txt
```

Keep production services, credentials, host-local state, and live remediation outside ordinary development and CI workflows.

## Branch Strategy

Branch from the current `main` branch. Keep branches focused on one coherent change, rebase stale branches before integration, and avoid unrelated refactors.

## Commit Convention

Use concise, imperative commit subjects that describe the change. Keep each commit reviewable and avoid mixing implementation, unrelated cleanup, and generated artifacts.

## Coding Standards

Prefer simple, explicit Python consistent with nearby code. Preserve public APIs and canonical authority boundaries. Do not weaken fail-closed behavior, add undocumented side effects, commit secrets, or create backup files.

## Testing Requirements

Add focused behavioral tests for changed behavior. Run the narrowest relevant tests while iterating, then run the affected integration tests and the full required regression before requesting review. Tests must not perform live production remediation.

## Documentation Requirements

Update documentation when public behavior, configuration, contracts, setup, or operational expectations change. Keep examples accurate, sanitized, and free of credentials or private host details.

## Pull Request Process

Open a focused pull request against `main`. Describe the change, affected contracts and boundaries, test commands and results, configuration implications, and any remaining risks. Required CI checks must pass before merge.

## Code Review Expectations

Reviewers prioritize correctness, safety, authority boundaries, regression risk, evidence continuity, and test coverage. Address review findings explicitly and do not bypass failing checks or conceal consequential behavior.
