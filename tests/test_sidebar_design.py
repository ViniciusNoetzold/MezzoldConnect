from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

from screens import common


class FakePage:
    def __init__(self) -> None:
        self.update_count = 0
        self.route = common.ROUTE_DASHBOARD
        self.routes: list[str] = []

    def update(self) -> None:
        self.update_count += 1

    def go(self, route: str) -> None:
        self.route = route
        self.routes.append(route)


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
        self.assertTrue(common.sidebar_is_expanded(page))

        update_count = page.update_count
        sidebar.on_hover(SimpleNamespace(data="true"))
        self.assertEqual(page.update_count, update_count)

        with patch("screens.common.auth.get_current_user", return_value="tester"), patch(
            "screens.common.auth.get_current_role", return_value="admin"
        ), patch("screens.common.database.get_setting", return_value="Mezzold"):
            rebuilt_sidebar = common.build_sidebar(page, common.ROUTE_CONTACTS)

        rebuilt_brand_label = rebuilt_sidebar.content.controls[0].controls[1]
        rebuilt_nav_label = rebuilt_sidebar.content.controls[2].controls[0].title
        self.assertEqual(rebuilt_sidebar.width, common.SIDEBAR_EXPANDED_WIDTH)
        self.assertEqual(rebuilt_brand_label.opacity, 1)
        self.assertEqual(rebuilt_nav_label.opacity, 1)

        rebuilt_sidebar.on_hover(SimpleNamespace(data="false"))
        self.assertEqual(rebuilt_sidebar.width, common.SIDEBAR_COLLAPSED_WIDTH)
        self.assertEqual(rebuilt_brand_label.opacity, 0)
        self.assertGreaterEqual(page.update_count, 2)
        self.assertFalse(common.sidebar_is_expanded(page))

        with patch("screens.common.auth.get_current_user", return_value="tester"), patch(
            "screens.common.auth.get_current_role", return_value="admin"
        ), patch("screens.common.database.get_setting", return_value="Mezzold"):
            collapsed_rebuild = common.build_sidebar(page, common.ROUTE_HELP)
        self.assertEqual(collapsed_rebuild.width, common.SIDEBAR_COLLAPSED_WIDTH)
        self.assertEqual(collapsed_rebuild.content.controls[0].controls[1].opacity, 0)

        transitions = common.disabled_page_transitions()
        self.assertEqual(transitions.windows, ft.PageTransitionTheme.NONE)
        self.assertEqual(transitions.android, ft.PageTransitionTheme.NONE)
        self.assertEqual(transitions.ios, ft.PageTransitionTheme.NONE)

    def test_stale_hover_leave_during_route_rebuild_does_not_collapse_sidebar(self) -> None:
        page = FakePage()
        with patch("screens.common.auth.get_current_user", return_value="tester"), patch(
            "screens.common.auth.get_current_role", return_value="admin"
        ), patch("screens.common.database.get_setting", return_value="Mezzold"):
            old_sidebar = common.build_sidebar(page, common.ROUTE_DASHBOARD)

        old_sidebar.on_hover(SimpleNamespace(data="true"))
        self.assertTrue(common.sidebar_is_expanded(page))
        updates_after_expand = page.update_count

        common.navigate(page, common.ROUTE_CONNECTION)
        old_sidebar.on_hover(SimpleNamespace(data="false"))
        self.assertTrue(common.sidebar_is_expanded(page))
        self.assertEqual(old_sidebar.width, common.SIDEBAR_EXPANDED_WIDTH)
        self.assertEqual(page.update_count, updates_after_expand)

        with patch("screens.common.auth.get_current_user", return_value="tester"), patch(
            "screens.common.auth.get_current_role", return_value="admin"
        ), patch("screens.common.database.get_setting", return_value="Mezzold"):
            new_sidebar = common.build_sidebar(page, common.ROUTE_CONNECTION)

        self.assertEqual(new_sidebar.width, common.SIDEBAR_EXPANDED_WIDTH)
        self.assertEqual(new_sidebar.content.controls[0].controls[1].opacity, 1)

        # A late event from the detached sidebar remains harmless after mount.
        old_sidebar.on_hover(SimpleNamespace(data="false"))
        self.assertTrue(common.sidebar_is_expanded(page))
        self.assertEqual(new_sidebar.width, common.SIDEBAR_EXPANDED_WIDTH)

        # A real pointer leave from the replacement control still collapses it.
        new_sidebar.on_hover(SimpleNamespace(data="false"))
        self.assertFalse(common.sidebar_is_expanded(page))
        self.assertEqual(new_sidebar.width, common.SIDEBAR_COLLAPSED_WIDTH)

    def test_navigation_does_not_rebuild_the_active_route(self) -> None:
        page = FakePage()
        page.route = f"{common.ROUTE_DASHBOARD}?tab=summary"

        common.navigate(page, common.ROUTE_DASHBOARD)
        self.assertEqual(page.routes, [])

        common.navigate(page, common.ROUTE_CONTACTS)
        self.assertEqual(page.routes, [common.ROUTE_CONTACTS])


if __name__ == "__main__":
    unittest.main()
