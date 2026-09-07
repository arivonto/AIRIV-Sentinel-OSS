"""Trusted host enablement boundary for Gate 4 bounded autonomy.

Absence of the root-owned configuration file means disabled. A present file
must be an exact canonical configuration owned by root and not writable by the
Sentinel service account. This module creates no incident, policy grant,
execution permit, remediation effect, or Commander approval evidence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from sentinel.systemd_production_bounded_autonomous import (
    UNIT,
    BoundedAutonomousSystemdCapability,
)


DEFAULT_ENABLEMENT_PATH = Path(
    "/etc/airiv-sentinel/gate4-bounded-autonomous.json"
)
SCHEMA = "airiv-sentinel-gate4-bounded-autonomous-enablement"
SCHEMA_VERSION = 1
COOLDOWN_SECONDS = 3600.0
RETRY_WINDOW_SECONDS = 86400.0
MAX_ATTEMPTS_PER_WINDOW = 1


def canonical_enabled_payload():
    return {
        "cooldown_seconds": COOLDOWN_SECONDS,
        "enabled": True,
        "max_attempts_per_window": MAX_ATTEMPTS_PER_WINDOW,
        "retry_window_seconds": RETRY_WINDOW_SECONDS,
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "unit": UNIT,
    }


def canonical_enabled_json():
    return json.dumps(
        canonical_enabled_payload(),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_parent(info):
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o755
    ):
        raise ValueError("unsafe_gate4_enablement_directory")


def _validate_file(info):
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o644
        or info.st_nlink != 1
    ):
        raise ValueError("unsafe_gate4_enablement_file")


def load_gate4_capability(
    *,
    path=DEFAULT_ENABLEMENT_PATH,
    lstat_fn=os.lstat,
    read_text_fn=None,
):
    """Load the exact Gate 4 capability or return hard-disabled by absence."""

    path = Path(path)
    if not path.is_absolute():
        raise ValueError("gate4_enablement_path_must_be_absolute")

    try:
        file_info = lstat_fn(path)
    except FileNotFoundError:
        return BoundedAutonomousSystemdCapability()

    try:
        parent_info = lstat_fn(path.parent)
    except FileNotFoundError as exc:
        raise ValueError("gate4_enablement_parent_missing") from exc

    _validate_parent(parent_info)
    _validate_file(file_info)

    if read_text_fn is None:
        read_text_fn = lambda target: Path(target).read_text(encoding="utf-8")

    payload = read_text_fn(path)
    if type(payload) is not str:
        raise TypeError("gate4_enablement_reader_must_return_str")

    canonical = canonical_enabled_json()
    if payload != canonical:
        raise ValueError("noncanonical_gate4_enablement")

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed_gate4_enablement") from exc

    if decoded != canonical_enabled_payload():
        raise ValueError("gate4_enablement_values_mismatch")

    return BoundedAutonomousSystemdCapability(
        enabled=True,
        unit=UNIT,
        cooldown_seconds=COOLDOWN_SECONDS,
        retry_window_seconds=RETRY_WINDOW_SECONDS,
        max_attempts_per_window=MAX_ATTEMPTS_PER_WINDOW,
    )
