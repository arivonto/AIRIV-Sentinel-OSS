from __future__ import annotations

import importlib.util
from pathlib import Path

from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    ProductionTargetMode,
    SystemdAttemptFact,
    SystemdProductionTargetPolicy,
    SystemdProductionTargetRule,
)


def load_helpers(
    name,
    path,
):
    spec = (
        importlib.util
        .spec_from_file_location(
            name,
            Path(path),
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


legacy = load_helpers(
    "_airiv_d83_legacy_helpers",
    "tests/test_systemd_commander_integration_v1.py",
)

d82 = load_helpers(
    "_airiv_d83_policy_helpers",
    "tests/test_systemd_production_policy_integration_v1.py",
)


def setup_case(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = legacy.make_runtime(
        tmp_path,
        monkeypatch,
    )

    # D8.2 helper builds an exact non-protected
    # production systemd target.
    plan = d82.make_plan()

    legacy.activate_exact_plan(
        runtime,
        plan,
    )

    legacy.configure_fake(
        orchestrator,
        fake,
        plan,
    )

    provider = legacy.SnapshotProvider(
        legacy.successful_after(
            plan
        )
    )

    return (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    )


def configure_target(
    runtime,
    plan,
    *,
    mode=ProductionTargetMode.AUTONOMOUS,
    cooldown=300.0,
    window=900.0,
    max_attempts=1,
):
    runtime.policy.configure_systemd_production_target_policy(
        SystemdProductionTargetPolicy(
            [
                SystemdProductionTargetRule(
                    unit=(
                        plan.scope
                        .target
                        .unit_name
                    ),
                    mode=mode,
                    cooldown_seconds=cooldown,
                    retry_window_seconds=window,
                    max_attempts_per_window=(
                        max_attempts
                    ),
                )
            ]
        )
    )


def execute(
    integration,
    plan,
    provider,
    **production,
):
    return integration.execute_verified(
        plan=plan,

        # Proves both branches keep the canonical
        # incident_state.strip() normalization.
        incident_state=" INVESTIGATING ",

        after_snapshot_provider=provider,

        **production,
    )


def test_legacy_default_behavior_is_preserved(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    result = execute(
        integration,
        plan,
        provider,
    )

    assert result.authorization.authorized

    assert result.execution is not None
    assert result.execution.success

    assert result.verification is not None
    assert result.verification.verified

    assert result.recovered

    assert len(fake.calls) == 1
    assert provider.calls == 1


def test_production_default_empty_denies_before_effect(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
    )

    assert not result.authorization.authorized

    assert result.execution is None
    assert result.identity_record is None
    assert result.verification is None

    assert fake.calls == []
    assert provider.calls == 0


def test_exact_autonomous_target_uses_existing_execution_path_once(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    configure_target(
        runtime,
        plan,
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
    )

    assert result.authorization.authorized

    assert result.execution is not None
    assert result.execution.success

    assert result.verification is not None
    assert result.verification.verified

    assert result.recovered

    assert len(fake.calls) == 1
    assert provider.calls == 1


def test_commander_only_target_denied_before_effect(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    configure_target(
        runtime,
        plan,
        mode=(
            ProductionTargetMode
            .COMMANDER_ONLY
        ),
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
    )

    assert not result.authorization.authorized

    assert result.execution is None
    assert result.verification is None

    assert fake.calls == []
    assert provider.calls == 0


def test_cooldown_denied_before_effect(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    configure_target(
        runtime,
        plan,
        cooldown=300.0,
        window=1000.0,
        max_attempts=10,
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
        production_attempts=(
            SystemdAttemptFact(
                unit=(
                    plan.scope
                    .target
                    .unit_name
                ),
                action=ACTION_RESTART,
                timestamp=900.0,
            ),
        ),
    )

    assert not result.authorization.authorized

    assert result.execution is None

    assert fake.calls == []
    assert provider.calls == 0


def test_retry_budget_denied_before_effect(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    configure_target(
        runtime,
        plan,
        cooldown=10.0,
        window=900.0,
        max_attempts=1,
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
        production_attempts=(
            SystemdAttemptFact(
                unit=(
                    plan.scope
                    .target
                    .unit_name
                ),
                action=ACTION_RESTART,
                timestamp=500.0,
            ),
        ),
    )

    assert not result.authorization.authorized

    assert result.execution is None

    assert fake.calls == []
    assert provider.calls == 0


def test_blast_radius_denied_before_effect(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    configure_target(
        runtime,
        plan,
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
        active_production_effects=1,
    )

    assert not result.authorization.authorized

    assert result.execution is None

    assert fake.calls == []
    assert provider.calls == 0


def test_production_calls_d82_once_and_bound_once(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    configure_target(
        runtime,
        plan,
    )

    original_production = (
        runtime.policy
        .evaluate_systemd_production_bound
    )

    original_bound = (
        runtime.policy
        .evaluate_bound
    )

    production_calls = []
    bound_calls = []

    def counted_bound(
        **kwargs,
    ):
        bound_calls.append(
            kwargs
        )

        return original_bound(
            **kwargs
        )

    def counted_production(
        **kwargs,
    ):
        production_calls.append(
            kwargs
        )

        return original_production(
            **kwargs
        )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_bound",
        counted_bound,
    )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_systemd_production_bound",
        counted_production,
    )

    result = execute(
        integration,
        plan,
        provider,
        production_now=1000.0,
    )

    assert result.authorization.authorized

    assert len(
        production_calls
    ) == 1

    assert len(
        bound_calls
    ) == 1

    assert len(
        fake.calls
    ) == 1


def test_legacy_calls_bound_once_and_never_d82(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
        plan,
        provider,
    ) = setup_case(
        tmp_path,
        monkeypatch,
    )

    original_production = (
        runtime.policy
        .evaluate_systemd_production_bound
    )

    original_bound = (
        runtime.policy
        .evaluate_bound
    )

    production_calls = []
    bound_calls = []

    def counted_bound(
        **kwargs,
    ):
        bound_calls.append(
            kwargs
        )

        return original_bound(
            **kwargs
        )

    def counted_production(
        **kwargs,
    ):
        production_calls.append(
            kwargs
        )

        return original_production(
            **kwargs
        )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_bound",
        counted_bound,
    )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_systemd_production_bound",
        counted_production,
    )

    result = execute(
        integration,
        plan,
        provider,
    )

    assert result.authorization.authorized

    assert len(
        bound_calls
    ) == 1

    assert production_calls == []

    assert len(
        fake.calls
    ) == 1
