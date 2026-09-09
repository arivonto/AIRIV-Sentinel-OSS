from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sentinel.ai_agent_execution import (
    AgentExecutionBoundary,
    AgentExecutionEvidenceTrail,
    AgentExecutionStatus,
    AgentRequest,
    AgentVerificationDecision,
    DenyAllAgentResultVerifier,
    RawAgentResult,
)


STARTED = "2026-09-09T09:00:00+07:00"
COMPLETED = "2026-09-09T09:00:01+07:00"


def make_request(**overrides):
    values = {
        "request_id": "req-001",
        "agent_id": "agent-deterministic",
        "task_id": "task-001",
        "input_payload": {"observation": ["a", "b"]},
        "requested_operation": "analyze",
        "execution_context": {"mode": "test"},
        "authority_context": {"authority": "sentinel-test"},
    }
    values.update(overrides)
    return AgentRequest(**values)


def make_result(request, **overrides):
    values = {
        "request_id": request.request_id,
        "agent_id": request.agent_id,
        "task_id": request.task_id,
        "started_at": STARTED,
        "completed_at": COMPLETED,
        "output": {"classification": "nominal"},
        "execution_status": AgentExecutionStatus.SUCCEEDED,
    }
    values.update(overrides)
    return RawAgentResult(**values)


class DeterministicAdapter:
    name = "DETERMINISTIC_TEST"
    enabled = True

    def __init__(self, result_factory=None):
        self.requests = []
        self.result_factory = result_factory or make_result

    def execute(self, request):
        self.requests.append(request)
        return self.result_factory(request)


class AcceptingVerifier:
    def __init__(self):
        self.calls = []

    def verify(self, request, result):
        self.calls.append((request, result))
        return AgentVerificationDecision(True, "OBSERVED_TEST_PROOF")


class ExplodingAdapter:
    name = "EXPLODING_TEST"
    enabled = True

    def execute(self, request):
        raise RuntimeError("secret provider detail must not escape")


class ExplodingVerifier:
    def verify(self, request, result):
        raise RuntimeError("secret verifier detail must not escape")


def test_request_requires_exact_execution_identity_and_mapping_contexts():
    with pytest.raises(ValueError, match="request_id is required"):
        make_request(request_id="")

    with pytest.raises(TypeError, match="execution_context must be a mapping"):
        make_request(execution_context="not-a-mapping")

    with pytest.raises(TypeError, match="authority_context must be a mapping"):
        make_request(authority_context=None)


def test_request_and_result_snapshots_are_immutable_and_detached():
    payload = {"nested": ["original"]}
    request = make_request(input_payload=payload)
    payload["nested"].append("mutated")

    assert request.to_dict()["input_payload"] == {"nested": ["original"]}
    with pytest.raises(TypeError):
        request.execution_context["new"] = "value"
    with pytest.raises(FrozenInstanceError):
        request.request_id = "rewritten"

    result = make_result(request, output={"actions": ["proposal-only"]})
    exported = result.to_dict()
    exported["output"]["actions"].append("mutated")
    assert result.to_dict()["output"] == {"actions": ["proposal-only"]}


def test_raw_result_rejects_naive_reversed_and_unknown_status():
    request = make_request()

    with pytest.raises(ValueError, match="timezone"):
        make_result(request, started_at="2026-09-09T09:00:00")

    with pytest.raises(ValueError, match="must not precede"):
        make_result(
            request,
            started_at="2026-09-09T09:00:02+07:00",
            completed_at="2026-09-09T09:00:01+07:00",
        )

    with pytest.raises(ValueError, match="unsupported agent execution status"):
        make_result(request, execution_status="UNKNOWN_PROVIDER_STATUS")


def test_default_boundary_is_disabled_fail_closed_and_has_no_effect():
    request = make_request()
    boundary = AgentExecutionBoundary()

    outcome = boundary.execute(request)

    assert outcome.attempted is False
    assert outcome.accepted is False
    assert outcome.raw_result is None
    assert outcome.verification.reason_code == "ADAPTER_DISABLED"
    assert outcome.boundary_error_code == "ADAPTER_DISABLED"
    assert outcome.evidence is None
    assert boundary.evidence_trail.records == ()


def test_successful_agent_self_report_is_rejected_without_independent_verifier():
    request = make_request()
    adapter = DeterministicAdapter()
    boundary = AgentExecutionBoundary(
        adapter=adapter,
        verifier=DenyAllAgentResultVerifier(),
    )

    outcome = boundary.execute(request)

    assert outcome.attempted is True
    assert outcome.raw_result.execution_status == AgentExecutionStatus.SUCCEEDED
    assert outcome.accepted is False
    assert outcome.verification.reason_code == "NO_INDEPENDENT_VERIFIER"
    assert len(boundary.evidence_trail.records) == 1
    assert boundary.evidence_trail.records[0].verification_accepted is False


