# Contributing to AIRIV Sentinel

Thank you for helping improve AIRIV Sentinel.

## Development principles

AIRIV Sentinel is safety-sensitive systems software. Contributions must preserve the canonical contracts and fail-closed production boundaries.

Before changing behavior:

1. Read the relevant files under `contracts/`.
2. Prefer the smallest complete change that preserves existing authority boundaries.
3. Add or update behavioral tests.
4. Do not weaken a safety invariant merely to make a test pass.
5. Keep production-host effects out of repository CI.

## Local setup

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel.git
cd AIRIV-Sentinel
python3.14 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-dev.txt
```

Run validation:

```bash
PYTHONPATH=. venv/bin/python -m compileall -q sentinel tests
PYTHONPATH=. venv/bin/python -m pytest -q -p no:cacheprovider
./scripts/public_release_secret_scan.sh
```

## Branches and pull requests

- Branch from `main`.
- Use a focused branch and focused commits.
- Keep unrelated refactors out of safety changes.
- Explain the affected contract, invariant, and test evidence in the pull request.
- GitHub Actions must pass before merge.

## Production and privileged behavior

A pull request must not rely on live production effects for ordinary validation. Tests should use controlled doubles/fakes unless a separately governed live-validation milestone explicitly requires host evidence.

Do not add:

- wildcard production remediation targets;
- implicit privilege expansion;
- fake Commander approval evidence;
- silent retries after indeterminate production effects;
- alternate execution paths that bypass canonical policy or verification;
- credentials, host secrets, or private environment data.

## Configuration examples

Public configuration belongs in example files such as `config/identities.example.yaml`. Machine-specific or confidential configuration must remain untracked.

## Backup files

Do not commit `.bak*`, `.pre_*`, `*.identity_backup*`, editor backups, or generated scratch copies. Git history is the source of historical versions.

## Security issues

Do not report vulnerabilities in a public issue. Follow [`SECURITY.md`](SECURITY.md).

## License

By contributing, you agree that your contribution is licensed under the Apache License 2.0, consistent with this repository's [`LICENSE`](LICENSE).
