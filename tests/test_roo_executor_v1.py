from __future__ import annotations

import pytest

from executor import ExecutionRequest, ExecutionResult
from roo_executor import RooExecutor


def test_roo_executor_invokes_roo_and_returns_execution_result():
    requests = []

    def roo(request):
        requests.append(request)
        return {"message": "handled by Roo"}

    request = ExecutionRequest(
        task_id="TASK-001",
        task_name="echo",
        payload={"message": "hello"},
    )

    result = RooExecutor(roo).execute(request)

    assert requests == [request]
    assert isinstance(result, ExecutionResult)
    assert result.task_id == "TASK-001"
    assert result.task_name == "echo"
    assert result.status == "success"
    assert result.response == {"message": "handled by Roo"}
    assert result.metadata["backend"] == "roo"


def test_roo_executor_preserves_executor_request_validation():
    with pytest.raises(TypeError, match="request must be ExecutionRequest"):
        RooExecutor(lambda request: None).execute(object())


def test_roo_executor_requires_callable_roo():
    with pytest.raises(TypeError, match="roo must be callable"):
        RooExecutor(None)
