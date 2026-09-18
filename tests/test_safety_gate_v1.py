from safety_gate import SafetyGate


def test_safety_gate_allows_valid_scope_and_evidence():
    gate = SafetyGate(
        allowed_files=("queue.py", "scheduler.py"),
        approved_tasks=("TASK-1",),
    )

    result = gate.evaluate(
        task_id="TASK-1",
        changed_files=["queue.py", "scheduler.py"],
        evidence={"status": "PASS", "notes": "ok"},
        status="complete",
    )

    assert result.allowed is True


def test_safety_gate_rejects_unexpected_modified_files():
    gate = SafetyGate(allowed_files=("queue.py",))

    result = gate.check_modified_files(["queue.py", "tmp/extra.txt"])

    assert result.allowed is False
    assert result.reason == "unexpected modified files"


def test_safety_gate_rejects_task_outside_approved_scope():
    gate = SafetyGate(approved_tasks=("TASK-1",))

    result = gate.check_task_scope("TASK-2")

    assert result.allowed is False
    assert result.reason == "task outside approved scope"


def test_safety_gate_rejects_missing_verification_evidence():
    gate = SafetyGate()

    result = gate.check_verification_evidence({})

    assert result.allowed is False
    assert result.reason == "missing verification evidence"


def test_safety_gate_rejects_invalid_status():
    gate = SafetyGate()

    result = gate.check_task_status("running")

    assert result.allowed is False
    assert result.reason == "invalid task status"
