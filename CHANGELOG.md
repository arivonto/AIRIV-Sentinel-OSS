# Changelog

All notable public-facing changes to AIRIV Sentinel are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project intends to use Semantic Versioning for published releases.

## [Unreleased]

### Added

- Apache License 2.0 public licensing.
- Public security and contribution policies.
- Public issue and pull-request templates.
- Public-release secret/history scan and repository hygiene gate.
- Expanded secret-bearing filename coverage for environment, credential, auth, service-account, keystore, token, and secret-file classes.
- Project documentation validator for Markdown links, HTML structure/anchors, and public host-topology disclosure minimization.
- Synchronized project-lock documentation for the **AIRIV Sentinel Roadmap** foundation.
- Explicit concept-evolution record covering the initial supervisor concept, Autonomous Commander mission, authority consolidation, execution identity, Gate 3, Gate 4, trusted-host automation, and clean public distribution.
- Locked repository-domain model: `AIRIV-Sentinel` = Private canonical source; `AIRIV-Sentinel-OSS` = Public curated open-source distribution.
- Curated public `index.html` alongside `README.md` as a required project-level documentation surface.
- Generic example identity configuration.

### Changed

- `README.md` and `index.html` explicitly lock the two-domain repository topology and distinguish canonical/private and curated/public regression surfaces.
- Public-facing documentation minimizes private host identities, user-specific absolute paths, private state/bridge locations, internal host command refs, authorization locations, and other topology not required for safe installation.
- Public CI now requires both Markdown and HTML project-lock surfaces to pass structure/link/disclosure checks.
- Public release governance reflects the locked topology: canonical engineering/operations repository remains private; `AIRIV-Sentinel-OSS` remains the curated public distribution with independent history.
- Public synchronization is explicitly fail-closed and may not introduce broad cross-repository write credentials merely for convenience.

### Removed

- Tracked development backup/scratch files from the current repository tree.
- Host/workflow-specific identity configuration from the public source tree where it is not required for the standard distribution.
- Outdated release guidance that suggested making the canonical engineering repository public.
- Stale source-repository checksum manifest; deterministic checksum manifests remain build artifacts where their scope is exact and verifiable.

## Release history

No stable public release has been published yet. Canonical private validation/provenance records are not a substitute for a tagged public release.
