from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import flet as ft

import campaigns
import contacts
import database
import whatsapp
from screens.campaigns import (
    CampaignsScreen,
    campaign_primary_action,
    parse_datetime,
    parse_variants,
    request_campaign_start,
)
from screens.schedule import ScheduleScreen


_TEMP = tempfile.TemporaryDirectory(
    prefix="mezzold-v2-campaign-screen-tests-", ignore_cleanup_errors=True
)
_ROOT = Path(_TEMP.name)


class FakePage:
    web = False

    def __init__(self) -> None:
        self.dialogs: list[object] = []
        self.routes: list[str] = []
        self.urls: list[str] = []

    def update(self) -> None:
        return None

    def show_dialog(self, dialog: object) -> None:
        dialog.open = True
        self.dialogs.append(dialog)

    def pop_dialog(self) -> object | None:
        if not self.dialogs:
            return None
        dialog = self.dialogs.pop()
        dialog.open = False
        return dialog

    def go(self, route: str) -> None:
        self.routes.append(route)

    def launch_url(self, url: str) -> None:
        self.urls.append(url)


class CampaignScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        data_dir = _ROOT / self.id().replace(".", "-")
        data_dir.mkdir(parents=True, exist_ok=True)
        database.DATA_DIR = data_dir
        database.DB_PATH = data_dir / "mezzold_connect.sqlite3"
        database.initialize_database()

    def _contact(self, name: str = "Ana", phone: str = "11999999999") -> int:
        return contacts.add_contact(
            name,
            phone,
            group_name=database.DEFAULT_CONTACT_FOLDER,
            opt_in=1,
            opt_in_source="teste_interface",
        )

    def test_helpers_keep_v1_formats_and_status_actions(self) -> None:
        self.assertEqual(parse_datetime("02/01/2030 10:30"), "2030-01-02T10:30:00")
        self.assertEqual(parse_datetime("2030-01-02T10:30"), "2030-01-02T10:30:00")
        self.assertEqual(parse_variants("A\n---\nB"), ["A", "B"])
        self.assertTrue(campaign_primary_action(campaigns.CAMPAIGN_STATUS_DRAFT)["enabled"])
        paused = campaign_primary_action(campaigns.CAMPAIGN_STATUS_PAUSED)
        self.assertEqual(paused["label"], "Continuar")
        self.assertTrue(paused["allow_resume"])
        self.assertFalse(campaign_primary_action(campaigns.CAMPAIGN_STATUS_DONE)["enabled"])

    def test_create_schedule_details_history_manual_link_and_resend(self) -> None:
        self._contact()
        page = FakePage()
        create = CampaignsScreen(page)
        self.assertEqual(create.folder_dropdown.value, database.DEFAULT_CONTACT_FOLDER)
        self.assertIn(create.media_picker, create.services)

        create.name_input.value = "Lembrete"
        create.message_input.value = "Olá {nome}"
        create.message_variants.value = "Olá!\n---\nBom dia!"
        create.send_mode_radio.value = "schedule"
        create.start_at_input.value = "2030-01-02 10:30"
        create.create_campaign()

        stored = campaigns.list_campaigns()
        self.assertEqual(len(stored), 1)
        campaign_id = int(stored[0]["id"])
        self.assertEqual(stored[0]["scheduled_at"], "2030-01-02T10:30:00")
        self.assertEqual(len(campaigns.get_campaign_variants(campaign_id)), 3)
        self.assertEqual(page.routes[-1], "/schedule")

        campaigns.log_message(
            campaign_id,
            None,
            "5511999999999",
            "Ana",
            "pendente_manual",
            action_url="https://wa.me/5511999999999?text=Oi",
            delivery_mode=whatsapp.DELIVERY_MODE_MANUAL_ASSISTED,
        )
        schedule = ScheduleScreen(page)
        self.assertEqual(schedule.selected_campaign_id, campaign_id)

        schedule.show_campaign_detail()
        self.assertEqual(page.dialogs[-1].key, "schedule-detail-dialog")
        page.pop_dialog()

        schedule.show_campaign_history()
        dialog = page.dialogs[-1]
        self.assertEqual(dialog.key, "schedule-history-dialog")
        table = dialog.content.content.controls[0]
        manual_button = table.rows[0].cells[5].content
        manual_button.on_click(None)
        self.assertEqual(page.urls[-1], "https://wa.me/5511999999999?text=Oi")
        page.pop_dialog()

        schedule.resend_campaign()
        self.assertEqual(len(campaigns.list_campaigns()), 2)
        duplicate = campaigns.get_campaign(schedule.selected_campaign_id or 0)
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate["status"], campaigns.CAMPAIGN_STATUS_DRAFT)
        self.assertIn("+ envio 2", duplicate["name"])

    def test_file_picker_uses_flet_service_and_sets_desktop_path(self) -> None:
        page = FakePage()
        screen = CampaignsScreen(page)
        picked = ft.FilePickerFile(
            id=1, name="catalogo.pdf", size=100, path=r"C:\midias\catalogo.pdf"
        )
        with mock.patch.object(
            screen.media_picker, "pick_files", new=mock.AsyncMock(return_value=[picked])
        ) as picker:
            asyncio.run(screen.pick_media())
        self.assertEqual(screen.media_path_input.value, r"C:\midias\catalogo.pdf")
        picker.assert_awaited_once()
        self.assertEqual(
            picker.await_args.kwargs["file_type"], ft.FilePickerFileType.CUSTOM
        )
        self.assertFalse(picker.await_args.kwargs["allow_multiple"])

    def test_high_risk_then_real_web_requires_two_explicit_confirmations(self) -> None:
        page = FakePage()
        campaign = {
            "id": 7,
            "name": "Web real",
            "folder_name": "Clientes",
            "delivery_mode": whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
            "delay_min_seconds": 30,
            "delay_max_seconds": 45,
        }
        config = whatsapp.WhatsAppConfig(
            delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
            dry_run=False,
        )
        with (
            mock.patch("screens.campaigns.campaigns.can_start_campaign", return_value=(True, "")),
            mock.patch("screens.campaigns.campaigns.get_campaign", return_value=campaign),
            mock.patch("screens.campaigns.campaigns.get_campaign_contacts", return_value=[{}, {}]),
            mock.patch("screens.campaigns.whatsapp.load_config", return_value=config),
            mock.patch("screens.campaigns.network.has_internet", return_value=True),
            mock.patch(
                "screens.campaigns.compliance.refresh_campaign_risk",
                return_value={"score": 75, "level": "alto", "notes": ["Delay curto"]},
            ),
            mock.patch("screens.campaigns.database.get_setting", return_value="0"),
            mock.patch("screens.campaigns.app_runtime.start_campaign", return_value=True) as start,
        ):
            self.assertTrue(request_campaign_start(page, 7))
            risk_dialog = page.dialogs[-1]
            self.assertEqual(risk_dialog.key, "risk-send-confirmation")
            risk_dialog.actions[1].on_click(None)
            web_dialog = page.dialogs[-1]
            self.assertEqual(web_dialog.key, "web-send-confirmation")
            start.assert_not_called()
            web_dialog.actions[1].on_click(None)

        start.assert_called_once()
        self.assertTrue(start.call_args.kwargs["explicit_user_confirmation"])

    def test_schedule_pause_and_cancel_delegate_to_shared_runtime(self) -> None:
        contact_id = self._contact()
        campaign_id = campaigns.create_campaign("Operacional", "Oi", [contact_id])
        page = FakePage()
        screen = ScheduleScreen(page)
        screen.select_campaign(campaign_id)

        with mock.patch("screens.schedule.app_runtime.pause_campaign") as pause:
            screen.pause_selected()
        pause.assert_called_once_with(campaign_id)

        with mock.patch("screens.schedule.app_runtime.cancel_campaign") as cancel:
            screen.cancel_selected()
            dialog = page.dialogs[-1]
            self.assertEqual(dialog.key, "schedule-cancel-dialog")
            dialog.actions[1].on_click(None)
        cancel.assert_called_once_with(campaign_id)


if __name__ == "__main__":
    unittest.main()
