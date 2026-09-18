from executor import ExecutionRequest, Executor


def test_executor_returns_backend_response():
    def backend(request):
        return {"task_id": request.task_id, "status": "ok"}

    executor = Executor(backend=backend)
    request = ExecutionRequest(task_id="TASK-1", task_name="unit check", payload={"value": 1})

    result = executor.execute(request)

    assert result.task_id == "TASK-1"
    assert result.task_name == "unit check"
    assert result.status == "success"
    assert result.response == {"task_id": "TASK-1", "status": "ok"}


def test_executor_rejects_invalid_request():
    executor = Executor()

    try:
        executor.execute(ExecutionRequest(task_id="", task_name="bad"))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_executor_uses_noop_backend_when_unset():
    executor = Executor()
    request = ExecutionRequest(task_id="TASK-2", task_name="noop")

    result = executor.execute(request)

    assert result.response == {"status": "noop"}
    assert result.metadata["backend"] == "noop"


def test_executor_invokes_backend_exactly_once():
    calls = []

    def backend(request):
        calls.append(request.task_id)
        return {"task_id": request.task_id, "status": "done"}

    executor = Executor(backend=backend)
    request = ExecutionRequest(task_id="TASK-3", task_name="single call")

    result = executor.execute(request)

    assert calls == ["TASK-3"]
    assert result.response == {"task_id": "TASK-3", "status": "done"}
