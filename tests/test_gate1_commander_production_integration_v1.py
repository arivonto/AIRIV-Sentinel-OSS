"""Gate 1 behavioral integration: durable Commander auth reaches policy/effect."""

from test_systemd_commander_integration_v1 import (
    SnapshotProvider,
    configure_fake,
    make_runtime,
    successful_after,
)
from test_systemd_incident_dispatch_v1 import context  # noqa: F401
from test_systemd_production_approval_issuance_v1 import inputs  # noqa: F401
from test_systemd_production_commander_only_policy_v1 import (
    facts,
    make_context,
)

from sentinel.systemd_production_target_policy import (
    ProductionTargetMode,
    SystemdProductionTargetPolicy,
    SystemdProductionTargetRule,
)


def configure_commander_only(runtime, plan):
    runtime.policy.allowed_actions.add(plan.effect.action)
    runtime.policy.configure_bound_effect(plan.effect)
    runtime.policy.configure_systemd_production_target_policy(
        SystemdProductionTargetPolicy(
            [
                SystemdProductionTargetRule(
                    plan.scope.target.unit_name,
                    ProductionTargetMode.COMMANDER_ONLY,
                )
            ]
        )
    )


def test_commander_only_authorization_executes_once_and_verifies(
    tmp_path,
    monkeypatch,
    facts,
):
    runtime, orchestrator, fake, integration = make_runtime(
        tmp_path,
        monkeypatch,
    )
    plan = facts[0].prepared.plan
    authorization = make_context(facts)

    configure_commander_only(runtime, plan)
    configure_fake(orchestrator, fake, plan)
    provider = SnapshotProvider(successful_after(plan))

    result = integration.execute_verified(
        plan=plan,
        incident_state="INVESTIGATING",
        after_snapshot_provider=provider,
        production_now=115.0,
        commander_authorization=authorization,
    )

    assert result.authorization.authorized
    assert result.execution_succeeded
    assert result.verification_succeeded
    assert result.recovered
    assert len(fake.calls) == 1
    assert provider.calls == 1


def test_commander_only_without_typed_authorization_denies_before_effect(
    tmp_path,
    monkeypatch,
    facts,
):
    runtime, orchestrator, fake, integration = make_runtime(
        tmp_path,
        monkeypatch,
    )
    plan = facts[0].prepared.plan

    configure_commander_only(runtime, plan)
    configure_fake(orchestrator, fake, plan)
    provider = SnapshotProvider(successful_after(plan))

    result = integration.execute_verified(
        plan=plan,
        incident_state="INVESTIGATING",
        after_snapshot_provider=provider,
        production_now=115.0,
    )

    assert not result.authorization.authorized
    assert result.execution is None
    assert result.verification is None
    assert fake.calls == []
    assert provider.calls == 0


def test_commander_authorization_rejected_outside_production_path(
    tmp_path,
    monkeypatch,
    facts,
):
    import pytest

    runtime, orchestrator, fake, integration = make_runtime(
        tmp_path,
        monkeypatch,
    )
    plan = facts[0].prepared.plan
    authorization = make_context(facts)

    runtime.policy.allowed_actions.add(plan.effect.action)
    runtime.policy.configure_bound_effect(plan.effect)
    configure_fake(orchestrator, fake, plan)

    with pytest.raises(
        ValueError,
        match="Commander authorization requires production evaluation",
    ):
        integration.execute_verified(
            plan=plan,
            incident_state="INVESTIGATING",
            after_snapshot_provider=SnapshotProvider(successful_after(plan)),
            commander_authorization=authorization,
        )

    assert fake.calls == []
