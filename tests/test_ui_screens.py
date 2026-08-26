from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft

import auth
import campaigns
import main as app_main
import whatsapp
from screens.campaigns import CampaignsScreen, request_campaign_start
from screens.connection import ConnectionScreen
from screens.contacts import ContactsScreen
from screens.dashboard import DashboardScreen
from screens.health import HealthScreen
from screens.help import HelpScreen
from screens.history import HistoryScreen
from screens.import_contacts import ImportContactsScreen
from screens.lead_search import LeadSearchScreen
from screens.login import LoginScreen
from screens.risk import RiskScreen
from screens.schedule import ScheduleScreen
from screens.updates import UpdatesScreen


class FakeSession:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


class FakePage:
    def __init__(self) -> None:
        self.services: list[object] = []
        self.dialogs: list[object] = []
        self.routes: list[str] = []
        self.urls: list[str] = []
        self.session = FakeSession()
        self.web = False
        self.route = "/"
        self.views: list[ft.View] = []
        self.window = SimpleNamespace()
        self.on_keyboard_event = None
        self.theme_mode = None
        self.theme = None
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1

    def show_dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> object | None:
        return self.dialogs.pop() if self.dialogs else None

    def go(self, route: str) -> None:
        self.route = route
        self.routes.append(route)

    def run_thread(self, handler, *args, **kwargs) -> None:
        handler(*args, **kwargs)

    def run_task(self, handler, *args, **kwargs):
        return None

    def launch_url(self, url: str) -> None:
        self.urls.append(url)


def config(*, dry_run: bool = True, mode: str = "official_api") -> whatsapp.WhatsAppConfig:
    return whatsapp.WhatsAppConfig(
        api_version="v24.0",
        token="",
        phone_number_id="",
        business_account_id="",
        webhook_url="",
        default_template="",
        default_language="pt_BR",
        delivery_mode=mode,
        dry_run=dry_run,
        send_interval_seconds=30,
        daily_send_limit=100,
    )


class ScreenConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patchers = [
            patch("screens.common.auth.get_current_user", return_value="tester"),
            patch("screens.common.auth.get_current_role", return_value="admin"),
            patch("screens.common.database.get_setting", side_effect=lambda _key, default="": default),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_every_view_constructs_with_flet_086(self) -> None:
        folders = [{"id": 1, "name": "Importados", "total_contacts": 0}]
        factories = [
            (LoginScreen, [patch("screens.login.auth.user_count", return_value=1)]),
            (DashboardScreen, []),
            (ContactsScreen, []),
            (ImportContactsScreen, [patch("screens.import_contacts.contacts.list_folders", return_value=folders)]),
            (
                CampaignsScreen,
                [
                    patch("screens.campaigns.whatsapp.load_config", return_value=config()),
                    patch("screens.campaigns.contacts.list_folders", return_value=folders),
                    patch("screens.campaigns.contacts.list_contacts", return_value=[]),
                    patch("screens.campaigns.contacts.list_used_contacts", return_value=[]),
                ],
            ),
            (
                ScheduleScreen,
                [
                    patch("screens.schedule.campaigns.list_campaigns", return_value=[]),
                    patch("screens.schedule.campaigns.get_due_campaigns", return_value=[]),
                    patch(
                        "screens.schedule.whatsapp.get_whatsapp_web_status",
                        return_value={"status": "disconnected", "label": "Desconectado"},
                    ),
                ],
            ),
            (RiskScreen, []),
            (HistoryScreen, []),
            (HealthScreen, [patch("screens.health.contacts.list_groups", return_value=[])]),
            (ConnectionScreen, []),
            (UpdatesScreen, [patch("screens.updates.database.get_setting", side_effect=lambda _key, default="": default)]),
            (HelpScreen, []),
            (LeadSearchScreen, []),
        ]
        routes: list[str] = []
        for factory, local_patchers in factories:
            with self.subTest(view=factory.__name__):
                for patcher in local_patchers:
                    patcher.start()
                try:
                    view = factory(FakePage())
                    self.assertIsInstance(view, ft.View)
                    self.assertTrue(view.controls)
                    routes.append(view.route)
                finally:
                    for patcher in reversed(local_patchers):
                        patcher.stop()
        self.assertEqual(len(routes), len(set(routes)))

    def test_initial_root_route_mounts_login_view(self) -> None:
        page = FakePage()
        with patch("main.database.initialize_database"), patch(
            "main.database.get_setting", side_effect=lambda _key, default="": default
        ), patch("main._start_embedded_worker"), patch("main.app_log.app_started"), patch(
            "main.auth.get_current_user", return_value=None
        ), patch("main.TrayIconManager") as tray_manager, patch(
            "screens.login.auth.user_count", return_value=1
        ):
            tray_manager.return_value.start.return_value = False
            app_main.main(page)
        self.assertEqual(len(page.views), 1)
        self.assertIsInstance(page.views[0], LoginScreen)
        self.assertGreater(page.update_count, 0)


class CriticalUiFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.common_patchers = [
            patch("screens.common.auth.get_current_user", return_value="tester"),
            patch("screens.common.auth.get_current_role", return_value="admin"),
            patch("screens.common.database.get_setting", side_effect=lambda _key, default="": default),
        ]
        for patcher in self.common_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_login_sets_complete_session_and_navigates(self) -> None:
        page = FakePage()
        user = auth.User(7, "tester", auth.ROLE_ADMIN, True, False)
        with patch("screens.login.auth.user_count", return_value=1), patch(
            "screens.login.auth.authenticate", return_value=user
        ), patch("screens.login.auth.set_current_user") as setter:
            screen = LoginScreen(page)
            screen.username_input.value = "tester"
            screen.password_input.value = "SenhaForte1!"
            screen.login()
        setter.assert_called_once_with(user)
        self.assertEqual(page.routes[-1], "/dashboard")

    def test_master_hotkey_only_activates_with_all_modifiers(self) -> None:
        page = FakePage()
        with patch("screens.login.auth.user_count", return_value=1):
            screen = LoginScreen(page)
        screen._keyboard_event(SimpleNamespace(key="M", ctrl=True, alt=True, shift=False))
        self.assertFalse(screen.master_mode_active)
        screen._keyboard_event(SimpleNamespace(key="M", ctrl=True, alt=True, shift=True))
        self.assertTrue(screen.master_mode_active)

    def test_master_default_credentials_only_login_after_hotkey(self) -> None:
        page = FakePage()
        user = auth.User(7, "000", auth.ROLE_MEZZOLD_MASTER, True, False)
        with patch("screens.login.auth.user_count", return_value=1), patch(
            "screens.login.auth.is_master_bootstrap_attempt", return_value=True
        ), patch(
            "screens.login.auth.ensure_master_admin", return_value=user
        ) as ensure_master, patch("screens.login.auth.set_current_user") as setter:
            screen = LoginScreen(page)
            screen.username_input.value = auth.MASTER_BOOTSTRAP_USERNAME
            screen.password_input.value = auth.MASTER_BOOTSTRAP_DEFAULT_PASSWORD
            screen.login()

            ensure_master.assert_not_called()
            self.assertIn("Modo autorizado", screen.error_text.value)
            self.assertFalse(page.routes)

            screen._keyboard_event(SimpleNamespace(key="M", ctrl=True, alt=True, shift=True))
            screen.username_input.value = auth.MASTER_BOOTSTRAP_USERNAME
            screen.password_input.value = auth.MASTER_BOOTSTRAP_DEFAULT_PASSWORD
            screen.login()

        ensure_master.assert_called_once_with(
            auth.MASTER_BOOTSTRAP_USERNAME,
            auth.MASTER_BOOTSTRAP_DEFAULT_PASSWORD,
        )
        setter.assert_called_once_with(user)
        self.assertEqual(page.routes[-1], "/dashboard")

    def test_scheduled_campaign_uses_only_eligible_contacts(self) -> None:
        page = FakePage()
        folders = [{"id": 1, "name": "Clientes", "total_contacts": 2}]
        contact_rows = [
            {"id": 1, "name": "A", "phone": "5511999999999", "opt_in": 1, "blacklisted": 0},
            {"id": 2, "name": "B", "phone": "5511888888888", "opt_in": 0, "blacklisted": 0},
        ]
        with patch("screens.campaigns.whatsapp.load_config", return_value=config()), patch(
            "screens.campaigns.contacts.list_folders", return_value=folders
        ), patch("screens.campaigns.contacts.list_contacts", return_value=contact_rows), patch(
            "screens.campaigns.contacts.list_used_contacts", return_value=[]
        ), patch("screens.campaigns.campaigns.create_campaign", return_value=12) as creator:
            screen = CampaignsScreen(page)
            screen.name_input.value = "Campanha agendada"
            screen.message_input.value = "Olá {nome}"
            screen.folder_dropdown.value = "Clientes"
            screen.send_mode_radio.value = "schedule"
            screen.start_at_input.value = "2030-01-02 10:30"
            screen.create_campaign()
        self.assertEqual(creator.call_args.kwargs["contact_ids"], [1])
        self.assertEqual(creator.call_args.kwargs["scheduled_at"], "2030-01-02T10:30:00")
        self.assertEqual(page.routes[-1], "/schedule")

    def test_critical_risk_block_prevents_runtime_start(self) -> None:
        page = FakePage()
        campaign = {"id": 1, "name": "Risco", "delivery_mode": "official_api"}
        with patch("screens.campaigns.campaigns.can_start_campaign", return_value=(True, "")), patch(
            "screens.campaigns.campaigns.get_campaign", return_value=campaign
        ), patch("screens.campaigns.whatsapp.load_config", return_value=config()), patch(
            "screens.campaigns.compliance.refresh_campaign_risk", return_value={"score": 80, "notes": ["Lista fria"]}
        ), patch("screens.campaigns.database.get_setting", return_value="1"), patch(
            "screens.campaigns.app_runtime.start_campaign"
        ) as starter:
            result = request_campaign_start(page, 1)
        self.assertFalse(result)
        starter.assert_not_called()
        self.assertEqual(page.dialogs[-1].title.value, "Envio bloqueado por risco crítico")

    def test_real_web_requires_dialog_confirmation(self) -> None:
        page = FakePage()
        campaign = {
            "id": 2,
            "name": "Web real",
            "delivery_mode": whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
            "delay_min_seconds": 60,
            "delay_max_seconds": 120,
        }
        with patch("screens.campaigns.campaigns.can_start_campaign", return_value=(True, "")), patch(
            "screens.campaigns.campaigns.get_campaign", return_value=campaign
        ), patch("screens.campaigns.campaigns.get_campaign_contacts", return_value=[{"id": 1}]), patch(
            "screens.campaigns.whatsapp.load_config",
            return_value=config(dry_run=False, mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL),
        ), patch("screens.campaigns.network.has_internet", return_value=True), patch(
            "screens.campaigns.compliance.refresh_campaign_risk", return_value={"score": 10, "notes": []}
        ), patch("screens.campaigns.app_runtime.start_campaign", return_value=True) as starter:
            request_campaign_start(page, 2)
            dialog = page.dialogs[-1]
            self.assertEqual(dialog.title.value, "Confirmar WhatsApp Web Experimental")
            dialog.actions[-1].on_click(None)
        self.assertTrue(starter.call_args.kwargs["explicit_user_confirmation"])

    def test_schedule_clones_campaign_for_resend(self) -> None:
        page = FakePage()
        item = {
            "id": 1,
            "name": "Original",
            "status": campaigns.CAMPAIGN_STATUS_DONE,
            "delivery_mode": "official_api",
            "total_contacts": 1,
        }
        clone = {**item, "id": 2, "name": "Original - Reenvio", "status": campaigns.CAMPAIGN_STATUS_DRAFT}
        with patch("screens.schedule.campaigns.list_campaigns", side_effect=[[item], [item, clone]]), patch(
            "screens.schedule.compliance.refresh_campaign_risk", return_value={"score": 0}
        ), patch("screens.schedule.campaigns.get_due_campaigns", return_value=[]), patch(
            "screens.schedule.whatsapp.get_whatsapp_web_status", return_value={"label": "Desconectado"}
        ), patch("screens.schedule.campaigns.duplicate_campaign_for_resend", return_value=2) as duplicate, patch(
            "screens.schedule.campaigns.get_campaign", return_value=clone
        ):
            screen = ScheduleScreen(page)
            screen.select_campaign(1, update_page=False)
            screen.resend_campaign()
        duplicate.assert_called_once_with(1)
        self.assertEqual(screen.selected_campaign_id, 2)

    def test_warmup_saves_ready_flag_and_confirms_real_web(self) -> None:
        page = FakePage()
        number = {
            "id": 4,
            "display_name": "Número",
            "phone": "5511999999999",
            "provider": whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
        }
        empty_stats = {"total": 0, "active": 0, "ready": 0, "paused": 0}
        with patch("screens.health.contacts.list_groups", return_value=["Clientes"]), patch(
            "screens.health.warmup.add_number", return_value=4
        ) as add_number, patch("screens.health.warmup.dashboard_stats", return_value=empty_stats), patch(
            "screens.health.warmup.list_numbers", return_value=[]
        ), patch("screens.health.warmup.list_recent_runs", return_value=[]), patch(
            "screens.health.warmup.list_recent_events", return_value=[]
        ), patch("screens.health.app_runtime.warmup_is_running", return_value=False), patch(
            "screens.health.warmup.get_number", return_value=number
        ), patch(
            "screens.health.whatsapp.load_config",
            return_value=config(dry_run=False, mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL),
        ), patch("screens.health.app_runtime.start_warmup", return_value=True) as starter:
            screen = HealthScreen(page)
            screen.f_name.value = "Número"
            screen.f_phone.value = "11999999999"
            screen.f_provider.value = whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL
            screen.f_group.value = "Clientes"
            screen.f_ready.value = True
            screen.save_number()
            self.assertTrue(add_number.call_args.kwargs["ready_for_campaigns"])
            screen.selected_number_id = 4
            screen.f_group.value = "Clientes"
            screen.start_warmup()
            dialog = page.dialogs[-1]
            dialog.content.controls[2].value = True
            dialog.actions[-1].on_click(None)
        self.assertTrue(starter.call_args.kwargs["explicit_user_confirmation"])


if __name__ == "__main__":
    unittest.main()
