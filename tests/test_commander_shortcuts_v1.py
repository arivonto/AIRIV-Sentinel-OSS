"""Commander copy/paste shortcut policy regression."""

import pytest

from sentinel.commander_shortcuts import (
    ShortcutAction,
    ShortcutEvent,
    decide_copy_paste_shortcut,
)


def decide(**changes):
    values = dict(key="c", ctrl=True, target_copyable=True)
    values.update(changes)
    return decide_copy_paste_shortcut(ShortcutEvent(**values))


def test_ctrl_c_copies_copyable_surface_and_prevents_default():
    result = decide()

    assert result.action is ShortcutAction.COPY
    assert result.reason == "copyable_surface_copy"
    assert result.browser_default_allowed is False


def test_cmd_c_is_supported_for_desktop_browser_surfaces():
    result = decide(ctrl=False, meta=True)

    assert result.action is ShortcutAction.COPY
    assert result.reason == "copyable_surface_copy"


def test_native_editable_copy_and_paste_are_preserved():
    copy = decide(target_editable=True, target_copyable=False)
    paste = decide(key="v", target_editable=True, target_copyable=False)

    assert copy.action is ShortcutAction.COPY
    assert copy.browser_default_allowed is True
    assert paste.action is ShortcutAction.PASTE
    assert paste.browser_default_allowed is True


def test_paste_outside_editable_target_is_ignored():
    result = decide(key="v", target_editable=False, target_copyable=True)

    assert result.action is ShortcutAction.IGNORE
    assert result.reason == "paste_target_not_editable"
    assert result.browser_default_allowed is True


@pytest.mark.parametrize(
    "changes",
    [
        {"key": "x"},
        {"ctrl": False, "meta": False},
        {"alt": True},
        {"target_copyable": False},
    ],
)
def test_non_matching_or_unsafe_shortcuts_are_ignored(changes):
    result = decide(**changes)

    assert result.action is ShortcutAction.IGNORE


def test_wrong_event_type_rejected():
    with pytest.raises(TypeError):
        decide_copy_paste_shortcut(object())
