import inspect
from pathlib import Path

from sentinel.runtime import SentinelRuntime
import sentinel.runtime as runtime_module
import sentinel.systemd_canary_live_execution as canary
import sentinel.systemd_production_probe_live_execution as probe

from sentinel.systemd_production_probe_design import (
    PROBE_COMPONENT_ID,
    PROBE_EFFECT_ARGV,
    PROBE_UNIT,
)


APPROVAL = "D8D12E-ONE-LIVE-DBUS-PROBE-RESTART"


def test_exact_probe_constants():
    assert probe.UNIT == PROBE_UNIT
    assert probe.COMPONENT == PROBE_COMPONENT_ID
    assert probe.D8D12E_APPROVAL_ID == APPROVAL


def test_exact_effect_argv_from_locked_design():
    assert PROBE_EFFECT_ARGV == (
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        PROBE_UNIT,
    )


def test_probe_surface_has_one_canonical_execution_edge():
    source = inspect.getsource(probe)

    assert source.count(".execute_verified(") == 1

    for forbidden in (
        "shell=True",
        "pkexec",
        "systemd-run",
        "os.system",
    ):
        assert forbidden not in source


def test_probe_surface_cannot_reference_canary_target():
    source = inspect.getsource(probe)

    assert (
        "airiv-sentinel-remediation-canary.service"
        not in source
    )


def test_runtime_owns_probe_surface():
    runtime = SentinelRuntime()

    assert isinstance(
        runtime.production_probe_live_execution,
        probe.SystemdProductionProbeLiveExecution,
    )

    assert runtime.last_production_probe_live_result is None


def test_runtime_probe_uses_exact_secure_default():
    runtime = SentinelRuntime()
    root = runtime.production_probe_live_execution.root
    repository = Path(probe.__file__).resolve().parents[1]
    assert root == (
        Path.home() / ".local" / "state" / "airiv-sentinel-secure"
        / "systemd_production_probe_live"
    )
    assert not root.resolve().is_relative_to(repository)
    assert root != repository / "var" / "systemd_production_probe_live"


def test_runtime_has_single_probe_cycle_edge():
    source = inspect.getsource(
        runtime_module.SentinelRuntime
    )

    assert (
        source.count(
            "self.production_probe_live_execution.cycle()"
        )
        == 1
    )


def test_runtime_has_no_direct_systemctl_authority():
    source = inspect.getsource(
        runtime_module.SentinelRuntime
    )

    assert "/usr/bin/systemctl" not in source
    assert "subprocess." not in source


def test_production_authority_remains_closed():
    runtime = SentinelRuntime()

    assert (
        runtime.policy.list_systemd_production_targets()
        == ()
    )

    assert (
        runtime
        .systemd_production_activation_runtime_bridge
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_runtime_delegation_bridge
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_runtime_invocation
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_execution_dispatch_gate
        .enabled
        is False
    )


def test_canary_remains_exact_canary_surface():
    assert (
        canary.UNIT
        == "airiv-sentinel-remediation-canary.service"
    )

    assert (
        canary.COMPONENT
        == "systemd:airiv-sentinel-remediation-canary.service"
    )


def test_contract_requires_separate_reload_gate():
    text = Path(
        "contracts/"
        "SYSTEMD_PRODUCTION_PROBE_LIVE_EXECUTION_CONTRACT.md"
    ).read_text(
        encoding="utf-8"
    )

    assert "separate explicit Commander approval" in text
    assert "Production allowlist remains EMPTY" in text
    assert "Synthetic `pkcheck --process` MUST NOT" in text
