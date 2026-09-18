from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from executor import ExecutionRequest, ExecutionResult, Executor
from sentinel.product_identity import (
    OLLAMA_DEFAULT_ENDPOINT,
    OLLAMA_DEFAULT_MODEL,
)


HttpPost = Callable[[str, dict[str, Any]], dict[str, Any]]


class OllamaExecutor(Executor):
    """Executor that sends one deterministic request to a local Ollama server."""

    def __init__(
        self,
        *,
        endpoint: str = OLLAMA_DEFAULT_ENDPOINT,
        model: str = OLLAMA_DEFAULT_MODEL,
        http_post: HttpPost | None = None,
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("endpoint must be a non-empty string")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        super().__init__()
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._http_post = http_post or self._post_json

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self._validate_request(request)
        payload = request.payload or {}
        prompt = payload.get("prompt", payload.get("message", request.task_name))
        if not isinstance(prompt, str):
            raise ValueError("request payload prompt must be a string")

        ollama_request = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            response = self._http_post(
                f"{self.endpoint}/api/generate",
                ollama_request,
            )
        except Exception as exc:
            return ExecutionResult(
                task_id=request.task_id,
                task_name=request.task_name,
                status="FAIL",
                response={"error": str(exc)},
                metadata={
                    "backend": "ollama",
                    "endpoint": self.endpoint,
                    "model": self.model,
                },
            )

        return ExecutionResult(
            task_id=request.task_id,
            task_name=request.task_name,
            status="success",
            response=response,
            metadata={
                "backend": "ollama",
                "endpoint": self.endpoint,
                "model": self.model,
            },
        )

    @staticmethod
    def _validate_request(request: ExecutionRequest) -> None:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be ExecutionRequest")
        if not request.task_id.strip():
            raise ValueError("task_id must not be empty")
        if not request.task_name.strip():
            raise ValueError("task_name must not be empty")

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise ValueError("Ollama response must be a JSON object")
        return decoded


__all__ = ["OllamaExecutor"]
