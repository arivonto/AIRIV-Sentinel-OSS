from __future__ import annotations

import pytest

from executor import ExecutionRequest, ExecutionResult
from ollama_executor import OllamaExecutor
from sentinel.product_identity import OLLAMA_DEFAULT_ENDPOINT, OLLAMA_DEFAULT_MODEL


def test_ollama_executor_calls_configured_generate_endpoint():
    calls = []

    def http_post(url, payload):
        calls.append((url, payload))
        return {"response": "hello from Ollama"}

    request = ExecutionRequest(
        task_id="TASK-001",
        task_name="echo",
        payload={"message": "hello"},
    )
    result = OllamaExecutor(http_post=http_post).execute(request)

    assert isinstance(result, ExecutionResult)
    assert calls == [
        (
            f"{OLLAMA_DEFAULT_ENDPOINT}/api/generate",
            {"model": OLLAMA_DEFAULT_MODEL, "prompt": "hello", "stream": False},
        )
    ]
    assert result.status == "success"
    assert result.response == {"response": "hello from Ollama"}
    assert result.metadata["model"] == OLLAMA_DEFAULT_MODEL


def test_ollama_executor_supports_custom_endpoint_and_model():
    calls = []
    executor = OllamaExecutor(
        endpoint="http://ollama.test/",
        model="custom:model",
        http_post=lambda url, payload: calls.append((url, payload)) or {},
    )

    executor.execute(ExecutionRequest("TASK-002", "summarize", {"prompt": "text"}))

    assert calls == [
        (
            "http://ollama.test/api/generate",
            {"model": "custom:model", "prompt": "text", "stream": False},
        )
    ]


def test_ollama_executor_returns_failure_result_when_endpoint_fails():
    result = OllamaExecutor(
        http_post=lambda url, payload: (_ for _ in ()).throw(ConnectionError("offline")),
    ).execute(ExecutionRequest("TASK-003", "echo"))

    assert result.status == "FAIL"
    assert result.response == {"error": "offline"}


def test_ollama_executor_rejects_invalid_request():
    with pytest.raises(TypeError, match="request must be ExecutionRequest"):
        OllamaExecutor(http_post=lambda url, payload: {}).execute(object())
