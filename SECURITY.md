# Security Policy

AIRIV Sentinel can perform consequential host operations when explicitly configured and authorized. Security reports and publication decisions must therefore be handled conservatively.

## Supported versions

Security fixes are applied to the current public `main` branch and to explicitly published supported releases. Pre-release development snapshots are not guaranteed long-term support.

## Reporting a vulnerability

Do **not** open a public issue for a vulnerability, suspected credential exposure, authorization bypass, unsafe remediation path, privilege-escalation issue, evidence-integrity issue, production-effect binding weakness, or sensitive host-topology disclosure.

Use GitHub private vulnerability reporting from the repository **Security** tab when available. If that channel is unavailable, contact the repository maintainer privately through the GitHub account that owns the repository before disclosing technical details.

A useful report includes:

- affected commit or release;
- affected component and authority boundary;
- prerequisites and threat model;
- minimal safe reproduction steps;
- expected vs. observed authorization behavior;
- whether a real host effect occurred;
- relevant sanitized logs/evidence with secrets and private topology removed;
- suggested mitigation, if known.

## Security invariants

AIRIV Sentinel is designed around these invariants:

- fail closed on unknown, malformed, stale, mismatched, exhausted, concurrent, unsupported, or unauthorized production state;
- `RemediationPolicy` remains the canonical remediation ALLOW/DENY authority;
- execution success is not equivalent to recovery;
- consequential effects require exact binding and independent verification;
- evidence must not be silently destroyed or rewritten;
- Commander-required effects must not be impersonated by autonomous code;
- production autonomy remains bounded by explicit target/action rules, cooldown, retry budget, concurrency/blast-radius controls, durable attempt accounting, and replay protection;
- uncertain execution outcomes must not be blindly retried;
- CI/self-hosted coordination must not be treated as general production root authority.

A report showing violation of any of these invariants is security-sensitive.

## Secrets and sensitive material

Never commit or publish:

- passwords or authentication cookies;
- credentials, API keys, access tokens, refresh tokens, or bearer tokens;
- private keys, client certificates containing private key material, keystores, or credential bundles;
- cloud/service-account credential files;
- machine-specific secret configuration;
- host-local authorization state;
- production incident/evidence stores containing sensitive environment data;
- private infrastructure addresses or topology that are not required for safe public use.

Repository CI includes history-aware high-confidence secret scanning and tracked secret-bearing filename rejection. Automated scanning reduces risk but is not a substitute for credential hygiene and review.

If a secret is committed, assume it is compromised: revoke/rotate it first, then remediate repository history as appropriate. Never rely on deletion alone.

## Public documentation disclosure boundary

Public documentation should explain architecture, installation, safety semantics, and supported interfaces without publishing operational details that materially improve an attacker's map of a specific trusted host.

Public-facing project documents must avoid unnecessary disclosure of:

- private host usernames or dedicated automation identities;
- user-specific absolute home paths;
- private bridge/state directories;
- internal command-trigger branch/ref names;
- host-local authorization file locations when not required for safe user installation;
- production evidence locations;
- private IP addresses, internal DNS names, tokens, or credentials.

## Distribution boundary

This public repository is a clean source distribution and does not inherit private canonical Git ancestry, private host-control/provenance files, runtime state, credentials, host-local configuration, or production evidence merely because those materials exist in private operations.

Publishing source code never grants runtime, host, Commander, or remediation authority.

## Public disclosure

Please allow reasonable time for validation and remediation before public disclosure. Maintainers may request coordinated disclosure when a report affects production execution, authorization, privilege boundaries, evidence integrity, or host security.
