"""Canonical Commander Intent domain boundary."""

from __future__ import annotations

from enum import Enum


class CommanderIntent(str, Enum):
    """
    Semantic intent selected by the Autonomous Commander.

    CommanderIntent is deliberately independent from:
    - diagnosis status
    - authorization / PolicyDecision
    - execution
    - verification
    - incident final outcome
    """

    NO_ACTION = "NO_ACTION"
    AUTONOMOUS_REMEDIATE = "AUTONOMOUS_REMEDIATE"
    NEED_COMMANDER = "NEED_COMMANDER"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
