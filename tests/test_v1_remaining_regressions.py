from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import app_update
import campaigns
import contact_service
import contacts
import database
import runtime
import tray_icon
import warmup
import whatsapp
from screens.history import HistoryScreen
from screens.settings import SettingsScreen


class _AsyncFilePicker:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def save_file(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "historico-disparos.csv"


class _FakePage:
    web = False

    def __init__(self) -> None:
        self.services: list[object] = []
        self.dialogs: list[object] = []
        self.routes: list[str] = []
        self.update_count = 0
        self.window = SimpleNamespace(
            visible=True,
            skip_task_bar=False,
            minimized=True,
            focused=False,
            destroy=mock.Mock(),
        )

    def update(self) -> None:
        self.update_count += 1

    def show_dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> object | None:
        return self.dialogs.pop() if self.dialogs else None

    def go(self, route: str) -> None:
        self.routes.append(route)

    def run_thread(self, handler: object, *args: object, **kwargs: object) -> None:
        handler(*args, **kwargs)  # type: ignore[operator]

    def run_task(self, handler: object, *args: object, **kwargs: object) -> None:
        handler(*args, **kwargs)  # type: ignore[operator]


class RemainingV1Regressions(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="mezzold-v1-remaining-")
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

        self._environment = mock.patch.dict(
            os.environ,
            {
                "MEZZOLD_DATA_DIR": str(self.root),
                "MEZZOLD_DB_PATH": str(self.root / "mezzold_connect.sqlite3"),
                "MEZZOLD_LEGACY_DATA_DIR": str(self.root / "missing-legacy"),
            },
            clear=False,
        )
        self._environment.start()
        self.addCleanup(self._environment.stop)

        for module, attribute, value in (
            (database, "DATA_DIR", self.root),
            (database, "DB_PATH", self.root / "mezzold_connect.sqlite3"),
        ):
            previous = getattr(module, attribute)
            setattr(module, attribute, value)
            self.addCleanup(setattr, module, attribute, previous)

        database.initialize_database()

    def _contact(self, name: str, phone: str, folder: str = "Importados") -> int:
        return contact_service.create_contact(
            name=name,
            phone=phone,
            email=f"{name.lower()}@example.test",
            group_name=folder,
            opt_in=1,
            opt_in_source="teste_v1",
        )

    def test_contact_edit_delete_and_folder_lifecycle_preserve_the_contact(self) -> None:
        folder_id = contact_service.create_folder("Prospects")
        contact_id = self._contact("Ana", "11999990001", "Prospects")

        contact_service.update_contact(
            contact_id,
            name="Ana Atualizada",
            phone="(11) 98888-7001",
            email="ana.atualizada@example.test",
            notes="registro editado",
        )
        edited = contact_service.get_contact(contact_id)
        self.assertIsNotNone(edited)
        self.assertEqual(edited["name"], "Ana Atualizada")
        self.assertEqual(edited["phone"], "5511988887001")
        self.assertEqual(edited["email"], "ana.atualizada@example.test")
        self.assertEqual(edited["notes"], "registro editado")

        contact_service.rename_folder(folder_id, "Clientes VIP")
        renamed = contact_service.get_contact(contact_id)
        self.assertEqual(renamed["group_name"], "Clientes VIP")
        self.assertEqual(
            [item["id"] for item in contact_service.list_contacts_by_folder("Clientes VIP")],
            [contact_id],
        )

        self.assertEqual(contact_service.delete_folder(folder_id), 1)
        preserved = contact_service.get_contact(contact_id)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved["group_name"], database.DEFAULT_CONTACT_FOLDER)
        self.assertIn(
            contact_id,
            [item["id"] for item in contact_service.list_contacts_by_folder(database.DEFAULT_CONTACT_FOLDER)],
        )

        contact_service.delete_contact(contact_id)
        self.assertIsNone(contact_service.get_contact(contact_id))

    def test_history_screen_exports_utf8_bom_csv_with_v1_labels(self) -> None:
        contact_id = self._contact("Joao", "11999990002")
        campaigns.log_message(
            None,
            contact_id,
            "5511999990002",
            "Joao",
            "simulado",
            action_url="https://wa.me/5511999990002",
            delivery_mode=whatsapp.DELIVERY_MODE_OFFICIAL_API,
        )
        page = _FakePage()
        with mock.patch("screens.common.auth.get_current_user", return_value="tester"), mock.patch(
            "screens.common.auth.get_current_role", return_value="admin"
        ), mock.patch("screens.history.auth.get_current_user", return_value="tester"), mock.patch(
            "screens.history.auth.get_current_role", return_value="admin"
        ), mock.patch("screens.common.show_snack") as snack:
            screen = HistoryScreen(page)
            picker = _AsyncFilePicker()
            screen.file_picker = picker  # type: ignore[assignment]
            screen.logs_data = campaigns.list_logs()
            asyncio.run(screen.export_history())

        self.assertEqual(len(picker.calls), 1)
        payload = picker.calls[0]
        self.assertEqual(payload["file_name"], "historico-disparos.csv")
        raw = payload["src_bytes"]
        self.assertIsInstance(raw, bytes)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertIn("Data/hora;Campanha;Contato;Telefone;Status;Modo;Erro;Link manual", text)
        self.assertIn(";Joao;5511999990002;Teste;API Oficial Meta;;https://wa.me/5511999990002", text)
        snack.assert_called_once_with(page, "1 registro(s) exportado(s).")

    def test_warmup_number_update_delete_and_runtime_stop_are_cooperative(self) -> None:
        number_id = warmup.add_number(
            "Linha teste",
            "11999990003",
            provider="official_api",
            daily_target=20,
            max_daily_target=100,
        )
        warmup.update_number(
            number_id,
            display_name="Linha atualizada",
            provider="manual",
            daily_target=35,
            max_daily_target=120,
            rest_start="23:00",
            rest_end="06:00",
            notes="ajustada",
        )
        updated = warmup.get_number(number_id)
        self.assertEqual(updated["display_name"], "Linha atualizada")
        self.assertEqual(updated["provider"], whatsapp.DELIVERY_MODE_MANUAL_ASSISTED)
        self.assertEqual(updated["daily_target"], 35)
        self.assertEqual(updated["max_daily_target"], 120)
        self.assertEqual(updated["rest_start"], "23:00")
        self.assertEqual(updated["notes"], "ajustada")

        manager = runtime.AppRuntime()
        event = threading.Event()
        manager._warmup_events[number_id] = event
        self.assertTrue(manager.stop_warmup(number_id))
        self.assertTrue(event.is_set())
        self.assertFalse(manager.stop_warmup(number_id + 999))

        warmup.delete_number(number_id)
        self.assertIsNone(warmup.get_number(number_id))

    def test_settings_and_license_survive_database_reinitialization(self) -> None:
        database.set_settings(
            {
                "company_name": "Mezzold QA",
                "app_theme": "dark",
                "ui_density": "compact",
                "smart_send_enabled": "1",
                "smart_daily_limit": "42",
            }
        )
        SettingsScreen._save_license("LIC-V1-OK", "Profissional", "2030-12-31")

        database.initialize_database()

        self.assertEqual(database.get_setting("company_name"), "Mezzold QA")
        self.assertEqual(database.get_setting("app_theme"), "dark")
        self.assertEqual(database.get_setting("ui_density"), "compact")
        self.assertEqual(database.get_setting("smart_send_enabled"), "1")
        self.assertEqual(database.get_setting("smart_daily_limit"), "42")
        license_data = SettingsScreen._load_license(object())
        self.assertEqual(license_data["license_key"], "LIC-V1-OK")
        self.assertEqual(license_data["plan_name"], "Profissional")
        self.assertEqual(license_data["valid_until"], "2030-12-31")
        self.assertEqual(license_data["status"], "ativa")

    def test_local_update_manifest_happy_path_selects_stable_release(self) -> None:
        manifest = self.root / "update-manifest.json"
        manifest.write_text(
            """{
              "channels": {
                "stable": {
                  "latest_version": "2.2.0",
                  "download_url": "https://example.test/MezzoldConnectSetup-v2.2.0.exe",
                  "release_notes": "Melhorias de estabilidade",
                  "sha256": "abc123"
                },
                "beta": {"latest_version": "2.3.0-beta.1"}
              }
            }""",
            encoding="utf-8",
        )

        result = app_update.check_for_updates(
            "2.1.0",
            str(manifest),
            download_url="https://example.test/releases",
            channel="stable",
        )

        self.assertEqual(result.status, "available")
        self.assertTrue(result.has_update)
        self.assertEqual(result.current_version, "2.1.0")
        self.assertEqual(result.latest_version, "2.2.0")
        self.assertEqual(result.download_url, "https://example.test/MezzoldConnectSetup-v2.2.0.exe")
        self.assertEqual(result.release_notes, "Melhorias de estabilidade")
        self.assertEqual(result.sha256, "abc123")
        self.assertEqual(result.channel, "stable")

    def test_tray_actions_delegate_and_update_native_window_state(self) -> None:
        page = _FakePage()
        manager = tray_icon.TrayIconManager(page)
        icon = SimpleNamespace(title="", stop=mock.Mock())
        manager._icon = icon

        with mock.patch("tray_icon.app_runtime.pause_all_campaigns", return_value=2) as pause, mock.patch(
            "tray_icon.app_runtime.resume_pending_campaigns", return_value=3
        ) as resume, mock.patch("tray_icon.app_log.app_minimized_to_tray"), mock.patch(
            "tray_icon.app_log.app_restored_from_tray"
        ):
            manager.minimize_to_tray()
            self.assertFalse(page.window.visible)
            self.assertTrue(page.window.skip_task_bar)
            self.assertIn("segundo plano", icon.title)

            manager.show_window()
            self.assertTrue(page.window.visible)
            self.assertFalse(page.window.skip_task_bar)
            self.assertFalse(page.window.minimized)
            self.assertTrue(page.window.focused)

            manager.pause_all()
            pause.assert_called_once_with()
            self.assertIn("2 envio(s) pausado(s)", icon.title)

            manager.resume_all()
            resume.assert_called_once_with()
            self.assertIn("3 envio(s) retomado(s)", icon.title)

            manager.show_status()
            self.assertEqual(page.routes[-1], "/schedule")

        manager.stop()
        icon.stop.assert_called_once_with()
        self.assertIsNone(manager._icon)

    def test_smart_campaign_daily_limit_pauses_without_calling_provider(self) -> None:
        contact_id = self._contact("Limite", "11999990004")
        database.set_settings(
            {
                "smart_send_enabled": "1",
                "smart_daily_limit": "1",
                "block_high_risk_campaigns": "0",
            }
        )
        campaign_id = campaigns.create_campaign(
            "Limite inteligente",
            "Mensagem A",
            [contact_id],
            message_variants=["Mensagem B", "Mensagem C"],
            delay_min_seconds=30,
            delay_max_seconds=45,
        )
        campaigns.log_message(
            None,
            None,
            "5511999999999",
            "Envio anterior",
            "enviado",
            delivery_mode=whatsapp.DELIVERY_MODE_OFFICIAL_API,
        )
        config = whatsapp.WhatsAppConfig(
            delivery_mode=whatsapp.DELIVERY_MODE_OFFICIAL_API,
            dry_run=True,
            daily_send_limit=500,
        )
        client = mock.Mock()
        progress: list[str] = []

        with mock.patch("campaigns.load_config", return_value=config), mock.patch(
            "campaigns.compliance.refresh_campaign_risk",
            return_value={"score": 0, "level": "baixo", "notes": []},
        ):
            totals = campaigns.send_campaign(
                campaign_id,
                client=client,
                progress_callback=lambda _index, _total, message: progress.append(message),
                runner="regression_test",
            )

        client.send_campaign_message.assert_not_called()
        self.assertEqual(campaigns.get_campaign(campaign_id)["status"], campaigns.CAMPAIGN_STATUS_PAUSED)
        self.assertEqual(sum(totals.values()), 0)
        self.assertEqual(progress, ["Limite diário de envio atingido."])

    def test_smart_pause_cadence_uses_configured_intervals_without_real_wait(self) -> None:
        database.set_settings(
            {
                "smart_send_enabled": "1",
                "smart_pause_every": "2",
                "smart_pause_min_seconds": "5",
                "smart_pause_max_seconds": "8",
                "smart_daily_limit": "7",
            }
        )
        campaign = {"id": 77, "delay_min_seconds": 2, "delay_max_seconds": 4}

        self.assertEqual(campaigns._smart_daily_limit(500), 7)
        with mock.patch("campaigns.random.uniform", side_effect=[3.0, 6.5]) as random_delay, mock.patch(
            "campaigns._interruptible_wait", side_effect=[False, False]
        ) as wait:
            stopped = campaigns._sleep_between_sends(2, 3, campaign, 1.0)

        self.assertFalse(stopped)
        self.assertEqual(random_delay.call_args_list, [mock.call(2, 4), mock.call(5, 8)])
        self.assertEqual(wait.call_args_list, [mock.call(3.0, 77), mock.call(6.5, 77)])

    def test_smart_session_deadline_causes_cooperative_pause(self) -> None:
        contact_id = self._contact("Sessao", "11999990005")
        database.set_settings({"smart_send_enabled": "1", "block_high_risk_campaigns": "0"})
        campaign_id = campaigns.create_campaign(
            "Janela inteligente",
            "Mensagem A",
            [contact_id],
            message_variants=["Mensagem B", "Mensagem C"],
        )
        config = whatsapp.WhatsAppConfig(dry_run=True, daily_send_limit=500)
        client = mock.Mock()
        progress: list[str] = []

        with mock.patch("campaigns.load_config", return_value=config), mock.patch(
            "campaigns.compliance.refresh_campaign_risk",
            return_value={"score": 0, "level": "baixo", "notes": []},
        ), mock.patch(
            "campaigns._smart_session_deadline",
            return_value=datetime.now() - timedelta(seconds=1),
        ), mock.patch("campaigns._sent_today_count", return_value=0):
            campaigns.send_campaign(
                campaign_id,
                client=client,
                progress_callback=lambda _index, _total, message: progress.append(message),
                runner="regression_test",
            )

        client.send_campaign_message.assert_not_called()
        self.assertEqual(campaigns.get_campaign(campaign_id)["status"], campaigns.CAMPAIGN_STATUS_PAUSED)
        self.assertEqual(progress, ["Janela máxima de envio inteligente atingida."])


if __name__ == "__main__":
    unittest.main()
