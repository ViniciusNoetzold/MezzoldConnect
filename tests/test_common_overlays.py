from __future__ import annotations

import unittest

from screens import common


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list[object] = []

    def show_dialog(self, dialog: object) -> None:
        dialog.open = True
        self.dialogs.append(dialog)


class CommonOverlayTests(unittest.TestCase):
    def test_transient_snackbars_reuse_the_active_overlay_without_a_fixed_key(self) -> None:
        page = FakePage()

        first = common.show_snack(page, "Primeira")
        second = common.show_snack(page, "Segunda")

        self.assertIsNone(first.key)
        self.assertIsNone(second.key)
        self.assertIs(first, second)
        self.assertEqual(first.content.value, "Segunda")
        self.assertEqual(page.dialogs, [first])

    def test_generic_alert_has_no_fixed_key_but_explicit_key_is_preserved(self) -> None:
        page = FakePage()

        generic = common.show_alert(page, "Aviso", "Conteúdo")
        identified = common.show_alert(page, "Ajuda", "Conteúdo", key="help-dialog")

        self.assertIsNone(generic.key)
        self.assertEqual(identified.key, "help-dialog")


if __name__ == "__main__":
    unittest.main()
