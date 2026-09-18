from verifier import Verifier


def test_verifier_passes_when_success_condition_and_scope_are_valid():
    verifier = Verifier(allowed_files=("queue.py", "scheduler.py"))

    result = verifier.verify_task(
        task={"id": "TASK-1", "name": "queue check"},
        success_condition="2 passed",
        changed_files=["queue.py", "scheduler.py"],
        evidence={"summary": "2 passed", "files": ["queue.py", "scheduler.py"]},
    )

    assert result.status == "PASS"


def test_verifier_fails_on_missing_success_condition():
    verifier = Verifier()

    result = verifier.verify_success(
        task={"id": "TASK-2", "name": "missing proof"},
        success_condition="all checks pass",
        evidence={"summary": "verification missing"},
    )

    assert result.status == "FAIL"
    assert result.details["reason"] == "success condition missing from evidence"


def test_verifier_fails_on_unexpected_modified_files():
    verifier = Verifier(allowed_files=("queue.py",))

    result = verifier.verify_scope(changed_files=["queue.py", "tmp/scratch.txt"])

    assert result.status == "FAIL"
    assert result.details["unexpected"] == ["tmp/scratch.txt"]


def test_verifier_fails_when_changed_files_list_is_empty():
    verifier = Verifier()

    result = verifier.verify_changed_files(changed_files=[])

    assert result.status == "FAIL"
    assert result.details["reason"] == "no changed files were supplied"


def test_verifier_bounded_scope_validation_rejects_out_of_scope_files():
    verifier = Verifier(allowed_files=("queue.py", "scheduler.py"))

    result = verifier.verify_result(
        task={"id": "TASK-3", "name": "scope check"},
        success_condition="scope ok",
        changed_files=["queue.py", "planner.py"],
        evidence={"summary": "scope ok"},
        allowed_files=("queue.py", "scheduler.py"),
    )

    assert result.status == "FAIL"
    assert result.details["unexpected"] == ["planner.py"]
