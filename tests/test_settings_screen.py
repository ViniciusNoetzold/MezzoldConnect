from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import flet as ft

from screens.settings import SettingsScreen, settings_flags_for_role


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list[object] = []
        self.routes: list[str] = []
        self.urls: list[str] = []
        self.theme_mode = None
        self.theme = None
        self.session = Mock()

    def update(self) -> None:
        return None

    def show_dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> object | None:
        return self.dialogs.pop() if self.dialogs else None

    def go(self, route: str) -> None:
        self.routes.append(route)

    def run_thread(self, handler, *args, **kwargs) -> None:
        handler(*args, **kwargs)

    def launch_url(self, url: str) -> None:
        self.urls.append(url)


class SettingsScreenTests(unittest.TestCase):
    def _screen(self, role: str, can_manage: bool = False) -> tuple[SettingsScreen, FakePage]:
        page = FakePage()
        record = Mock(id=7, username="tester", role=role)
        config = Mock(
            api_version="v24.0",
            token="protected-secret",
            phone_number_id="phone",
            business_account_id="business",
            webhook_url="",
            default_template="template",
            default_language="pt_BR",
            delivery_mode="official_api",
            dry_run=True,
            send_interval_seconds=30.0,
            daily_send_limit=100,
        )
        patches = [
            patch("screens.settings.auth.get_current_user_record", return_value=record),
            patch("screens.settings.auth.get_current_user_id", return_value=7),
            patch("screens.settings.auth.get_current_user", return_value="tester"),
            patch("screens.settings.auth.get_current_role", return_value=role),
            patch("screens.settings.auth.can_manage_users", return_value=can_manage),
            patch("screens.settings.whatsapp.load_config", return_value=config),
            patch(
                "screens.settings.whatsapp.get_whatsapp_web_status",
                return_value={"status": "disconnected", "label": "desconectado", "message": "ok"},
            ),
            patch("screens.settings.database.get_setting", side_effect=lambda _key, default="": default),
            patch.object(SettingsScreen, "_load_license", return_value={}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return SettingsScreen(page), page

    def test_role_flags_keep_team_out_of_user_management(self) -> None:
        self.assertEqual(settings_flags_for_role("cliente"), {"advanced": False, "technical": False, "manage_users": False})
        self.assertEqual(settings_flags_for_role("equipe"), {"advanced": True, "technical": True, "manage_users": False})
        self.assertTrue(settings_flags_for_role("admin")["manage_users"])
        self.assertTrue(settings_flags_for_role("mezzold_master")["manage_users"])

    def test_screen_construction_and_token_redaction_by_role(self) -> None:
        client, _ = self._screen("cliente")
        self.assertFalse(client.is_technical)
        self.assertEqual(len(client.tab_pages), 3)
        self.assertEqual(client.cfg_token.value, "")

        team, _ = self._screen("equipe")
        self.assertTrue(team.is_technical)
        self.assertFalse(team.can_manage_users)
        self.assertEqual(len(team.tab_pages), 3)

        admin, _ = self._screen("admin", can_manage=True)
        self.assertTrue(admin.can_manage_users)
        self.assertEqual(len(admin.tab_pages), 4)

    def test_password_change_uses_numeric_user_id(self) -> None:
        screen, _ = self._screen("cliente")
        screen.old_password.value = "old-pass"
        screen.new_password.value = "new-pass-123"
        screen.confirm_new_password.value = "new-pass-123"
        with patch("screens.settings.auth.change_password") as changer:
            screen.change_password()
        changer.assert_called_once_with(7, "old-pass", "new-pass-123")

    def test_backup_prefers_consistent_database_api(self) -> None:
        screen, _ = self._screen("cliente")
        with patch("screens.settings.database.create_backup", return_value="backup.sqlite3") as creator:
            screen.make_backup()
        creator.assert_called_once_with()
        self.assertIn("backup.sqlite3", screen.backup_status.value)

    def test_update_checker_receives_complete_contract(self) -> None:
        screen, _ = self._screen("cliente")
        result = Mock(status="current", has_update=False, download_url="https://example.test")
        with patch("screens.settings.app_update.check_for_updates", return_value=result) as checker:
            screen.check_updates()
        checker.assert_called_once_with(
            "2.1.0",
            "",
            download_url="https://github.com/ViniciusNoetzold/MezzoldConnect/releases",
            channel="stable",
        )

    def test_startup_saves_worker_minimized_flag(self) -> None:
        screen, _ = self._screen("cliente")
        screen.startup_switch.value = True
        screen.startup_minimized.value = True
        with patch("screens.settings.startup.is_supported", return_value=True), patch(
            "screens.settings.startup.set_startup_enabled"
        ) as setter:
            screen.save_system_settings()
        setter.assert_called_once_with(True, minimized=True)

    def test_technical_save_requires_password_and_visible_code(self) -> None:
        screen, page = self._screen("equipe")
        callback = Mock()
        with patch("screens.settings.auth.verify_user_password", return_value=True) as verifier:
            screen._confirm_technical_save(callback)
            dialog = page.dialogs[-1]
            code = str(dialog.content.controls[1].value).split(":", 1)[1].strip()
            dialog.content.controls[2].value = "correct-password"
            dialog.content.controls[3].value = code
            dialog.actions[1].on_click(None)
        verifier.assert_called_once_with(7, "correct-password")
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
