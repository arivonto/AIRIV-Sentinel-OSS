from __future__ import annotations

import pytest

from executor_factory import ExecutorFactory, create_executor
from local_executor import LocalExecutor
from ollama_executor import OllamaExecutor
from roo_executor import RooExecutor


def test_factory_returns_local_executor():
    assert isinstance(create_executor({"provider": "local"}), LocalExecutor)


def test_factory_returns_roo_executor_with_configured_callable():
    roo = lambda request: {"ok": True}

    executor = ExecutorFactory.create({"provider": "roo", "roo": roo})

    assert isinstance(executor, RooExecutor)
    assert executor.backend is roo


def test_factory_returns_ollama_executor_with_configuration():
    http_post = lambda url, payload: {}

    executor = create_executor(
        {
            "provider": "ollama",
            "endpoint": "http://ollama.test",
            "model": "custom:model",
            "http_post": http_post,
        }
    )

    assert isinstance(executor, OllamaExecutor)
    assert executor.endpoint == "http://ollama.test"
    assert executor.model == "custom:model"
    assert executor._http_post is http_post


@pytest.mark.parametrize("provider", ["unknown", "", "  "])
def test_factory_rejects_unsupported_or_empty_provider(provider):
    with pytest.raises(ValueError):
        create_executor({"provider": provider})


def test_factory_requires_mapping_configuration():
    with pytest.raises(TypeError, match="configuration must be a mapping"):
        create_executor(None)
