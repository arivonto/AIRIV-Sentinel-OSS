"""Global pytest safety isolation for AIRIV Sentinel tests."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_execution_identity_journal(monkeypatch, tmp_path):
    """
    Prevent tests from writing to Sentinel's canonical runtime journal.

    Production defaults remain unchanged. Every test receives an isolated
    execution-identity journal unless that test explicitly overrides the
    environment for its own isolated scenario.
    """
    root = tmp_path / "execution_identity"

    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(root),
    )


@pytest.fixture(autouse=True)
def isolate_systemd_production_state(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_SYSTEMD_EVIDENCE_DIR",
        str(tmp_path / "systemd_evidence"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR",
        str(tmp_path / "systemd_production_runtime"),
    )


@pytest.fixture(autouse=True)
def isolate_systemd_production_activation_state(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_ACTIVATION_DIR",
        str(tmp_path / "systemd_production_activation"),
    )
