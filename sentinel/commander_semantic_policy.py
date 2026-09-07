"""Canonical Commander-owned semantic policy boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommanderSemanticRule:
    """Explicit semantic rule owned by the Commander boundary."""

    trigger: str
    remediation_required: bool
    commander_action_required: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.trigger, str) or not self.trigger.strip():
            raise ValueError("trigger must be a non-empty string")

        if not isinstance(self.remediation_required, bool):
            raise TypeError("remediation_required must be bool")

        if not isinstance(self.commander_action_required, bool):
            raise TypeError("commander_action_required must be bool")

        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")


@dataclass(frozen=True)
class CommanderSemanticFacts:
    """Semantic facts produced by CommanderSemanticPolicy."""

    remediation_required: bool
    commander_action_required: bool
    reason: str
    configured: bool


class CommanderSemanticPolicy:
    """
    Authoritative source for Commander semantic response requirements.

    This boundary:
      - does not diagnose
      - does not authorize
      - does not select executable commands
      - does not execute
      - does not verify
      - does not resolve incidents

    Unconfigured triggers fail closed to NEED_COMMANDER semantics.
    """

    def __init__(self) -> None:
        self._rules: dict[str, CommanderSemanticRule] = {}

    def register(self, rule: CommanderSemanticRule) -> None:
        if rule.trigger in self._rules:
            raise ValueError(
                f"semantic rule already registered: {rule.trigger}"
            )

        self._rules[rule.trigger] = rule

    def get(self, trigger: str) -> CommanderSemanticRule | None:
        return self._rules.get(trigger)

    def list_triggers(self) -> tuple[str, ...]:
        return tuple(sorted(self._rules))

    def assess(self, trigger: str) -> CommanderSemanticFacts:
        if not isinstance(trigger, str) or not trigger.strip():
            raise ValueError("trigger must be a non-empty string")

        rule = self._rules.get(trigger)

        if rule is None:
            return CommanderSemanticFacts(
                remediation_required=False,
                commander_action_required=True,
                reason="semantic_policy_unconfigured",
                configured=False,
            )

        return CommanderSemanticFacts(
            remediation_required=rule.remediation_required,
            commander_action_required=rule.commander_action_required,
            reason=rule.reason,
            configured=True,
        )
