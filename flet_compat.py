"""Small compatibility guards for the Flet version pinned by the desktop app."""
from __future__ import annotations

from typing import Any


def install_dialog_dismiss_guard() -> None:
    """Make duplicate dialog-dismiss events harmless in Flet 0.86.x.

    The web and desktop clients can report the same dismiss animation more than
    once when a background job updates the page at that exact moment.  Flet's
    managed wrapper then tries to restore an event property on a reconciled
    (frozen) control and raises.  The dialog has already been removed at that
    point, so ignoring only that specific second restore is safe and keeps the
    handler idempotent.
    """

    from flet.controls.base_page import BasePage

    current = BasePage._restore_dialog_on_dismiss
    if getattr(current, "_mezzold_duplicate_dismiss_guard", False):
        return

    original = current

    def safe_restore(self: BasePage, dialog: Any) -> None:
        try:
            original(self, dialog)
        except RuntimeError as exc:
            if "Frozen controls cannot be updated" not in str(exc):
                raise

    setattr(safe_restore, "_mezzold_duplicate_dismiss_guard", True)
    BasePage._restore_dialog_on_dismiss = safe_restore


__all__ = ["install_dialog_dismiss_guard"]
