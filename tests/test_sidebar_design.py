from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

from screens import common


class FakePage:
    def __init__(self) -> None:
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1

    def go(self, _route: str) -> None:
        return None


class SidebarDesignTests(unittest.TestCase):
    def test_sidebar_expands_on_hover_without_animating_routes(self) -> None:
        page = FakePage()
        with patch("screens.common.auth.get_current_user", return_value="tester"), patch(
            "screens.common.auth.get_current_role", return_value="admin"
        ), patch("screens.common.database.get_setting", return_value="Mezzold"):
            sidebar = common.build_sidebar(page, common.ROUTE_DASHBOARD)

        brand_label = sidebar.content.controls[0].controls[1]
        first_nav_label = sidebar.content.controls[2].controls[0].title
        self.assertEqual(sidebar.width, common.SIDEBAR_COLLAPSED_WIDTH)
        self.assertEqual(brand_label.opacity, 0)
        self.assertEqual(first_nav_label.opacity, 0)

        sidebar.on_hover(SimpleNamespace(data="true"))
        self.assertEqual(sidebar.width, common.SIDEBAR_EXPANDED_WIDTH)
        self.assertEqual(brand_label.opacity, 1)
        self.assertEqual(first_nav_label.opacity, 1)

        sidebar.on_hover(SimpleNamespace(data="false"))
        self.assertEqual(sidebar.width, common.SIDEBAR_COLLAPSED_WIDTH)
        self.assertEqual(brand_label.opacity, 0)
        self.assertGreaterEqual(page.update_count, 2)

        transitions = common.disabled_page_transitions()
        self.assertEqual(transitions.windows, ft.PageTransitionTheme.NONE)
        self.assertEqual(transitions.android, ft.PageTransitionTheme.NONE)
        self.assertEqual(transitions.ios, ft.PageTransitionTheme.NONE)


if __name__ == "__main__":
    unittest.main()
