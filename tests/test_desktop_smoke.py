from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


APP_MODULES = (
    "database",
    "contacts",
    "contact_service",
    "campaigns",
    "whatsapp",
    "compliance",
)


class DesktopSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_root = Path(tempfile.mkdtemp(prefix="mezzold-desktop-smoke-"))
        cls.data_dir = cls.temp_root / "data"
        cls.db_path = cls.data_dir / "mezzold_connect_test.sqlite3"
        os.environ["MEZZOLD_DATA_DIR"] = str(cls.data_dir)
        os.environ["MEZZOLD_DB_PATH"] = str(cls.db_path)
        os.environ.pop("MEZZOLD_WHATSAPP_TOKEN", None)

        for module_name in APP_MODULES:
            sys.modules.pop(module_name, None)

        cls.database = importlib.import_module("database")
        cls.contacts = importlib.import_module("contact_service")
        cls.campaigns = importlib.import_module("campaigns")
        cls.whatsapp = importlib.import_module("whatsapp")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_root, ignore_errors=True)

    def setUp(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        self.database.initialize_database()

    def test_database_initialization_and_settings_roundtrip(self) -> None:
        self.assertTrue(self.db_path.exists())
        self.assertEqual(str(self.database.DB_PATH), str(self.db_path))

        self.assertEqual(self.database.get_setting("company_name"), "Mezzold")
        self.database.set_setting("company_name", "Smoke Test")
        self.assertEqual(self.database.get_setting("company_name"), "Smoke Test")
        self.database.set_setting("app_theme", "dark")
        self.database.set_setting("ui_density", "compact")
        self.database.set_setting("app_update_channel", "beta")
        self.assertEqual(self.database.get_setting("app_theme"), "dark")
        self.assertEqual(self.database.get_setting("ui_density"), "compact")
        self.assertEqual(self.database.get_setting("app_update_channel"), "beta")
        self.assertEqual(self.database.get_setting("app_current_version"), self.database.APP_VERSION)

    def test_settings_screen_presets_preserve_custom_values(self) -> None:
        settings = importlib.import_module("screens.settings")

        self.assertEqual(settings._options_with_current(("50", "100"), "250"), ("50", "100", "250"))
        self.assertEqual(settings._options_with_current(("50", "100"), "100"), ("50", "100"))
        self.assertEqual(settings._delay_preset_for_values("60", "120"), "Seguro")
        self.assertEqual(settings._delay_preset_for_values("17", "31"), settings.CUSTOM_DELAY_PRESET)

    def test_import_contacts_from_csv_txt_xlsx_and_list_by_folder(self) -> None:
        manual_folder_id = self.contacts.create_folder("Leads Manuais")
        self.assertGreater(manual_folder_id, 0)

        csv_path = self.temp_root / "contacts.csv"
        csv_path.write_text(
            "nome,telefone,email,opt_in\n"
            "Ana CSV,+551199990001,ana@example.com,sim\n",
            encoding="utf-8",
        )
        txt_path = self.temp_root / "contacts.txt"
        txt_path.write_text(
            "nome;telefone;email;opt_in\n"
            "Bia TXT;+551199990002;bia@example.com;sim\n",
            encoding="utf-8",
        )
        xlsx_path = self.temp_root / "contacts.xlsx"
        self._write_xlsx(
            xlsx_path,
            [
                ["nome", "telefone", "email", "opt_in"],
                ["Caio XLSX", "+551199990003", "caio@example.com", "sim"],
            ],
        )

        csv_summary = self.contacts.import_contacts(str(csv_path), folder_name="Leads CSV")
        txt_summary = self.contacts.import_contacts(str(txt_path), folder_name="Leads TXT")
        xlsx_summary = self.contacts.import_contacts(str(xlsx_path), folder_name="Leads XLSX")

        self.assertEqual(csv_summary.imported, 1)
        self.assertEqual(txt_summary.imported, 1)
        self.assertEqual(xlsx_summary.imported, 1)
        self.assertEqual(len(self.contacts.list_contacts_by_folder("Leads CSV")), 1)
        self.assertEqual(len(self.contacts.list_contacts_by_folder("Leads TXT")), 1)
        self.assertEqual(len(self.contacts.list_contacts_by_folder("Leads XLSX")), 1)

        folder_names = {str(folder["name"]) for folder in self.contacts.list_folders()}
        self.assertIn("Leads Manuais", folder_names)
        self.assertIn("Leads CSV", folder_names)

    def test_campaign_creation_schedule_delay_folder_and_dry_run_send(self) -> None:
        self.whatsapp.save_config(
            self.whatsapp.WhatsAppConfig(
                delivery_mode="official_api",
                dry_run=True,
                send_interval_seconds=0.5,
                daily_send_limit=10,
            )
        )
        contact_id = self.contacts.create_contact(
            "Cliente Campanha",
            "+551199990010",
            group_name="Campanha Smoke",
            opt_in=1,
        )

        scheduled_at = self.database.now_text()
        campaign_id = self.campaigns.create_campaign(
            name="Campanha Smoke",
            message="Ola, teste de smoke.",
            contact_ids=[contact_id],
            scheduled_at=scheduled_at,
            folder_name="Campanha Smoke",
            delay_min_seconds=1,
            delay_max_seconds=2,
        )

        campaign = self.campaigns.get_campaign(campaign_id)
        self.assertIsNotNone(campaign)
        self.assertEqual(campaign["status"], self.campaigns.CAMPAIGN_STATUS_SCHEDULED)
        self.assertEqual(campaign["folder_name"], "Campanha Smoke")
        self.assertEqual(campaign["delay_min_seconds"], 1)
        self.assertEqual(campaign["delay_max_seconds"], 2)
        self.assertEqual(len(self.campaigns.get_campaign_contacts(campaign_id)), 1)
        self.assertTrue(any(item["id"] == campaign_id for item in self.campaigns.get_due_campaigns()))

        totals = self.campaigns.send_campaign(campaign_id, runner="desktop_smoke")
        self.assertEqual(totals["simulado"], 1)

        sent_campaign = self.campaigns.get_campaign(campaign_id)
        self.assertEqual(sent_campaign["status"], self.campaigns.CAMPAIGN_STATUS_DONE)
        logs = self.campaigns.list_campaign_logs(campaign_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], "simulado")
        self.assertTrue(str(logs[0]["provider_message_id"]).startswith("dryrun-"))
        self.assertEqual(logs[0]["delivery_mode"], "official_api")

    def test_whatsapp_web_dry_run_never_opens_provider_and_logs_mode(self) -> None:
        self.database.set_setting("block_high_risk_campaigns", "0")
        self.whatsapp.save_config(
            self.whatsapp.WhatsAppConfig(
                delivery_mode=self.whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=True,
                send_interval_seconds=0.5,
                daily_send_limit=10,
            )
        )
        contact_id = self.contacts.create_contact(
            "Cliente Web Teste",
            "+551199990020",
            group_name="Web Teste",
            opt_in=1,
        )
        campaign_id = self.campaigns.create_campaign(
            name="Web Experimental Dry Run",
            message="Ola, teste web.",
            contact_ids=[contact_id],
            folder_name="Web Teste",
            delay_min_seconds=10,
            delay_max_seconds=12,
        )

        original_provider = self.whatsapp.get_whatsapp_web_provider

        def fail_provider(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("Dry-run nao deve abrir provider WhatsApp Web.")

        self.whatsapp.get_whatsapp_web_provider = fail_provider
        try:
            totals = self.campaigns.send_campaign(campaign_id, runner="desktop_web_dryrun")
        finally:
            self.whatsapp.get_whatsapp_web_provider = original_provider

        self.assertEqual(totals["simulado"], 1)
        logs = self.campaigns.list_campaign_logs(campaign_id)
        self.assertEqual(logs[0]["status"], "simulado")
        self.assertEqual(logs[0]["delivery_mode"], self.whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL)

    def test_whatsapp_web_real_send_requires_explicit_confirmation(self) -> None:
        self.database.set_setting("block_high_risk_campaigns", "0")
        self.whatsapp.save_config(
            self.whatsapp.WhatsAppConfig(
                delivery_mode=self.whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=False,
                send_interval_seconds=30,
                daily_send_limit=10,
            )
        )
        contact_id = self.contacts.create_contact(
            "Cliente Web Real",
            "+551199990021",
            group_name="Web Real",
            opt_in=1,
        )
        campaign_id = self.campaigns.create_campaign(
            name="Web Sem Confirmacao",
            message="Ola, teste confirmacao.",
            contact_ids=[contact_id],
            folder_name="Web Real",
            delay_min_seconds=30,
            delay_max_seconds=45,
        )

        with self.assertRaises(self.campaigns.CampaignError):
            self.campaigns.send_campaign(campaign_id, runner="desktop_web_real")

    def test_campaign_blocks_blacklist_and_missing_opt_in_before_send(self) -> None:
        self.database.set_setting("block_high_risk_campaigns", "0")
        self.whatsapp.save_config(
            self.whatsapp.WhatsAppConfig(
                delivery_mode="official_api",
                dry_run=True,
                send_interval_seconds=0.5,
                daily_send_limit=10,
            )
        )
        no_opt_in_id = self.contacts.create_contact(
            "Sem Opt In",
            "+551199990030",
            group_name="Bloqueios",
            opt_in=0,
        )
        blacklisted_id = self.contacts.create_contact(
            "Bloqueado",
            "+551199990031",
            group_name="Bloqueios",
            opt_in=1,
            blacklisted=True,
        )
        campaign_id = self.campaigns.create_campaign(
            name="Bloqueios",
            message="Ola.",
            contact_ids=[no_opt_in_id, blacklisted_id],
            folder_name="Bloqueios",
            delay_min_seconds=1,
            delay_max_seconds=2,
        )

        totals = self.campaigns.send_campaign(campaign_id, runner="desktop_blocks")

        self.assertEqual(totals["sem_autorizacao"], 1)
        self.assertEqual(totals["bloqueado"], 1)
        self.assertEqual(totals["simulado"], 0)
        statuses = {log["status"] for log in self.campaigns.list_campaign_logs(campaign_id)}
        self.assertEqual(statuses, {"sem_autorizacao", "bloqueado"})

    def test_campaign_without_mode_defaults_to_official_api(self) -> None:
        contact_id = self.contacts.create_contact(
            "Cliente Padrao",
            "+551199990040",
            group_name="Padrao",
            opt_in=1,
        )
        campaign_id = self.campaigns.create_campaign(
            name="Campanha Padrao",
            message="Ola.",
            contact_ids=[contact_id],
            folder_name="Padrao",
        )

        campaign = self.campaigns.get_campaign(campaign_id)
        self.assertEqual(campaign["delivery_mode"], "official_api")

    def test_whatsapp_settings_do_not_store_plain_token(self) -> None:
        secret = "smoke-token-value"
        config = self.whatsapp.WhatsAppConfig(
            api_version="v24.0",
            phone_number_id="12345",
            business_account_id="67890",
            webhook_url="https://example.com/webhook",
            default_template="hello_world",
            default_language="pt_BR",
            delivery_mode="official_api",
            dry_run=True,
            send_interval_seconds=0.5,
            daily_send_limit=25,
        )

        if os.name == "nt":
            self.whatsapp.save_config(config, token_to_save=secret)
            stored_token = self.database.get_setting("whatsapp_token_protected")
            self.assertNotEqual(stored_token, secret)
            self.assertTrue(stored_token.startswith("dpapi:"))
            self.assertEqual(self.whatsapp.load_config().token, secret)
        else:
            self.whatsapp.save_config(config)
            self.assertEqual(self.database.get_setting("whatsapp_token_protected"), "")

        loaded = self.whatsapp.load_config()
        self.assertEqual(loaded.phone_number_id, "12345")
        self.assertTrue(loaded.dry_run)
        self.assertEqual(loaded.daily_send_limit, 25)

    def _write_xlsx(self, path: Path, rows: list[list[str]]) -> None:
        def cell_ref(row_index: int, column_index: int) -> str:
            return f"{chr(ord('A') + column_index)}{row_index}"

        row_xml: list[str] = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row):
                cells.append(
                    f'<c r="{cell_ref(row_index, column_index)}" t="inlineStr">'
                    f"<is><t>{value}</t></is></c>"
                )
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml)}</sheetData>'
            "</worksheet>"
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


if __name__ == "__main__":
    unittest.main()
