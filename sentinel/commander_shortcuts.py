"""Commander UI shortcut policy.

This module is side-effect free. It defines copy/paste keyboard behavior that
UI surfaces can adopt consistently without granting shell or host authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ShortcutAction(str, Enum):
    COPY = "COPY"
    PASTE = "PASTE"
    IGNORE = "IGNORE"


@dataclass(frozen=True, slots=True)
class ShortcutEvent:
    key: str
    ctrl: bool = False
    meta: bool = False
    shift: bool = False
    alt: bool = False
    target_editable: bool = False
    target_copyable: bool = False


@dataclass(frozen=True, slots=True)
class ShortcutDecision:
    action: ShortcutAction
    reason: str
    browser_default_allowed: bool


def decide_copy_paste_shortcut(event: ShortcutEvent) -> ShortcutDecision:
    """Classify copy/paste shortcuts for Sentinel UI surfaces."""

    if type(event) is not ShortcutEvent:
        raise TypeError("ShortcutEvent required")

    key = event.key.lower()
    command_modifier = (event.ctrl or event.meta) and not event.alt

    if not command_modifier or key not in ("c", "v"):
        return ShortcutDecision(
            action=ShortcutAction.IGNORE,
            reason="not_copy_paste_shortcut",
            browser_default_allowed=True,
        )

    if key == "c":
        if event.target_editable:
            return ShortcutDecision(
                action=ShortcutAction.COPY,
                reason="native_editable_copy",
                browser_default_allowed=True,
            )
        if event.target_copyable:
            return ShortcutDecision(
                action=ShortcutAction.COPY,
                reason="copyable_surface_copy",
                browser_default_allowed=False,
            )
        return ShortcutDecision(
            action=ShortcutAction.IGNORE,
            reason="copy_target_not_copyable",
            browser_default_allowed=True,
        )

    if event.target_editable:
        return ShortcutDecision(
            action=ShortcutAction.PASTE,
            reason="native_editable_paste",
            browser_default_allowed=True,
        )

    return ShortcutDecision(
        action=ShortcutAction.IGNORE,
        reason="paste_target_not_editable",
        browser_default_allowed=True,
    )
