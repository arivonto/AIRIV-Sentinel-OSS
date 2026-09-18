from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from local_executor import LocalExecutor
from ollama_executor import OllamaExecutor
from roo_executor import RooExecutor


class ExecutorFactory:
    """Create a supported executor from an explicit provider configuration."""

    @staticmethod
    def create(config: Mapping[str, Any]) -> Any:
        if not isinstance(config, Mapping):
            raise TypeError("executor configuration must be a mapping")

        provider = config.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("executor configuration requires a provider")

        normalized = provider.strip().lower()
        if normalized == "local":
            return LocalExecutor()
        if normalized == "roo":
            return RooExecutor(config.get("roo"))
        if normalized == "ollama":
            options = {
                key: config[key]
                for key in ("endpoint", "model", "http_post")
                if key in config
            }
            return OllamaExecutor(**options)
        raise ValueError(f"unsupported executor provider: {provider}")


def create_executor(config: Mapping[str, Any]) -> Any:
    return ExecutorFactory.create(config)


__all__ = ["ExecutorFactory", "create_executor"]
