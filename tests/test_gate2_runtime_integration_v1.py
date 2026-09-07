"""Gate 2 behavioral runtime integration for Commander-approved production remediation."""

import inspect

import pytest

from sentinel.runtime import SentinelRuntime
from test_gate1_commander_production_integration_v1 import (
    configure_commander_only,
)
from test_systemd_commander_integration_v1 import (
    FakeArgvExecutor,
    SnapshotProvider,
    configure_fake,
    successful_after,
)
from test_systemd_incident_dispatch_v1 import context  # noqa: F401
from test_systemd_production_approval_issuance_v1 import inputs  # noqa: F401
from test_systemd_production_commander_only_policy_v1 import (
    facts,
    make_context,
)


def make_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "diagnostic"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "execution"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "runtime"),
    )

    runtime = SentinelRuntime()
    orchestrator = runtime.commander.remediation_orchestrator
    fake = FakeArgvExecutor(success=True)
    orchestrator.gate.executor = fake
    return runtime, orchestrator, fake


def assert_stored_runtime_layers_disabled(runtime):
    assert runtime.systemd_production_execution_dispatch_gate.enabled is False
    assert runtime.systemd_production_runtime_invocation.enabled is False
    assert runtime.systemd_production_runtime_delegation_bridge.enabled is False
    assert runtime.systemd_production_activation_runtime_bridge.enabled is False


def test_default_runtime_keeps_all_generic_production_layers_disabled():
    runtime = SentinelRuntime()

    assert_stored_runtime_layers_disabled(runtime)
    assert runtime.policy.list_systemd_production_targets() == ()
    assert not hasattr(runtime, "systemd_production_execution_delegation")


def test_explicit_runtime_reaches_canonical_policy_execution_and_verification(
    tmp_path,
    monkeypatch,
    facts,
):
    runtime, orchestrator, fake = make_runtime(
        tmp_path,
        monkeypatch,
    )
    binding = facts[0]
    plan = binding.prepared.plan
    authorization = make_context(facts)

    configure_commander_only(runtime, plan)
    configure_fake(orchestrator, fake, plan)
    provider = SnapshotProvider(successful_after(plan))

    result = runtime.invoke_systemd_production_remediation(
        activation_binding=binding,
        authorization_context=authorization,
        incident_state="INVESTIGATING",
        after_snapshot_provider=provider,
        production_now=115.0,
        timeout=3.0,
    )

    assert result.delegated
    runtime_result = result.runtime_delegation_result
    assert runtime_result is not None
    assert runtime_result.delegated

    integration_result = runtime_result.integration_result
    assert integration_result is not None
    assert integration_result.authorization.authorized
    assert integration_result.execution_succeeded
    assert integration_result.verification_succeeded
    assert integration_result.recovered
    assert len(fake.calls) == 1
    assert provider.calls == 1

    # Explicit per-call enablement never leaks into runtime state.
    assert_stored_runtime_layers_disabled(runtime)
    assert not hasattr(runtime, "systemd_production_execution_delegation")


def test_raw_authorization_context_is_rejected_before_effect(
    tmp_path,
    monkeypatch,
    facts,
):
    runtime, orchestrator, fake = make_runtime(
        tmp_path,
        monkeypatch,
    )
    binding = facts[0]
    plan = binding.prepared.plan

    configure_commander_only(runtime, plan)
    configure_fake(orchestrator, fake, plan)
    provider = SnapshotProvider(successful_after(plan))

    with pytest.raises(
        TypeError,
        match="canonical Commander authorization context required",
    ):
        runtime.invoke_systemd_production_remediation(
            activation_binding=binding,
            authorization_context=object(),
            incident_state="INVESTIGATING",
            after_snapshot_provider=provider,
            production_now=115.0,
        )

    assert fake.calls == []
    assert provider.calls == 0
    assert_stored_runtime_layers_disabled(runtime)


def test_runtime_does_not_store_execution_delegation_authority(
    tmp_path,
    monkeypatch,
):
    runtime, _, _ = make_runtime(
        tmp_path,
        monkeypatch,
    )
    assert not hasattr(runtime, "systemd_production_execution_delegation")


def test_run_once_never_invokes_generic_production_remediation():
    source = inspect.getsource(SentinelRuntime.run_once)
    assert "invoke_systemd_production_remediation" not in source
    assert "SystemdProductionExecutionDelegationBoundary" not in source
