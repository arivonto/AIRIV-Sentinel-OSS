"""D8.15 transitive Commander-authorization dependency closure."""

import subprocess
import sys


def _run(source: str):
    return subprocess.run(
        [sys.executable, "-B", "-c", source],
        text=True,
        capture_output=True,
        check=False,
    )


def test_authorization_import_does_not_load_policy_or_runtime_coordinator():
    result = _run(
        """
import sys
import sentinel.systemd_production_commander_authorization

assert "sentinel.remediation_policy" not in sys.modules
assert "sentinel.diagnostic.runtime_coordinator" not in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


def test_authorization_first_import_order():
    result = _run(
        """
import sentinel.systemd_production_commander_authorization
import sentinel.remediation_policy
"""
    )

    assert result.returncode == 0, result.stderr


def test_policy_first_import_order():
    result = _run(
        """
import sentinel.remediation_policy
import sentinel.systemd_production_commander_authorization
"""
    )

    assert result.returncode == 0, result.stderr


def test_diagnostic_runtime_exports_remain_lazy_and_compatible():
    result = _run(
        """
import sys
import sentinel.diagnostic as diagnostic

assert "sentinel.diagnostic.runtime_coordinator" not in sys.modules
assert "sentinel.remediation_policy" not in sys.modules

assert diagnostic.RuntimeDiagnosticConfig.__name__ == "RuntimeDiagnosticConfig"
assert diagnostic.RuntimeDiagnosticCoordinator.__name__ == "RuntimeDiagnosticCoordinator"

assert "sentinel.diagnostic.runtime_coordinator" in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr
