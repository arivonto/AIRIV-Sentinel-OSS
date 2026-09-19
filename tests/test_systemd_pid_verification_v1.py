"""Tests for Stage 3C-V: raw PID restart verification."""

from __future__ import annotations

import pytest

from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope,
    SystemdManagerIdentity,
    SystemdOperation,
    SystemdPrivilegeBoundary,
    SystemdRestartVerification,
    SystemdRestartVerifier,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


def _manager() -> SystemdManagerIdentity:
    return SystemdManagerIdentity(
        boot_id="12345678-1234-1234-1234-123456789012",
        manager_pid=1,
        manager_start_ticks=1000000,
    )


def _identity(unit: str = "myapp.service") -> SystemdUnitIdentity:
    return SystemdUnitIdentity(
        unit_name=unit,
        fragment_path=f"/etc/systemd/system/{unit}",
        fragment_sha256="a" * 64,
        fragment_device=2049,
        fragment_inode=655370,
        fragment_uid=0,
        fragment_gid=0,
        manager=_manager(),
    )


def _snapshot(
    *,
    unit: str = "myapp.service",
    pid: int = 1000,
    invocation: str = "abcdef0123456789abcdef0123456789",
    active: str = "active",
    loaded: str = "loaded",
    sub: str = "running",
) -> SystemdUnitSnapshot:
    return SystemdUnitSnapshot(
        identity=_identity(unit),
        load_state=loaded,
        active_state=active,
        sub_state=sub,
        unit_file_state="enabled",
        main_pid=pid,
        invocation_id=invocation,
        exec_main_start_timestamp_monotonic=1000000,
    )


def _scope() -> BoundSystemdActionScope:
    return BoundSystemdActionScope(
        target=_identity(),
        operation=SystemdOperation.RESTART,
        privilege=SystemdPrivilegeBoundary(systemctl_binary="/usr/bin/systemctl"),
        require_new_invocation=True,
        require_new_pid=True,
    )


@pytest.fixture
def verifier() -> SystemdRestartVerifier:
    return SystemdRestartVerifier()


# --- 1. All conditions met → verified ---

def test_all_conditions_met_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="b" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is True
    assert result.new_pid is True
    assert result.new_invocation is True
    assert result.active_after is True
    assert result.same_target_identity is True


# --- 2. PID unchanged → NOT verified ---

def test_pid_unchanged_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=1000, invocation="b" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.new_pid is False
    assert result.reason == "systemd_pid_not_changed"


# --- 3. Invocation unchanged → NOT verified ---

def test_invocation_unchanged_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="a" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.new_invocation is False
    assert result.reason == "systemd_invocation_not_changed"


# --- 4. Inactive after → NOT verified ---

def test_inactive_after_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="b" * 32, active="inactive")
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.active_after is False


# --- 5. Before PID = 0 → PID condition fails ---

def test_before_pid_zero_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=0, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="b" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.new_pid is False


# --- 6. After PID = 0 → PID condition fails ---

def test_after_pid_zero_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=0, invocation="b" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.new_pid is False


# --- 7. Negative before PID → snapshot construction rejects ---

def test_negative_before_pid_rejected_at_construction():
    """SystemdUnitSnapshot rejects negative main_pid at construction."""
    with pytest.raises(ValueError, match="main_pid must be non-negative"):
        _snapshot(pid=-1, invocation="a" * 32)


# --- 8. Negative after PID → snapshot construction rejects ---

def test_negative_after_pid_rejected_at_construction():
    """SystemdUnitSnapshot rejects negative main_pid at construction."""
    with pytest.raises(ValueError, match="main_pid must be non-negative"):
        _snapshot(pid=-1, invocation="b" * 32)


# --- 9. Different target identity → NOT verified ---

def test_different_target_identity_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32, unit="app1.service")
    after = _snapshot(pid=2000, invocation="b" * 32, unit="app2.service")
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.same_target_identity is False


# --- 10. Both PID and invocation unchanged → NOT verified ---

def test_both_unchanged_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=1000, invocation="a" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False


# --- 11. PID changed is directly from main_pid, not invocation ---

def test_pid_independent_of_invocation(verifier: SystemdRestartVerifier):
    """PID change is derived from main_pid values, not inferred from invocation."""
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="b" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.new_pid is True
    # Verify PID comparison is direct
    assert result.new_pid == (after.main_pid != before.main_pid and before.main_pid > 0 and after.main_pid > 0)


# --- 12. PID changed but invocation same → NOT verified ---

def test_pid_changed_invocation_same_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="a" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.new_invocation is False
    # Verifier returns at invocation check before computing new_pid
    assert result.reason == "systemd_invocation_not_changed"


# --- 13. Invocation changed but PID same → NOT verified ---

def test_invocation_changed_pid_same_not_verified(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=1000, invocation="b" * 32)
    result = verifier.verify(scope=_scope(), before=before, after=after)
    assert result.verified is False
    assert result.new_invocation is True
    assert result.new_pid is False


# --- 14. require_new_pid=False allows unchanged PID ---

def test_require_new_pid_false_allows_unchanged(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=1000, invocation="b" * 32)
    scope = _scope()
    # Override require_new_pid
    object.__setattr__(scope, "require_new_pid", False)
    result = verifier.verify(scope=scope, before=before, after=after)
    assert result.verified is True
    assert result.new_pid is False
    assert result.new_invocation is True


# --- 15. require_new_invocation=False allows unchanged invocation ---

def test_require_new_invocation_false_allows_unchanged(verifier: SystemdRestartVerifier):
    before = _snapshot(pid=1000, invocation="a" * 32)
    after = _snapshot(pid=2000, invocation="a" * 32)
    scope = _scope()
    object.__setattr__(scope, "require_new_invocation", False)
    result = verifier.verify(scope=scope, before=before, after=after)
    assert result.verified is True
    assert result.new_invocation is False
    assert result.new_pid is True


# --- 16. Verification result exposes new_pid field ---

def test_verification_result_has_new_pid_field():
    v = SystemdRestartVerification(
        verified=True,
        same_target_identity=True,
        active_after=True,
        new_invocation=True,
        new_pid=True,
        before_target_fingerprint="a" * 64,
        after_target_fingerprint="a" * 64,
        reason="verified",
    )
    assert v.new_pid is True
