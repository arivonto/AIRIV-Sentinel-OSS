# Security Policy

AIRIV Sentinel can perform consequential host operations when explicitly configured and authorized. Security reports must therefore be handled conservatively.

## Supported versions

Security fixes are applied to the current `main` branch and to explicitly published supported releases. Pre-release development snapshots are not guaranteed long-term support.

## Reporting a vulnerability

Do **not** open a public issue for a vulnerability, suspected credential exposure, authorization bypass, unsafe remediation path, privilege-escalation issue, evidence-integrity issue, or production-effect binding weakness.

Use GitHub private vulnerability reporting from the repository **Security** tab when available. If that channel is unavailable, contact the repository maintainer privately through the GitHub account that owns this repository before disclosing technical details.

A useful report includes:

- affected commit or release;
- affected component and boundary;
- prerequisites and threat model;
- minimal reproduction steps;
- expected vs. observed authorization behavior;
- whether a real host effect occurred;
- relevant logs/evidence with secrets removed;
- suggested mitigation, if known.

## Security invariants

AIRIV Sentinel is designed around these invariants:

- fail closed on unknown, malformed, stale, mismatched, exhausted, or unauthorized production state;
- `RemediationPolicy` remains the canonical remediation ALLOW/DENY authority;
- execution success is not equivalent to recovery;
- consequential effects require exact binding and independent verification;
- evidence must not be silently destroyed or rewritten;
- Commander-required effects must not be impersonated by autonomous code;
- production autonomy must remain bounded by explicit target/action rules, cooldown, retry budget, and blast-radius controls.

A report showing violation of any of these invariants should be treated as security-sensitive.

## Secrets

Never commit credentials, API keys, tokens, private keys, production secrets, or host-specific confidential configuration. The repository CI includes a history-aware high-confidence secret scan, but automated scanning is not a substitute for credential hygiene.

If a secret is committed, assume it is compromised: revoke/rotate it first, then remediate repository history as appropriate.

## Public disclosure

Please allow reasonable time for validation and remediation before public disclosure. The maintainers may request coordinated disclosure when a report affects production execution, authorization, or privilege boundaries.
