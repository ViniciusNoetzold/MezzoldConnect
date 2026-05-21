from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


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

    def test_extract_and_import_leads_from_pasted_google_maps_text(self) -> None:
        pasted = """
        Oficina do Vale
        Aberto
        (51) 99999-0001
        Rua Central, 100

        Mecanica Avenida
        Fechado
        +55 51 98888-0002
        Avenida Brasil, 200

        Mecanica Avenida
        +55 51 98888-0002
        """

        leads = self.contacts.extract_leads_from_text(pasted)

        self.assertEqual(len(leads), 2)
        self.assertEqual(leads[0]["name"], "Oficina do Vale")
        self.assertEqual(leads[0]["phone"], "5551999990001")
        self.assertEqual(leads[1]["name"], "Mecanica Avenida")
        self.assertEqual(leads[1]["phone"], "5551988880002")

        summary = self.contacts.import_leads(leads, folder_name="Leads Maps")
        self.assertEqual(summary.imported, 2)
        self.assertEqual(summary.updated, 0)
        imported = self.contacts.list_contacts_by_folder("Leads Maps")
        self.assertEqual(len(imported), 2)

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
        campaign_contacts = self.campaigns.get_campaign_contacts(campaign_id)
        self.assertEqual(len(campaign_contacts), 1)
        self.assertEqual(campaign_contacts[0]["campaign_status"], self.campaigns.CONTACT_STATUS_SIMULATED)
        listed = next(item for item in self.campaigns.list_campaigns() if int(item["id"]) == campaign_id)
        self.assertEqual(int(listed["sent_contacts"]), 0)
        self.assertEqual(int(listed["processed_contacts"]), 1)
        self.assertEqual(self.campaigns.dashboard_stats()["sent"], 0)
        logs = self.campaigns.list_campaign_logs(campaign_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], "simulado")
        self.assertTrue(str(logs[0]["provider_message_id"]).startswith("dryrun-"))
        self.assertEqual(logs[0]["delivery_mode"], "official_api")

    def test_duplicate_campaign_for_resend_keeps_content_and_increments_name(self) -> None:
        contact_a = self.contacts.create_contact(
            "Cliente A",
            "+551199990111",
            group_name="Reenvio",
            opt_in=1,
        )
        contact_b = self.contacts.create_contact(
            "Cliente B",
            "+551199990112",
            group_name="Reenvio",
            opt_in=1,
        )

        campaign_id = self.campaigns.create_campaign(
            name="Promo Maio",
            message="Ola, oferta da semana.",
            contact_ids=[contact_a, contact_b],
            folder_name="Reenvio",
            delay_min_seconds=30,
            delay_max_seconds=45,
            message_variants=["Ola, oferta da semana.", "Ola, oferta especial."],
        )

        resend_two = self.campaigns.duplicate_campaign_for_resend(campaign_id)
        resend_three = self.campaigns.duplicate_campaign_for_resend(resend_two)

        duplicated = self.campaigns.get_campaign(resend_two)
        duplicated_again = self.campaigns.get_campaign(resend_three)
        self.assertIsNotNone(duplicated)
        self.assertIsNotNone(duplicated_again)
        self.assertEqual(duplicated["name"], "Promo Maio + envio 2")
        self.assertEqual(duplicated_again["name"], "Promo Maio + envio 3")
        self.assertEqual(duplicated["status"], self.campaigns.CAMPAIGN_STATUS_DRAFT)
        self.assertEqual(duplicated["folder_name"], "Reenvio")
        self.assertEqual(duplicated["delay_min_seconds"], 30)
        self.assertEqual(duplicated["delay_max_seconds"], 45)
        self.assertEqual(len(self.campaigns.get_campaign_contacts(resend_two)), 2)
        variants = self.campaigns.get_campaign_variants(resend_two)
        self.assertGreaterEqual(len(variants), 2)
        self.assertEqual(
            self.campaigns.next_resend_campaign_name("Promo Maio"),
            "Promo Maio + envio 4",
        )

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

    def test_whatsapp_web_provider_wraps_driver_startup_failures(self) -> None:
        provider = self.whatsapp.WhatsAppWebExperimentalProvider(
            self.whatsapp.WhatsAppConfig(
                delivery_mode=self.whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=False,
            )
        )
        attempts: list[str] = []

        def fail_start(browser_name: str) -> object:
            attempts.append(browser_name)
            raise self.whatsapp.WhatsAppWebSessionError(f"falha forçada em {browser_name}")

        with mock.patch.object(provider, "_start_browser_driver", side_effect=fail_start):
            with self.assertRaises(self.whatsapp.WhatsAppWebSessionError) as ctx:
                provider._ensure_driver()

        self.assertEqual(attempts, ["chrome", "edge"])
        self.assertIn("Chrome", str(ctx.exception))
        snapshot = provider.status_snapshot(refresh=False)
        self.assertEqual(snapshot["status"], self.whatsapp.WEB_STATUS_ERROR)
        self.assertIn("Edge", snapshot["message"])

    def test_whatsapp_web_page_state_accepts_loaded_composer_as_connected(self) -> None:
        provider = self.whatsapp.WhatsAppWebExperimentalProvider()

        class FakeElement:
            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

        class FakeDriver:
            def find_elements(self, _by: object, selector: str) -> list[object]:
                if selector == "#pane-side":
                    return []
                if selector == "footer":
                    return [FakeElement()]
                if selector == "canvas":
                    return []
                if selector == "div[contenteditable='true']":
                    return []
                return []

            def find_element(self, _by: object, _selector: str) -> object:
                raise RuntimeError("body not needed")

        status, message = provider._page_state(FakeDriver())
        self.assertEqual(status, self.whatsapp.WEB_STATUS_CONNECTED)
        self.assertIn("conectado", message)

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


class RBACTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_root = Path(tempfile.mkdtemp(prefix="mezzold-rbac-"))
        cls.data_dir = cls.temp_root / "data"
        cls.db_path = cls.data_dir / "mezzold_rbac_test.sqlite3"
        os.environ["MEZZOLD_DATA_DIR"] = str(cls.data_dir)
        os.environ["MEZZOLD_DB_PATH"] = str(cls.db_path)
        for mod in ("database", "auth"):
            sys.modules.pop(mod, None)
        cls.db_mod = importlib.import_module("database")
        cls.auth_mod = importlib.import_module("auth")
        cls.ui_mod = importlib.import_module("ui")
        cls.settings_mod = importlib.import_module("screens.settings")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_root, ignore_errors=True)

    def setUp(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        self.db_mod.initialize_database()

    def test_first_user_becomes_admin_with_forced_password_change(self) -> None:
        user = self.auth_mod.create_user("superadmin", "senha1234")
        self.assertEqual(user.role, self.auth_mod.ROLE_ADMIN)
        self.assertTrue(user.must_change_password)

    def test_master_bootstrap_creates_admin_and_blocks_normal_login(self) -> None:
        user = self.auth_mod.ensure_master_admin(
            self.auth_mod.MASTER_BOOTSTRAP_USERNAME,
            self.auth_mod._MASTER_BOOTSTRAP_PASSWORD,
        )

        self.assertEqual(user.username, self.auth_mod.MASTER_BOOTSTRAP_USERNAME)
        self.assertEqual(user.role, self.auth_mod.ROLE_ADMIN)
        self.assertTrue(user.is_active)
        self.assertFalse(user.must_change_password)
        self.assertIsNone(
            self.auth_mod.authenticate(
                self.auth_mod.MASTER_BOOTSTRAP_USERNAME,
                self.auth_mod._MASTER_BOOTSTRAP_PASSWORD,
            )
        )

        with self.db_mod.connect() as conn:
            row = conn.execute(
                "SELECT username, password_hash, role, is_active FROM users WHERE username = ?",
                (self.auth_mod.MASTER_BOOTSTRAP_USERNAME,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["username"], self.auth_mod.MASTER_BOOTSTRAP_USERNAME)
        self.assertTrue(row["password_hash"])
        self.assertEqual(row["role"], self.auth_mod.ROLE_ADMIN)
        self.assertEqual(int(row["is_active"]), 1)

    def test_master_bootstrap_repairs_existing_reserved_user(self) -> None:
        self.auth_mod.create_user("admin0", "senha1234", role=self.auth_mod.ROLE_ADMIN)
        existing = self.auth_mod.create_user(
            self.auth_mod.MASTER_BOOTSTRAP_USERNAME,
            "OldPass1!",
            role=self.auth_mod.ROLE_CLIENTE,
            must_change_password=True,
            is_active=False,
        )

        user = self.auth_mod.ensure_master_admin(
            self.auth_mod.MASTER_BOOTSTRAP_USERNAME,
            self.auth_mod._MASTER_BOOTSTRAP_PASSWORD,
        )
        updated = self.auth_mod.get_user(existing.id)

        self.assertEqual(user.id, existing.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.role, self.auth_mod.ROLE_ADMIN)
        self.assertTrue(updated.is_active)
        self.assertFalse(updated.must_change_password)

    def test_master_bootstrap_rejects_wrong_user_or_password(self) -> None:
        with self.assertRaisesRegex(self.auth_mod.AuthError, "Usuário master inválido"):
            self.auth_mod.ensure_master_admin("001", self.auth_mod._MASTER_BOOTSTRAP_PASSWORD)
        with self.assertRaisesRegex(self.auth_mod.AuthError, "Senha master inválida"):
            self.auth_mod.ensure_master_admin(self.auth_mod.MASTER_BOOTSTRAP_USERNAME, "senha-errada")
        self.assertEqual(self.auth_mod.user_count(), 0)

    def test_create_user_with_explicit_role(self) -> None:
        self.auth_mod.create_user("admin0", "senha1234", role=self.auth_mod.ROLE_ADMIN)
        equipe = self.auth_mod.create_user("eq1", "senha1234", role=self.auth_mod.ROLE_EQUIPE)
        cliente = self.auth_mod.create_user("cl1", "senha1234", role=self.auth_mod.ROLE_CLIENTE)
        self.assertEqual(equipe.role, self.auth_mod.ROLE_EQUIPE)
        self.assertEqual(cliente.role, self.auth_mod.ROLE_CLIENTE)

    def test_authenticate_returns_correct_role_and_blocks_inactive(self) -> None:
        self.auth_mod.create_user("admin0", "senha1234", role=self.auth_mod.ROLE_ADMIN)
        eq = self.auth_mod.create_user("eq1", "senha1234", role=self.auth_mod.ROLE_EQUIPE)
        self.auth_mod.deactivate_user(eq.id)
        result = self.auth_mod.authenticate("eq1", "senha1234")
        self.assertIsNone(result, "Inactive user must not authenticate")
        adm = self.auth_mod.authenticate("admin0", "senha1234")
        self.assertIsNotNone(adm)
        self.assertEqual(adm.role, self.auth_mod.ROLE_ADMIN)

    def test_password_change_clears_must_change_flag(self) -> None:
        user = self.auth_mod.create_user("changer", "OldPass1!", must_change_password=True)
        self.assertTrue(user.must_change_password)
        self.auth_mod.change_password(user.id, "OldPass1!", "NewPass2!")
        updated = self.auth_mod.get_user(user.id)
        self.assertIsNotNone(updated)
        self.assertFalse(updated.must_change_password)

    def test_reset_password_sets_must_change(self) -> None:
        self.auth_mod.create_user("admin0", "senha1234", role=self.auth_mod.ROLE_ADMIN)
        user = self.auth_mod.create_user("target", "OldPass1!", must_change_password=False)
        self.auth_mod.reset_user_password(user.id, "TempPass1!")
        updated = self.auth_mod.get_user(user.id)
        self.assertIsNotNone(updated)
        self.assertTrue(updated.must_change_password)

    def test_update_role_and_list_users(self) -> None:
        u = self.auth_mod.create_user("eq1", "senha1234", role=self.auth_mod.ROLE_EQUIPE)
        self.auth_mod.update_user_role(u.id, self.auth_mod.ROLE_ADMIN)
        listing = self.auth_mod.list_users()
        match = next((item for item in listing if item["username"] == "eq1"), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["role"], self.auth_mod.ROLE_ADMIN)

    def test_sidebar_labels_for_cliente_excludes_advanced(self) -> None:
        labels = self.ui_mod.sidebar_labels_for_role(self.auth_mod.ROLE_CLIENTE)
        self.assertIn("Nova campanha", labels)
        self.assertNotIn("Aquecer números", labels)
        self.assertNotIn("Gerenciar usuários", labels)

    def test_sidebar_labels_for_equipe_includes_warmup(self) -> None:
        labels = self.ui_mod.sidebar_labels_for_role(self.auth_mod.ROLE_EQUIPE)
        self.assertIn("Nova campanha", labels)
        self.assertIn("Aquecer números", labels)
        self.assertNotIn("Gerenciar usuários", labels)

    def test_sidebar_labels_for_admin_includes_all(self) -> None:
        labels = self.ui_mod.sidebar_labels_for_role(self.auth_mod.ROLE_ADMIN)
        self.assertIn("Nova campanha", labels)
        self.assertIn("Aquecer números", labels)
        self.assertIn("Gerenciar usuários", labels)

    def test_settings_flags_cliente_hides_advanced(self) -> None:
        flags = self.settings_mod.settings_flags_for_role(self.auth_mod.ROLE_CLIENTE)
        self.assertFalse(flags["advanced"])
        self.assertFalse(flags["technical"])

    def test_settings_flags_equipe_shows_advanced(self) -> None:
        flags = self.settings_mod.settings_flags_for_role(self.auth_mod.ROLE_EQUIPE)
        self.assertTrue(flags["advanced"])
        self.assertTrue(flags["technical"])

    def test_settings_flags_admin_shows_advanced(self) -> None:
        flags = self.settings_mod.settings_flags_for_role(self.auth_mod.ROLE_ADMIN)
        self.assertTrue(flags["advanced"])
        self.assertTrue(flags["technical"])


if __name__ == "__main__":
    unittest.main()
