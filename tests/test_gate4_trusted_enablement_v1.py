"""Gate 4 trusted host enablement boundary regression."""

from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from sentinel.systemd_production_bounded_autonomous import UNIT
from sentinel.systemd_production_gate4_enablement import (
    COOLDOWN_SECONDS,
    MAX_ATTEMPTS_PER_WINDOW,
    RETRY_WINDOW_SECONDS,
    canonical_enabled_json,
    load_gate4_capability,
)
from sentinel.systemd_production_target_policy import ProductionTargetMode


def fake_info(*, directory, mode, uid=0, gid=0, nlink=1):
    return SimpleNamespace(
        st_mode=(stat.S_IFDIR if directory else stat.S_IFREG) | mode,
        st_uid=uid,
        st_gid=gid,
        st_nlink=nlink,
    )


def canonical_lstat(path):
    path = Path(path)
    if path.name == "gate4-bounded-autonomous.json":
        return fake_info(directory=False, mode=0o644)
    if path.name == "airiv-sentinel":
        return fake_info(directory=True, mode=0o755)
    raise FileNotFoundError(path)


def test_gate4_enablement_absence_is_hard_disabled():
    def missing(path):
        raise FileNotFoundError(path)

    capability = load_gate4_capability(
        path="/etc/airiv-sentinel/gate4-bounded-autonomous.json",
        lstat_fn=missing,
    )

    assert capability.enabled is False
    assert capability.unit == UNIT
    assert capability.cooldown_seconds == COOLDOWN_SECONDS
    assert capability.retry_window_seconds == RETRY_WINDOW_SECONDS
    assert capability.max_attempts_per_window == MAX_ATTEMPTS_PER_WINDOW


def test_gate4_exact_root_owned_canonical_file_enables_only_exact_probe():
    capability = load_gate4_capability(
        path="/etc/airiv-sentinel/gate4-bounded-autonomous.json",
        lstat_fn=canonical_lstat,
        read_text_fn=lambda path: canonical_enabled_json(),
    )

    assert capability.enabled is True
    assert capability.unit == UNIT
    assert capability.cooldown_seconds == 3600.0
    assert capability.retry_window_seconds == 86400.0
    assert capability.max_attempts_per_window == 1
    assert capability.target_rule.mode is ProductionTargetMode.AUTONOMOUS


def test_gate4_rejects_service_user_writable_enablement_file():
    def unsafe(path):
        path = Path(path)
        if path.name == "gate4-bounded-autonomous.json":
            return fake_info(directory=False, mode=0o664)
        return fake_info(directory=True, mode=0o755)

    with pytest.raises(ValueError, match="unsafe_gate4_enablement_file"):
        load_gate4_capability(
            path="/etc/airiv-sentinel/gate4-bounded-autonomous.json",
            lstat_fn=unsafe,
            read_text_fn=lambda path: canonical_enabled_json(),
        )


def test_gate4_rejects_non_root_enablement_file():
    def unsafe(path):
        path = Path(path)
        if path.name == "gate4-bounded-autonomous.json":
            return fake_info(directory=False, mode=0o644, uid=1000, gid=1000)
        return fake_info(directory=True, mode=0o755)

    with pytest.raises(ValueError, match="unsafe_gate4_enablement_file"):
        load_gate4_capability(
            path="/etc/airiv-sentinel/gate4-bounded-autonomous.json",
            lstat_fn=unsafe,
            read_text_fn=lambda path: canonical_enabled_json(),
        )


def test_gate4_rejects_unsafe_parent_directory():
    def unsafe(path):
        path = Path(path)
        if path.name == "gate4-bounded-autonomous.json":
            return fake_info(directory=False, mode=0o644)
        return fake_info(directory=True, mode=0o777)

    with pytest.raises(ValueError, match="unsafe_gate4_enablement_directory"):
        load_gate4_capability(
            path="/etc/airiv-sentinel/gate4-bounded-autonomous.json",
            lstat_fn=unsafe,
            read_text_fn=lambda path: canonical_enabled_json(),
        )


def test_gate4_rejects_noncanonical_or_broadened_configuration():
    broadened = canonical_enabled_json().replace(
        '"cooldown_seconds":3600.0',
        '"cooldown_seconds":0.0',
    )

    with pytest.raises(ValueError, match="noncanonical_gate4_enablement"):
        load_gate4_capability(
            path="/etc/airiv-sentinel/gate4-bounded-autonomous.json",
            lstat_fn=canonical_lstat,
            read_text_fn=lambda path: broadened,
        )


def test_gate4_enablement_path_must_be_absolute():
    with pytest.raises(ValueError, match="gate4_enablement_path_must_be_absolute"):
        load_gate4_capability(path="relative/gate4.json")
