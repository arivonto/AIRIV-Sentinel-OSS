from __future__ import annotations

import json

import pytest

from sentinel.ai_agent_execution import (
    AgentExecutionBoundary,
    AgentVerificationDecision,
    RawAgentResult,
)
from sentinel.ai_agent_identity import (
    AgentExecutionIdentityLedger,
    AgentExecutionIdentityState,
    ReplaySafeAgentExecutionOrchestrator,
    fingerprint_agent_request,
)
from sentinel.ai_agent_local_proof import (
    DeterministicLocalAgentAdapter,
    DeterministicLocalAgentVerifier,
)
from tests.test_ai_agent_execution_foundation_v1 import make_request, make_result


def test_request_fingerprint_is_stable_across_mapping_order():
    first = make_request(
        input_payload={"b": 2, "a": 1},
        execution_context={"z": 9, "a": 1},
    )
    second = make_request(
        input_payload={"a": 1, "b": 2},
        execution_context={"a": 1, "z": 9},
    )

    assert fingerprint_agent_request(first) == fingerprint_agent_request(second)


def test_request_fingerprint_fails_closed_for_non_json_payload():
    request = make_request(input_payload={"opaque": object()})

    with pytest.raises(ValueError, match="deterministically JSON serializable"):
        fingerprint_agent_request(request)


def test_ledger_claim_is_durable_and_exact_replay_is_suppressed(tmp_path):
    request = make_request()
    ledger = AgentExecutionIdentityLedger(tmp_path)

    first = ledger.claim(request)
    second = ledger.claim(request)

    assert first.claimed is True
    assert first.replayed is False
    assert second.claimed is False
    assert second.replayed is True
    assert second.record.state == AgentExecutionIdentityState.UNKNOWN
    assert second.record.detail_code == "REPLAY_AFTER_INCOMPLETE_ATTEMPT"
    assert ledger.load(request.request_id) == second.record


def test_ledger_rejects_same_request_id_with_different_bound_request(tmp_path):
    ledger = AgentExecutionIdentityLedger(tmp_path)
    ledger.claim(make_request())

    with pytest.raises(RuntimeError, match="does not match original request identity"):
        ledger.claim(make_request(requested_operation="different-operation"))


def test_corrupt_identity_record_fails_closed(tmp_path):
    request = make_request()
    ledger = AgentExecutionIdentityLedger(tmp_path)
    claim = ledger.claim(request)
    record_path = ledger._record_path(request.request_id)
    record_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unreadable"):
        ledger.load(claim.record.request_id)


def test_local_proof_adapter_is_disabled_by_default():
    request = make_request()
    boundary = AgentExecutionBoundary(
        adapter=DeterministicLocalAgentAdapter(),
        verifier=DeterministicLocalAgentVerifier(),
    )

    outcome = boundary.execute(request)

    assert outcome.attempted is False
    assert outcome.accepted is False
    assert outcome.verification.reason_code == "ADAPTER_DISABLED"


def test_deterministic_local_proof_executes_verifies_and_persists_identity(tmp_path):
    request = make_request()
    adapter = DeterministicLocalAgentAdapter(enabled=True)
    boundary = AgentExecutionBoundary(
        adapter=adapter,
        verifier=DeterministicLocalAgentVerifier(),
    )
    orchestrator = ReplaySafeAgentExecutionOrchestrator(
        boundary=boundary,
        ledger=AgentExecutionIdentityLedger(tmp_path),
    )

    outcome = orchestrator.execute(request)

    assert outcome.replayed is False
    assert outcome.executed is True
    assert outcome.record.state == AgentExecutionIdentityState.SUCCEEDED
    assert outcome.record.accepted is True
    assert outcome.boundary_outcome.accepted is True
    assert outcome.boundary_outcome.verification.reason_code == "LOCAL_PROOF_VERIFIED"
    assert adapter.execution_count == 1
    assert outcome.boundary_outcome.raw_result.to_dict()["output"]["proposal_only"] is True

    replay = orchestrator.execute(request)
    assert replay.replayed is True
    assert replay.executed is False
    assert replay.record.state == AgentExecutionIdentityState.SUCCEEDED
    assert adapter.execution_count == 1


def test_local_verifier_rejects_tampered_agent_output():
    request = make_request()
    result = make_result(
        request,
        output={
            "proof_version": "AIRIV_SENTINEL_AI_LOCAL_PROOF_V1",
            "request_sha256": "0" * 64,
            "requested_operation": request.requested_operation,
            "proposal_only": True,
        },
    )

    decision = DeterministicLocalAgentVerifier().verify(request, result)

    assert decision.accepted is False
    assert decision.reason_code == "LOCAL_PROOF_MISMATCH"


def test_rejected_successful_agent_result_becomes_terminal_failed_identity(tmp_path):
    class RejectingVerifier:
        def verify(self, request, result):
            return AgentVerificationDecision(False, "INDEPENDENT_REJECTION")

    request = make_request()
    orchestrator = ReplaySafeAgentExecutionOrchestrator(
        boundary=AgentExecutionBoundary(
            adapter=DeterministicLocalAgentAdapter(enabled=True),
            verifier=RejectingVerifier(),
        ),
        ledger=AgentExecutionIdentityLedger(tmp_path),
    )

    outcome = orchestrator.execute(request)

    assert outcome.record.state == AgentExecutionIdentityState.FAILED
    assert outcome.record.accepted is False
    assert outcome.record.detail_code == "INDEPENDENT_REJECTION"


def test_ambiguous_adapter_exception_becomes_terminal_unknown_and_no_retry(tmp_path):
    class ExplodingAdapter:
        name = "EXPLODING_TEST"
        enabled = True

        def __init__(self):
            self.calls = 0

        def execute(self, request):
            self.calls += 1
            raise RuntimeError("ambiguous provider failure")

    request = make_request()
    adapter = ExplodingAdapter()
    orchestrator = ReplaySafeAgentExecutionOrchestrator(
        boundary=AgentExecutionBoundary(adapter=adapter),
        ledger=AgentExecutionIdentityLedger(tmp_path),
    )

    first = orchestrator.execute(request)
    second = orchestrator.execute(request)

    assert first.record.state == AgentExecutionIdentityState.UNKNOWN
    assert first.record.detail_code == "adapter_exception:RuntimeError"
    assert second.replayed is True
    assert second.executed is False
    assert second.record.state == AgentExecutionIdentityState.UNKNOWN
    assert adapter.calls == 1


def test_identity_ledger_never_persists_raw_payload_or_output(tmp_path):
    request = make_request(input_payload={"sensitive_prompt": "do-not-persist"})
    adapter = DeterministicLocalAgentAdapter(enabled=True)
    orchestrator = ReplaySafeAgentExecutionOrchestrator(
        boundary=AgentExecutionBoundary(
            adapter=adapter,
            verifier=DeterministicLocalAgentVerifier(),
        ),
        ledger=AgentExecutionIdentityLedger(tmp_path),
    )

    orchestrator.execute(request)
    raw = orchestrator.ledger._record_path(request.request_id).read_text(
        encoding="utf-8"
    )
    data = json.loads(raw)

    assert "do-not-persist" not in raw
    assert "input_payload" not in data
    assert "output" not in data
    assert data["request_sha256"] == fingerprint_agent_request(request)
