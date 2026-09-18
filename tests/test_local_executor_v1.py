from executor import ExecutionRequest
from local_executor import LocalExecutor


def test_local_executor_executes_registered_handler():
    executor = LocalExecutor()

    def handler(request):
        return {"task_id": request.task_id, "ok": True}

    executor.register_handler("echo", handler)
    request = ExecutionRequest(
        task_id="TASK-1",
        task_name="echo",
        payload={"task_type": "echo"},
    )

    result = executor.execute(request)

    assert result.status == "success"
    assert result.response == {"task_id": "TASK-1", "ok": True}
    assert result.metadata["task_type"] == "echo"


def test_local_executor_rejects_unknown_task_type():
    executor = LocalExecutor()
    request = ExecutionRequest(
        task_id="TASK-2",
        task_name="unknown",
        payload={"task_type": "missing"},
    )

    result = executor.execute(request)

    assert result.status == "FAIL"
    assert result.response["error"] == "unknown task type: missing"


def test_local_executor_rejects_invalid_handler_registration():
    executor = LocalExecutor()

    try:
        executor.register_handler("", lambda request: None)
        assert False, "expected ValueError"
    except ValueError:
        pass

    try:
        executor.register_handler("task", "not callable")
        assert False, "expected TypeError"
    except TypeError:
        pass


def test_local_executor_returns_fail_when_handler_raises():
    executor = LocalExecutor()

    def handler(request):
        raise RuntimeError("boom")

    executor.register_handler("fail", handler)
    request = ExecutionRequest(
        task_id="TASK-3",
        task_name="fail",
        payload={"task_type": "fail"},
    )

    result = executor.execute(request)

    assert result.status == "FAIL"
    assert result.response["error"] == "boom"
