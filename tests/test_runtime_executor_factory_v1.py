from __future__ import annotations

import yaml

from local_executor import LocalExecutor
from ollama_executor import OllamaExecutor
from runtime import Runtime


def write_queue(path):
    path.write_text(
        yaml.safe_dump(
            {
                "mission_id": "MISSION-001",
                "tasks": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_runtime_uses_factory_for_default_local_executor(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    write_queue(queue_file)

    runtime = Runtime(queue_file)

    assert isinstance(runtime.executor, LocalExecutor)


def test_runtime_uses_factory_for_configured_ollama_executor(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    write_queue(queue_file)

    runtime = Runtime(
        queue_file,
        executor_config={
            "provider": "ollama",
            "endpoint": "http://ollama.test",
            "model": "custom:model",
            "http_post": lambda url, payload: {},
        },
    )

    assert isinstance(runtime.executor, OllamaExecutor)
    assert runtime.executor.endpoint == "http://ollama.test"
    assert runtime.executor.model == "custom:model"
