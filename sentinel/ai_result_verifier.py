"""AIRIV Sentinel AI result verification boundary V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sentinel.agent.executor import AgentExecutionResult


@dataclass(frozen=True)
class AIResultVerificationResult:
    """Normalized Sentinel verification result for an AI execution."""

    accepted: bool
    reason: str
    observation: Any = None


class AIResultVerifier:
    """
    Sentinel-owned verification boundary for AI agent results.

    This boundary:
    - does not execute AI agents
    - does not execute system commands
    - does not mutate incident lifecycle
    - does not write evidence directly
    - does not treat AI self-report as verification
    """

    def __init__(
        self,
        verifier: Callable[[AgentExecutionResult], Any],
    ) -> None:
        if not callable(verifier):
            raise TypeError("verifier must be callable")
        self.verifier = verifier

    def verify(
        self,
        result: AgentExecutionResult,
    ) -> AIResultVerificationResult:
        if not isinstance(result, AgentExecutionResult):
            raise TypeError(
                "result must be an AgentExecutionResult"
            )

        try:
            observation = self.verifier(result)

            if isinstance(
                observation,
                AIResultVerificationResult,
            ):
                return observation

            if hasattr(observation, "accepted"):
                return AIResultVerificationResult(
                    accepted=bool(observation.accepted),
                    reason=str(
                        getattr(
                            observation,
                            "reason",
                            "",
                        )
                    ),
                    observation=getattr(
                        observation,
                        "observation",
                        observation,
                    ),
                )

            if isinstance(observation, bool):
                return AIResultVerificationResult(
                    accepted=observation,
                    reason=(
                        "AI result accepted by Sentinel verifier."
                        if observation
                        else
                        "AI result rejected by Sentinel verifier."
                    ),
                    observation=observation,
                )

            return AIResultVerificationResult(
                accepted=False,
                reason=(
                    "AI result verifier returned an "
                    "unsupported verification result."
                ),
                observation=observation,
            )

        except Exception as exc:
            return AIResultVerificationResult(
                accepted=False,
                reason=(
                    "AI result verification failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
                observation=None,
            )
