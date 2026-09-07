"""Gate 1 E2E: Commander-approved systemd path reaches canonical terminalization."""

from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_decider import CommanderIntentDecision
from sentinel.incidents.manager import IncidentManager
from sentinel.systemd_production_commander_incident_continuation import (
    build_systemd_production_commander_incident_continuation,
)
from sentinel.systemd_production_commander_resolution import (
    resolve_systemd_production_commander_result,
)
from test_gate1_commander_production_integration_v1 import (
    configure_commander_only,
    context,  # noqa: F401
    facts,
    inputs,  # noqa: F401
)
from test_systemd_commander_integration_v1 import (
    SnapshotProvider,
    configure_fake,
    make_runtime,
    successful_after,
)
from test_systemd_production_commander_incident_continuation_v1 import (
    _exact_shell,
)
from test_systemd_production_commander_only_policy_v1 import make_context


def make_investigating_incident(plan):
    manager = IncidentManager()
    incident = manager.evaluate_anomaly(
        observation={
            "pane_id": plan.effect.component_id,
            "agent_identity": "sentinel",
        },
        anomaly_type="SYSTEMD_PRODUCTION_TEST",
        reason="Gate 1 Commander-approved resolution E2E.",
    )
    incident.incident_id = plan.effect.incident_id
    manager.investigate(plan.effect.component_id)
    return manager, incident


def make_continuation(*, incident, prepared, authorization):
    decision = _exact_shell(
        CommanderIntentDecision,
        intent=CommanderIntent.NEED_COMMANDER,
    )
    return build_systemd_production_commander_incident_continuation(
        incident=incident,
        decision=decision,
        binding=prepared.binding,
        prepared=prepared,
        approval=authorization.approval,
        now=115.0,
    )


def test_verified_commander_remediation_terminalizes_recovered(
    tmp_path,
    monkeypatch,
    facts,
):
    runtime, orchestrator, fake, integration = make_runtime(
        tmp_path,
        monkeypatch,
    )
    prepared = facts[0].prepared
    plan = prepared.plan
    authorization = make_context(facts)
    manager, incident = make_investigating_incident(plan)
    continuation = make_continuation(
        incident=incident,
        prepared=prepared,
        authorization=authorization,
    )

    configure_commander_only(runtime, plan)
    configure_fake(orchestrator, fake, plan)
    provider = SnapshotProvider(successful_after(plan))

    integration_result = integration.execute_verified(
        plan=plan,
        incident_state="INVESTIGATING",
        after_snapshot_provider=provider,
        production_now=115.0,
        commander_authorization=authorization,
    )

    resolution = resolve_systemd_production_commander_result(
        continuation=continuation,
        commander_authorization=authorization,
        integration_result=integration_result,
        incident_manager=manager,
    )

    assert resolution.final_outcome == "RECOVERED"
    assert resolution.incident is incident
    assert incident.status == "TERMINAL"
    assert incident.lifecycle_state == "TERMINAL"
    assert incident.final_outcome == "RECOVERED"
    assert manager.get_active_incident(plan.effect.component_id) is None
    assert manager.get_history()[-1]["final_outcome"] == "RECOVERED"
    assert len(fake.calls) == 1
    assert provider.calls == 1