def test_independent_verifier_can_accept_observed_result_with_evidence():
    request = make_request()
    adapter = DeterministicAdapter()
    verifier = AcceptingVerifier()
    trail = AgentExecutionEvidenceTrail()
    boundary = AgentExecutionBoundary(
        adapter=adapter,
        verifier=verifier,
        evidence_trail=trail,
    )

    outcome = boundary.execute(request)

    assert adapter.requests == [request]
    assert len(verifier.calls) == 1
    assert outcome.accepted is True
    assert outcome.verification.reason_code == "OBSERVED_TEST_PROOF"
    assert outcome.evidence is trail.records[0]
    assert outcome.evidence.to_dict()["result_snapshot"]["output"] == {
        "classification": "nominal"
    }
    assert not hasattr(outcome, "incident_status")
    assert not hasattr(outcome, "remediation_authorized")
    assert not hasattr(outcome, "command")


def test_result_identity_mismatch_is_rejected_before_verifier():
    request = make_request()
    verifier = AcceptingVerifier()
    adapter = DeterministicAdapter(
        lambda req: make_result(req, request_id="wrong-request")
    )
    boundary = AgentExecutionBoundary(adapter=adapter, verifier=verifier)

    outcome = boundary.execute(request)

    assert outcome.accepted is False
    assert outcome.verification.reason_code == "RESULT_REQUEST_ID_MISMATCH"
    assert outcome.boundary_error_code == "RESULT_REQUEST_ID_MISMATCH"
    assert verifier.calls == []
    assert outcome.evidence.result_snapshot["request_id"] == "wrong-request"


def test_non_success_terminal_result_is_observable_but_never_verified_as_success():
    request = make_request()
    verifier = AcceptingVerifier()
    adapter = DeterministicAdapter(
        lambda req: make_result(req, execution_status=AgentExecutionStatus.FAILED)
    )
    boundary = AgentExecutionBoundary(adapter=adapter, verifier=verifier)

    outcome = boundary.execute(request)

    assert outcome.accepted is False
    assert outcome.verification.reason_code == "AGENT_FAILED"
    assert verifier.calls == []
    assert outcome.evidence.execution_status == AgentExecutionStatus.FAILED


def test_invalid_adapter_result_type_fails_closed_and_is_evidenced():
    class InvalidAdapter:
        name = "INVALID_TEST"
        enabled = True

        def execute(self, request):
            return {"claimed": "success"}

    outcome = AgentExecutionBoundary(adapter=InvalidAdapter()).execute(make_request())

    assert outcome.accepted is False
    assert outcome.raw_result is None
    assert outcome.verification.reason_code == "INVALID_RAW_RESULT_TYPE"
    assert outcome.evidence.boundary_error_code == "INVALID_RAW_RESULT_TYPE"


def test_adapter_exception_is_sanitized_and_evidenced():
    outcome = AgentExecutionBoundary(adapter=ExplodingAdapter()).execute(make_request())

    assert outcome.accepted is False
    assert outcome.verification.reason_code == "ADAPTER_EXCEPTION"
    assert outcome.boundary_error_code == "adapter_exception:RuntimeError"
    assert "secret" not in outcome.boundary_error_code
    assert outcome.evidence.boundary_error_code == "adapter_exception:RuntimeError"


def test_verifier_exception_is_sanitized_and_evidenced():
    outcome = AgentExecutionBoundary(
        adapter=DeterministicAdapter(),
        verifier=ExplodingVerifier(),
    ).execute(make_request())

    assert outcome.accepted is False
    assert outcome.verification.reason_code == "VERIFIER_EXCEPTION"
    assert outcome.boundary_error_code == "verifier_exception:RuntimeError"
    assert "secret" not in outcome.boundary_error_code
    assert outcome.evidence.verification_accepted is False


def test_evidence_trail_is_append_only_snapshot_surface():
    request = make_request()
    trail = AgentExecutionEvidenceTrail()
    boundary = AgentExecutionBoundary(
        adapter=DeterministicAdapter(),
        verifier=AcceptingVerifier(),
        evidence_trail=trail,
    )

    first = boundary.execute(request)
    second = boundary.execute(
        make_request(request_id="req-002", task_id="task-002")
    )

    assert tuple(record.sequence for record in trail.records) == (1, 2)
    assert first.evidence.sequence == 1
    assert second.evidence.sequence == 2
    with pytest.raises(AttributeError):
        trail.records.append(first.evidence)
    with pytest.raises(FrozenInstanceError):
        first.evidence.sequence = 99
