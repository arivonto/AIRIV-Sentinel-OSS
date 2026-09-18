"""AIRIV Sentinel active constitution loader.

The loader is side-effect free. It reads the active constitution, authority,
and authenticity files at startup and reports UNKNOWN/invalid facts without
granting production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONSTITUTION = REPO_ROOT / "constitution" / "ACTIVE.yaml"
DEFAULT_AUTHORITY = REPO_ROOT / "constitution" / "ACTIVE_AUTHORITY.yaml"
DEFAULT_AUTHENTICITY = REPO_ROOT / "constitution" / "ACTIVE_AUTHENTICITY.yaml"
DEFAULT_MANIFEST = REPO_ROOT / "state" / "constitution" / "manifest.env"

V11_VERSION = "1.1"
V11_STATUS = "FINAL_LOCKED"
V11_AUTHORITY_PROFILE = "TRUSTED_AUTONOMOUS_ENGINEERING"
V11_AUTHENTICITY_MODE = "REALITY_FIRST"
V11_PRODUCTION_MODE = "SEPARATELY_BOUNDED"


@dataclass(frozen=True, slots=True)
class ConstitutionSnapshot:
    version: str
    status: str
    authority_profile: str
    authenticity_mode: str
    routine_development_approval_required: bool
    production_mode: str
    constitution_path: str
    authority_path: str
    authenticity_path: str
    blueprint_path: str | None
    blueprint_sha256: str | None
    blueprint_digest_verified: bool
    runtime_integration: str
    facts: Mapping[str, Any]

    @property
    def v11_runtime_active(self) -> bool:
        return (
            self.version == V11_VERSION
            and self.status == V11_STATUS
            and self.authority_profile == V11_AUTHORITY_PROFILE
            and self.authenticity_mode == V11_AUTHENTICITY_MODE
            and self.routine_development_approval_required is False
            and self.production_mode == V11_PRODUCTION_MODE
            and self.blueprint_digest_verified is True
        )


def load_active_constitution(
    *,
    constitution_path: str | os.PathLike[str] | None = None,
    authority_path: str | os.PathLike[str] | None = None,
    authenticity_path: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
) -> ConstitutionSnapshot:
    """Load active constitution facts from env paths or repo defaults."""

    manifest = _read_manifest(Path(manifest_path) if manifest_path else DEFAULT_MANIFEST)

    constitution = _resolve_path(
        constitution_path
        or os.environ.get("SENTINEL_CONSTITUTION_FILE")
        or manifest.get("SENTINEL_CONSTITUTION_PATH")
        or DEFAULT_CONSTITUTION
    )
    authority = _resolve_path(
        authority_path
        or os.environ.get("SENTINEL_AUTHORITY_FILE")
        or manifest.get("SENTINEL_AUTHORITY_PATH")
        or DEFAULT_AUTHORITY
    )
    authenticity = _resolve_path(
        authenticity_path
        or os.environ.get("SENTINEL_AUTHENTICITY_FILE")
        or manifest.get("SENTINEL_AUTHENTICITY_PATH")
        or DEFAULT_AUTHENTICITY
    )

    constitution_data = _read_yaml(constitution)
    authority_data = _read_yaml(authority)
    authenticity_data = _read_yaml(authenticity)

    identity = constitution_data.get("identity", {})
    commander = constitution_data.get("commander", {})
    sentinel = constitution_data.get("sentinel", {})
    trust_domains = constitution_data.get("trust_domains", {})
    production = trust_domains.get("production", {})
    blueprint = constitution_data.get("blueprint", {})

    blueprint_path = _blueprint_path(blueprint.get("artifact"))
    expected_sha = blueprint.get("sha256") or manifest.get("SENTINEL_BLUEPRINT_SHA256")
    digest_verified = _verify_digest(blueprint_path, expected_sha)

    rules = tuple(authenticity_data.get("rules", ()))
    authenticity_mode = (
        V11_AUTHENTICITY_MODE
        if (
            "REALITY_OUTRANKS_INFERENCE" in rules
            and "EVIDENCE_OUTRANKS_NARRATIVE" in rules
        )
        else "UNKNOWN"
    )

    runtime_integration = (
        "ACTIVE"
        if (
            identity.get("constitution_version") == V11_VERSION
            and sentinel.get("mode") == V11_AUTHORITY_PROFILE
            and digest_verified
        )
        else "UNKNOWN"
    )

    facts = MappingProxyType(
        {
            "authority_schema": authority_data.get("schema"),
            "authenticity_schema": authenticity_data.get("schema"),
            "authority_chain": tuple(authority_data.get("authority_chain", ())),
            "authenticity_rules": rules,
        }
    )

    return ConstitutionSnapshot(
        version=str(identity.get("constitution_version", "UNKNOWN")),
        status=str(identity.get("status", "UNKNOWN")),
        authority_profile=str(sentinel.get("mode", "UNKNOWN")),
        authenticity_mode=authenticity_mode,
        routine_development_approval_required=bool(
            commander.get("routine_engineering_approval_required", True)
        ),
        production_mode=str(production.get("mode", "UNKNOWN")),
        constitution_path=str(constitution),
        authority_path=str(authority),
        authenticity_path=str(authenticity),
        blueprint_path=str(blueprint_path) if blueprint_path else None,
        blueprint_sha256=str(expected_sha) if expected_sha else None,
        blueprint_digest_verified=digest_verified,
        runtime_integration=runtime_integration,
        facts=facts,
    )


def _read_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"constitution file must contain mapping: {path}")
    return data


def _resolve_path(value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _blueprint_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _resolve_path(value)


def _verify_digest(path: Path | None, expected: object) -> bool:
    if path is None or not isinstance(expected, str) or not expected.strip():
        return False
    if not path.exists() or not path.is_file():
        return False
    digest = sha256(path.read_bytes()).hexdigest()
    return digest == expected.strip()
