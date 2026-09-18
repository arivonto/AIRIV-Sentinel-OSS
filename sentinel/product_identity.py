"""Sentinel product identity and phase guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


OLLAMA_DEFAULT_ENDPOINT = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "qwen3:4b"


class SentinelPhase(str, Enum):
    CORE = "phase_1_core"
    DESKTOP = "phase_2_desktop"
    REMOTE = "phase_3_remote"
    WEB = "phase_4_web"


@dataclass(frozen=True)
class SentinelIdentity:
    name: str
    definition: str
    motto: tuple[str, ...]
    owns: tuple[str, ...]
    provider_owns: tuple[str, ...]
    supported_providers: tuple[str, ...]
    current_phase: SentinelPhase
    primary_platform: str
    excluded_platforms: tuple[str, ...]
    phase1_success_command: tuple[str, ...]

    def accepts_provider(self, provider: str) -> bool:
        normalized = provider.strip().lower()
        return normalized in {item.lower() for item in self.supported_providers}


@dataclass(frozen=True)
class IdentityDecision:
    accepted: bool
    reasons: tuple[str, ...]


SENTINEL_IDENTITY = SentinelIdentity(
    name="AIRIV Sentinel",
    definition=(
        "Linux-first Autonomous Multi-AI Engineering Desktop designed to execute "
        "engineering missions autonomously by orchestrating multiple AI reasoning "
        "providers while maintaining its own engineering identity."
    ),
    motto=("One Mission.", "Any AI.", "Linux First."),
    owns=(
        "Mission",
        "Engineering Brain",
        "Engineering Memory",
        "Engineering Workflow",
        "Verification",
        "Operational Knowledge",
        "Skill Registry",
        "User Experience",
    ),
    provider_owns=("Reasoning", "Analysis", "Explanation", "Code suggestions"),
    supported_providers=(
        "Ollama",
    ),
    current_phase=SentinelPhase.CORE,
    primary_platform="Linux",
    excluded_platforms=("Windows", "macOS"),
    phase1_success_command=(
        "sentinel",
        "mission",
        "Fix this repository until all tests pass.",
    ),
)


def evaluate_identity_alignment(
    *,
    target_phase: SentinelPhase,
    linux_first: bool,
    preserves_ai_independence: bool,
    preserves_mission_ownership: bool,
    preserves_engineering_brain_ownership: bool,
    avoids_vendor_lock_in: bool,
) -> IdentityDecision:
    reasons: list[str] = []

    if target_phase is not SentinelPhase.CORE:
        reasons.append("Phase 1 must stay focused on AIRIV Sentinel Core.")
    if not linux_first:
        reasons.append("Primary platform must remain Linux.")
    if not preserves_ai_independence:
        reasons.append("AI providers must remain interchangeable reasoning resources.")
    if not preserves_mission_ownership:
        reasons.append("Mission ownership must remain inside Sentinel.")
    if not preserves_engineering_brain_ownership:
        reasons.append("Engineering Brain ownership must remain inside Sentinel.")
    if not avoids_vendor_lock_in:
        reasons.append("Implementation must avoid vendor lock-in.")

    return IdentityDecision(accepted=not reasons, reasons=tuple(reasons))
