from unittest.mock import patch

from sentinel.incidents.manager import IncidentManager
from sentinel.runtime import SentinelRuntime


def build_runtime_and_incident():
    runtime = SentinelRuntime()
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        {
            "pane_id": "%runtime-verification",
            "agent_identity": "sentinel",
            "source": "runtime-test",
            "captured_at": "2026-09-03T00:00:00+00:00",
        },
        "STUCK",
        "Runtime verification boundary test",
    )

    manager.investigate(incident.component_id)

    return runtime, incident


def test_runtime_creates_verifier_from_canonical_incident_component():
    runtime, incident = build_runtime_and_incident()

    captured = {}

    class FakeVerifier:
        def __init__(self, target):
            captured["target"] = target

        def verify(self):
            raise AssertionError("verification must not execute")

    runtime.orchestrator.handle_incident = lambda **kwargs: (
        type(
            "Result",
            (),
            {
                "decision": type(
                    "Decision",
                    (),
                    {
                        "decision": type(
                            "DecisionValue",
                            (),
                            {"value": "DENY"},
                        )(),
                        "reason": "denied",
                        "action": "restart_test",
                    },
                )(),
                "execution": None,
                "verification": None,
            },
        )()
    )

    with patch(
        "sentinel.runtime.TmuxRemediationVerifier",
        FakeVerifier,
    ):
        runtime.remediate(
            incident=incident,
            action="restart_test",
            command="true",
        )

    assert captured["target"].pane_id == incident.component_id
    assert captured["target"].expected_alive is True


def test_runtime_restores_existing_orchestrator_verifier_state():
    runtime, incident = build_runtime_and_incident()

    original_verifier = object()
    runtime.orchestrator.verifier = original_verifier

    runtime.orchestrator.handle_incident = lambda **kwargs: (
        type(
            "Result",
            (),
            {
                "decision": type(
                    "Decision",
                    (),
                    {
                        "decision": type(
                            "DecisionValue",
                            (),
                            {"value": "DENY"},
                        )(),
                        "reason": "denied",
                        "action": "restart_test",
                    },
                )(),
                "execution": None,
                "verification": None,
            },
        )()
    )

    runtime.remediate(
        incident=incident,
        action="restart_test",
        command="true",
    )

    assert runtime.orchestrator.verifier is original_verifier
