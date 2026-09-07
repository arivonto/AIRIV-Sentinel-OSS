"""Temporary controlled-live activation lease.

Temporarily activates exactly one test/local bound remediation effect
and restores the exact previous instance-local policy/catalog state.

No remediation execution occurs here.
"""

from __future__ import annotations

from sentinel.bound_effect_contract import (
    BoundRemediationEffectContract,
    bound_effect_policy_run_id,
    validate_bound_effect_contract,
)


import threading
from dataclasses import dataclass
from typing import Any

from sentinel.remediation_action_catalog import RemediationActionEntry


_LEASE_LOCK = threading.RLock()
_LEASED_PAIRS: set[tuple[int, int]] = set()


@dataclass(frozen=True, slots=True)
class ActivationSnapshot:
    allowed_actions: frozenset[str]
    bound_attribute_existed: bool
    bound_effects: tuple[tuple[str, Any], ...]
    catalog_entries: tuple[tuple[str, Any], ...]
    catalog_triggers: tuple[tuple[str, str], ...]


class TemporaryLiveRemediationActivationLease:
    """Exclusive temporary activation for one policy/catalog instance pair."""

    def __init__(
        self,
        *,
        policy,
        catalog,
        effect: BoundRemediationEffectContract,
        entry: RemediationActionEntry,
        trigger: str | None = None,
    ) -> None:
        validate_bound_effect_contract(
            effect
        )

        if not isinstance(entry, RemediationActionEntry):
            raise TypeError("entry must be RemediationActionEntry")

        if entry.action != effect.action:
            raise ValueError("catalog_effect_action_mismatch")

        if trigger is not None:
            if not isinstance(trigger, str):
                raise TypeError("trigger must be str or None")
            if not trigger.strip():
                raise ValueError("trigger must not be empty")

        self.policy = policy
        self.catalog = catalog
        self.effect = effect
        self.entry = entry
        self.trigger = trigger

        self._active = False
        self._pair_claimed = False
        self._snapshot: ActivationSnapshot | None = None

        self._allowed_ref = None
        self._bound_ref = None
        self._entries_ref = None
        self._triggers_ref = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def pair_key(self) -> tuple[int, int]:
        return (id(self.policy), id(self.catalog))

    def _claim(self) -> None:
        with _LEASE_LOCK:
            if self.pair_key in _LEASED_PAIRS:
                raise RuntimeError("activation_lease_already_held")

            _LEASED_PAIRS.add(self.pair_key)
            self._pair_claimed = True

    def _release(self) -> None:
        if not self._pair_claimed:
            return

        with _LEASE_LOCK:
            _LEASED_PAIRS.discard(self.pair_key)

        self._pair_claimed = False

    def _capture(self) -> ActivationSnapshot:
        allowed = getattr(self.policy, "allowed_actions", None)
        entries = getattr(self.catalog, "_entries", None)
        triggers = getattr(self.catalog, "_trigger_map", None)

        if not isinstance(allowed, set):
            raise TypeError("policy.allowed_actions must be set")

        if not isinstance(entries, dict):
            raise TypeError("catalog._entries must be dict")

        if not isinstance(triggers, dict):
            raise TypeError("catalog._trigger_map must be dict")

        bound_existed = hasattr(
            self.policy,
            "_bound_effects_by_run",
        )

        bound = getattr(
            self.policy,
            "_bound_effects_by_run",
            {},
        )

        if not isinstance(bound, dict):
            raise TypeError("policy bound configuration must be dict")

        self._allowed_ref = allowed
        self._entries_ref = entries
        self._triggers_ref = triggers
        self._bound_ref = bound if bound_existed else None

        return ActivationSnapshot(
            allowed_actions=frozenset(allowed),
            bound_attribute_existed=bound_existed,
            bound_effects=tuple(bound.items()),
            catalog_entries=tuple(entries.items()),
            catalog_triggers=tuple(triggers.items()),
        )

    def _validate_free(
        self,
        snapshot: ActivationSnapshot,
    ) -> None:
        if self.effect.action in snapshot.allowed_actions:
            raise RuntimeError("lease_action_already_allowed")

        if any(
            action == self.entry.action
            for action, _ in snapshot.catalog_entries
        ):
            raise RuntimeError("lease_action_already_registered")

        if any(
            run_id == bound_effect_policy_run_id(self.effect)
            for run_id, _ in snapshot.bound_effects
        ):
            raise RuntimeError("lease_run_already_bound")

        if (
            self.trigger is not None
            and any(
                trigger == self.trigger
                for trigger, _ in snapshot.catalog_triggers
            )
        ):
            raise RuntimeError("lease_trigger_already_registered")

    def _restore(self) -> None:
        snapshot = self._snapshot

        if snapshot is None:
            return

        if not isinstance(self._allowed_ref, set):
            raise RuntimeError("activation_restore_allowed_ref_invalid")

        if not isinstance(self._entries_ref, dict):
            raise RuntimeError("activation_restore_entries_ref_invalid")

        if not isinstance(self._triggers_ref, dict):
            raise RuntimeError("activation_restore_triggers_ref_invalid")

        self.policy.allowed_actions = self._allowed_ref
        self._allowed_ref.clear()
        self._allowed_ref.update(snapshot.allowed_actions)

        self.catalog._entries = self._entries_ref
        self._entries_ref.clear()
        self._entries_ref.update(dict(snapshot.catalog_entries))

        self.catalog._trigger_map = self._triggers_ref
        self._triggers_ref.clear()
        self._triggers_ref.update(dict(snapshot.catalog_triggers))

        if snapshot.bound_attribute_existed:
            if not isinstance(self._bound_ref, dict):
                raise RuntimeError("activation_restore_bound_ref_invalid")

            self.policy._bound_effects_by_run = self._bound_ref

            self._bound_ref.clear()
            self._bound_ref.update(dict(snapshot.bound_effects))

        elif hasattr(
            self.policy,
            "_bound_effects_by_run",
        ):
            delattr(
                self.policy,
                "_bound_effects_by_run",
            )

    def _assert_restored(self) -> None:
        snapshot = self._snapshot

        if snapshot is None:
            return

        if frozenset(self.policy.allowed_actions) != snapshot.allowed_actions:
            raise RuntimeError("activation_restore_policy_mismatch")

        if tuple(self.catalog._entries.items()) != snapshot.catalog_entries:
            raise RuntimeError("activation_restore_catalog_mismatch")

        if (
            tuple(self.catalog._trigger_map.items())
            != snapshot.catalog_triggers
        ):
            raise RuntimeError("activation_restore_trigger_mismatch")

        exists = hasattr(
            self.policy,
            "_bound_effects_by_run",
        )

        if exists != snapshot.bound_attribute_existed:
            raise RuntimeError("activation_restore_bound_presence_mismatch")

        if exists:
            if (
                tuple(self.policy._bound_effects_by_run.items())
                != snapshot.bound_effects
            ):
                raise RuntimeError("activation_restore_bound_mismatch")

    def activate(self):
        if self._active:
            raise RuntimeError("activation_lease_already_active")

        self._claim()

        try:
            self._snapshot = self._capture()

            self._validate_free(
                self._snapshot
            )

            # Exact activation order.
            self.policy.allowed_actions.add(
                self.effect.action
            )

            self.policy.configure_bound_effect(
                self.effect
            )

            self.catalog.register(
                self.entry,
                trigger=self.trigger,
            )

            if self.effect.action not in self.policy.allowed_actions:
                raise RuntimeError("lease_policy_activation_failed")

            if (
                bound_effect_policy_run_id(self.effect)
                not in self.policy.list_bound_runs()
            ):
                raise RuntimeError("lease_bound_activation_failed")

            if self.catalog.get(self.entry.action) != self.entry:
                raise RuntimeError("lease_catalog_activation_failed")

            if self.trigger is not None:
                if (
                    self.catalog.select_for_trigger(self.trigger)
                    != self.entry
                ):
                    raise RuntimeError("lease_trigger_activation_failed")

            self._active = True
            return self

        except Exception:
            try:
                self._restore()
                self._assert_restored()
            finally:
                self._active = False
                self._release()

            raise

    def close(self) -> bool:
        if not self._active and self._snapshot is None:
            self._release()
            return False

        try:
            self._restore()
            self._assert_restored()
        finally:
            self._active = False
            self._snapshot = None
            self._release()

        return True

    def __enter__(self):
        return self.activate()

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        self.close()
        return False
