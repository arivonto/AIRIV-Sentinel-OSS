from sentinel.contract_verifier import ContractVerifier


def test_observation_verifier_does_not_claim_noncanonical_contract():
    verifier = ContractVerifier()

    observation = {
        "source": "TMUX",
        "captured_at": "2026-09-03T00:00:00+00:00",
        "pane_id": "%0",
        "capture_ok": True,
        "pane_dead": False,
    }

    violations = verifier.verify(observation)

    assert violations == []
    assert verifier.CONTRACT_ID is None


def test_observation_integrity_violation_is_not_falsely_attributed_to_contract():
    verifier = ContractVerifier()

    observation = {
        "source": "TMUX",
        "captured_at": "2026-09-03T00:00:00+00:00",
        "pane_id": "%0",
        "capture_ok": False,
        "pane_dead": False,
    }

    violations = verifier.verify(observation)

    assert len(violations) == 1
    assert violations[0].violation_type == "CAPTURE_FAILED"
    assert violations[0].contract_id is None
