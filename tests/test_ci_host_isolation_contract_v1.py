"""CI contract: pytest must never inherit live AIRIV Sentinel host state."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sentinel.runtime import SentinelRuntime


ISOLATED_STATE_ENV = (
    "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
    "AIRIV_SENTINEL_SYSTEMD_EVIDENCE_DIR",
    "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR",
    "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_ACTIVATION_DIR",
    "AIRIV_SENTINEL_INCIDENT_REPORT_DIR",
    "AIRIV_SENTINEL_DELIVERY_IDENTITY_DIR",
    "AIRIV_SENTINEL_DELIVERY_DRY_RUN_DIR",
)

FORBIDDEN_HOST_PREFIXES = (
    "/var/lib/airiv-sentinel",
    "/etc/airiv-sentinel",
    "/home/",
)


def test_pytest_runtime_isolates_gate4_host_enablement():
    """Global pytest isolation must force Gate 4 disabled for ordinary tests."""
    runtime = SentinelRuntime()

    assert runtime.gate4_autonomous_remediation.capability.enabled is False


@pytest.mark.parametrize("env_name", ISOLATED_STATE_ENV)
def test_pytest_redirects_production_state_to_per_test_tmp_path(env_name, tmp_path):
    """Every canonical persistent-state override must resolve inside pytest tmp state."""
    raw = os.environ.get(env_name)

    assert raw, f"missing pytest isolation override: {env_name}"

    resolved = Path(raw).resolve()
    sandbox = tmp_path.resolve()

    assert resolved == sandbox or sandbox in resolved.parents
    assert not any(str(resolved).startswith(prefix) for prefix in FORBIDDEN_HOST_PREFIXES)
