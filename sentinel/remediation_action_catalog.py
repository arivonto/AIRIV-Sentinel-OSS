from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RemediationActionEntry:
    """
    Registered remediation action.

    The catalog owns operational definitions.
    Diagnosis does not generate commands.
    """

    action: str
    command: str
    rationale: str


class RemediationActionCatalog:
    """
    Explicit registry of remediation actions.

    Registration is controlled and deterministic.
    Selection is based only on explicitly registered mappings.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RemediationActionEntry] = {}
        self._trigger_map: dict[str, str] = {}

    def register(
        self,
        entry: RemediationActionEntry,
        *,
        trigger: str | None = None,
    ) -> None:
        if not entry.action:
            raise ValueError("action must not be empty")

        if not entry.command:
            raise ValueError("command must not be empty")

        if entry.action in self._entries:
            raise ValueError(
                f"remediation action already registered: {entry.action}"
            )

        self._entries[entry.action] = entry

        if trigger is not None:
            if not trigger:
                raise ValueError("trigger must not be empty")

            if trigger in self._trigger_map:
                raise ValueError(
                    f"remediation trigger already registered: {trigger}"
                )

            self._trigger_map[trigger] = entry.action

    def get(self, action: str) -> RemediationActionEntry:
        try:
            return self._entries[action]
        except KeyError as exc:
            raise KeyError(
                f"remediation action not registered: {action}"
            ) from exc

    def select_for_trigger(self, trigger: str) -> RemediationActionEntry:
        try:
            action = self._trigger_map[trigger]
        except KeyError as exc:
            raise KeyError(
                f"no remediation action registered for trigger: {trigger}"
            ) from exc

        return self.get(action)

    def list_actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def list_triggers(self) -> tuple[str, ...]:
        return tuple(sorted(self._trigger_map))


class RemediationActionSelector:
    """
    Selects an action only from the registered catalog.

    No command generation is permitted here.
    """

    def __init__(self, catalog: RemediationActionCatalog) -> None:
        if not isinstance(catalog, RemediationActionCatalog):
            raise TypeError(
                "catalog must be a RemediationActionCatalog"
            )

        self.catalog = catalog

    def select(
        self,
        *,
        incident: Any,
        diagnosis: Any,
    ) -> RemediationActionEntry:
        if incident.incident_id is None:
            raise ValueError("incident must have an incident_id")

        if diagnosis.status.value != "ESTABLISHED":
            raise ValueError(
                "only ESTABLISHED diagnosis may select remediation"
            )

        trigger = getattr(incident, "anomaly_type", None)

        if not trigger:
            raise ValueError(
                "incident must provide anomaly_type for remediation selection"
            )

        return self.catalog.select_for_trigger(trigger)
