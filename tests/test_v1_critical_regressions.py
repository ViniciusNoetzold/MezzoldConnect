from __future__ import annotations

import logging
import os
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock


_IMPORT_TEMP = tempfile.TemporaryDirectory(prefix="mezzold-v1-regression-import-")
_IMPORT_ROOT = Path(_IMPORT_TEMP.name)
_IMPORT_ENVIRONMENT = mock.patch.dict(
    os.environ,
    {
        "MEZZOLD_DATA_DIR": str(_IMPORT_ROOT),
        "MEZZOLD_DB_PATH": str(_IMPORT_ROOT / "mezzold_connect.sqlite3"),
        "MEZZOLD_LEGACY_DATA_DIR": str(_IMPORT_ROOT / "missing-legacy"),
    },
    clear=False,
)
_IMPORT_ENVIRONMENT.start()

import auth
import campaigns
import compliance
import contact_service
import contacts
import database
import warmup
import whatsapp
from screens import common
from screens.settings import settings_flags_for_role


MASTER_TEST_PASSWORD = "TestMasterPass1!"


def tearDownModule() -> None:
    auth.clear_session()
    whatsapp._WEB_PROVIDER = None
    for logger_name in ("campaigns", "background_worker"):
        logger = logging.getLogger(logger_name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
    _IMPORT_ENVIRONMENT.stop()
    _IMPORT_TEMP.cleanup()


class TemporaryDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="mezzold-v1-regression-")
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

        self._environment = mock.patch.dict(
            os.environ,
            {
                "MEZZOLD_DATA_DIR": str(self.root),
                "MEZZOLD_DB_PATH": str(self.root / "mezzold_connect.sqlite3"),
                "MEZZOLD_LEGACY_DATA_DIR": str(self.root / "missing-legacy"),
                "MEZZOLD_WHATSAPP_TOKEN": "",
            },
            clear=False,
        )
        self._environment.start()
        self.addCleanup(self._environment.stop)

        module_values = (
            (database, "DATA_DIR", self.root),
            (database, "DB_PATH", self.root / "mezzold_connect.sqlite3"),
            (whatsapp, "DATA_DIR", self.root),
            (whatsapp, "WEB_PROFILE_DIR", self.root / "whatsapp_web_profile"),
            (whatsapp, "WEB_LOG_PATH", self.root / "whatsapp_web.log"),
        )
        for module, attribute, value in module_values:
            previous = getattr(module, attribute)
            setattr(module, attribute, value)
            self.addCleanup(setattr, module, attribute, previous)

        previous_provider = whatsapp._WEB_PROVIDER
        whatsapp._WEB_PROVIDER = None
        self.addCleanup(setattr, whatsapp, "_WEB_PROVIDER", previous_provider)
        self.addCleanup(auth.clear_session)

        database.initialize_database()
        auth.clear_session()

    @staticmethod
    def _write_xlsx(path: Path, rows: list[list[str]]) -> None:
        def cell_ref(row_index: int, column_index: int) -> str:
            value = column_index + 1
            letters = ""
            while value:
                value, remainder = divmod(value - 1, 26)
                letters = chr(ord("A") + remainder) + letters
            return f"{letters}{row_index}"

        row_xml: list[str] = []
        for row_index, row in enumerate(rows, start=1):
            cells = [
                f'<c r="{cell_ref(row_index, column_index)}" t="inlineStr">'
                f"<is><t>{value}</t></is></c>"
                for column_index, value in enumerate(row)
            ]
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml)}</sheetData>'
            "</worksheet>"
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


class ContactImportExportRegressions(TemporaryDatabaseTestCase):
    def test_imports_csv_txt_and_xlsx_into_the_selected_folders(self) -> None:
        csv_path = self.root / "contacts.csv"
        csv_path.write_text(
            "nome,telefone,email,opt_in\n"
            "Ana CSV,+551199990001,ana@example.com,sim\n",
            encoding="utf-8",
        )
        txt_path = self.root / "contacts.txt"
        txt_path.write_text(
            "nome;telefone;email;opt_in\n"
            "Bia TXT;+551199990002;bia@example.com;sim\n",
            encoding="utf-8",
        )
        xlsx_path = self.root / "contacts.xlsx"
        self._write_xlsx(
            xlsx_path,
            [
                ["nome", "telefone", "email", "opt_in"],
                ["Caio XLSX", "+551199990003", "caio@example.com", "sim"],
            ],
        )

        csv_summary = contact_service.import_contacts(str(csv_path), folder_name="Leads CSV")
        txt_summary = contact_service.import_contacts(str(txt_path), folder_name="Leads TXT")
        xlsx_summary = contact_service.import_contacts(str(xlsx_path), folder_name="Leads XLSX")

        self.assertEqual((csv_summary.imported, txt_summary.imported, xlsx_summary.imported), (1, 1, 1))
        self.assertEqual([item["name"] for item in contacts.list_contacts_by_folder("Leads CSV")], ["Ana CSV"])
        self.assertEqual([item["name"] for item in contacts.list_contacts_by_folder("Leads TXT")], ["Bia TXT"])
        self.assertEqual([item["name"] for item in contacts.list_contacts_by_folder("Leads XLSX")], ["Caio XLSX"])

    def test_export_contacts_uses_utf8_bom_and_respects_folder_and_search(self) -> None:
        contact_service.create_contact(
            "Cliente Árvore",
            "+551199990004",
            email="arvore@example.com",
            group_name="Exportação",
            opt_in=1,
            notes="Observação interna",
        )
        contact_service.create_contact(
            "Cliente Ignorado",
            "+551199990005",
            group_name="Outra Pasta",
            opt_in=1,
        )
        destination = self.root / "contatos-exportados.csv"

        total = contact_service.export_contacts_csv(
            str(destination),
            group_name="Exportação",
            search="Árvore",
        )

        self.assertEqual(total, 1)
        raw = destination.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = destination.read_text(encoding="utf-8-sig")
        self.assertIn("nome;telefone;pasta/grupo;status;observacoes;criado_em;atualizado_em", text)
        self.assertIn("Cliente Árvore", text)
        self.assertIn("Observação interna", text)
        self.assertNotIn("Cliente Ignorado", text)


class CampaignAndProviderRegressions(TemporaryDatabaseTestCase):
    def _contact(self, name: str, phone: str, *, opt_in: int = 1, blacklisted: bool = False) -> int:
        return contact_service.create_contact(
            name,
            phone,
            group_name="Regressão",
            opt_in=opt_in,
            blacklisted=blacklisted,
        )

    def test_runtime_blocks_blacklist_and_missing_opt_in_before_calling_provider(self) -> None:
        database.set_setting("block_high_risk_campaigns", "0")
        whatsapp.save_config(
            whatsapp.WhatsAppConfig(
                delivery_mode=whatsapp.DELIVERY_MODE_OFFICIAL_API,
                dry_run=True,
                send_interval_seconds=0.5,
                daily_send_limit=10,
            )
        )
        no_opt_in = self._contact("Sem Opt-in", "+551199990030", opt_in=0)
        blacklisted = self._contact("Blacklist", "+551199990031", blacklisted=True)
        campaign_id = campaigns.create_campaign(
            "Bloqueios",
            "Olá.",
            [no_opt_in, blacklisted],
            folder_name="Regressão",
            delay_min_seconds=10,
            delay_max_seconds=20,
        )
        provider = mock.Mock()

        totals = campaigns.send_campaign(campaign_id, client=provider, runner="v1_regression")

        provider.send_campaign_message.assert_not_called()
        self.assertEqual(totals["sem_autorizacao"], 1)
        self.assertEqual(totals["bloqueado"], 1)
        self.assertEqual(totals["simulado"], 0)
        self.assertEqual(
            {item["status"] for item in campaigns.list_campaign_logs(campaign_id)},
            {"sem_autorizacao", "bloqueado"},
        )

    def test_whatsapp_web_dry_run_never_constructs_the_web_provider(self) -> None:
        database.set_setting("block_high_risk_campaigns", "0")
        whatsapp.save_config(
            whatsapp.WhatsAppConfig(
                delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=True,
                send_interval_seconds=10,
                daily_send_limit=10,
            )
        )
        contact_id = self._contact("Cliente Web", "+551199990020")
        campaign_id = campaigns.create_campaign(
            "Web Dry-run",
            "Olá, teste web.",
            [contact_id],
            folder_name="Regressão",
            delay_min_seconds=10,
            delay_max_seconds=12,
            delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
        )

        with mock.patch.object(
            whatsapp,
            "get_whatsapp_web_provider",
            side_effect=AssertionError("dry-run não pode abrir o provider Web"),
        ):
            totals = campaigns.send_campaign(campaign_id, runner="v1_web_dryrun")

        self.assertEqual(totals["simulado"], 1)
        log = campaigns.list_campaign_logs(campaign_id)[0]
        self.assertEqual(log["status"], "simulado")
        self.assertEqual(log["delivery_mode"], whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL)

    def test_campaign_without_explicit_mode_defaults_to_official_api(self) -> None:
        contact_id = self._contact("Cliente Padrão", "+551199990040")
        campaign_id = campaigns.create_campaign(
            "Campanha Padrão",
            "Olá.",
            [contact_id],
            folder_name="Regressão",
        )
        self.assertEqual(
            campaigns.get_campaign(campaign_id)["delivery_mode"],
            whatsapp.DELIVERY_MODE_OFFICIAL_API,
        )

    def test_selenium_imports_driver_fallback_and_connected_page_state(self) -> None:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        self.assertIsNotNone(ChromeOptions)
        self.assertIsNotNone(ChromeService)
        self.assertEqual(By.CSS_SELECTOR, "css selector")
        self.assertIsNotNone(WebDriverWait)

        provider = whatsapp.WhatsAppWebExperimentalProvider(
            whatsapp.WhatsAppConfig(
                delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=False,
            )
        )
        attempts: list[str] = []

        def fail_start(browser_name: str) -> object:
            attempts.append(browser_name)
            raise whatsapp.WhatsAppWebSessionError(f"falha forçada em {browser_name}")

        with mock.patch.object(provider, "_start_browser_driver", side_effect=fail_start):
            with self.assertRaises(whatsapp.WhatsAppWebSessionError) as caught:
                provider._ensure_driver()
        self.assertEqual(attempts, ["chrome", "edge"])
        self.assertIn("Chrome", str(caught.exception))
        self.assertIn("Edge", provider.status_snapshot(refresh=False)["message"])

        class FakeElement:
            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

        class FakeDriver:
            def find_elements(self, _by: object, selector: str) -> list[object]:
                return [FakeElement()] if selector == "footer" else []

            def find_element(self, _by: object, _selector: str) -> object:
                raise RuntimeError("body não é necessário")

        status, message = provider._page_state(FakeDriver())
        self.assertEqual(status, whatsapp.WEB_STATUS_CONNECTED)
        self.assertIn("conectado", message.lower())

    def test_build_contract_packages_selenium_and_both_browser_fallbacks(self) -> None:
        root = Path(__file__).resolve().parents[1]
        build_text = (root / "build.ps1").read_text(encoding="utf-8")
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("selenium==", requirements)
        self.assertIn('"--hidden-import", "selenium"', build_text)
        self.assertIn('"selenium.webdriver.chrome"', build_text)
        self.assertIn('"selenium.webdriver.edge"', build_text)

    @unittest.skipUnless(os.name == "nt", "DPAPI só está disponível no Windows")
    def test_whatsapp_token_is_dpapi_protected_and_round_trips(self) -> None:
        secret = "token-regression-not-plain-text"
        config = whatsapp.WhatsAppConfig(
            api_version="v24.0",
            phone_number_id="12345",
            business_account_id="67890",
            webhook_url="https://example.test/webhook",
            default_template="hello_world",
            default_language="pt_BR",
            delivery_mode=whatsapp.DELIVERY_MODE_OFFICIAL_API,
            dry_run=True,
            send_interval_seconds=0.5,
            daily_send_limit=25,
        )

        whatsapp.save_config(config, token_to_save=secret)

        protected = database.get_setting("whatsapp_token_protected")
        self.assertTrue(protected.startswith("dpapi:"))
        self.assertNotEqual(protected, secret)
        self.assertNotIn(secret, protected)
        self.assertEqual(whatsapp.load_config().token, secret)


class AuthAndRbacRegressions(TemporaryDatabaseTestCase):
    def test_first_user_becomes_admin_and_must_change_password(self) -> None:
        user = auth.create_user("primeiro", "Senha123!")
        self.assertEqual(user.role, auth.ROLE_ADMIN)
        self.assertTrue(user.must_change_password)

        auth.change_password(user.id, "Senha123!", "SenhaNova123!")
        updated = auth.get_user(user.id)
        self.assertIsNotNone(updated)
        self.assertFalse(updated.must_change_password)
        self.assertIsNotNone(auth.authenticate("primeiro", "SenhaNova123!"))

    def test_master_bootstrap_repairs_reserved_user_and_enforces_protections(self) -> None:
        auth.create_user("admin-base", "Senha123!", role=auth.ROLE_ADMIN)
        with database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users
                    (username, password_hash, role, is_active, must_change_password, created_at, updated_at)
                VALUES (?, ?, ?, 0, 1, ?, ?)
                """,
                (
                    auth.MASTER_BOOTSTRAP_USERNAME,
                    auth.hash_password("SenhaAntiga123!"),
                    auth.ROLE_CLIENTE,
                    database.now_text(),
                    database.now_text(),
                ),
            )
            reserved_id = int(cursor.lastrowid)

        with mock.patch.dict(
            os.environ,
            {auth.MASTER_BOOTSTRAP_PASSWORD_ENV: MASTER_TEST_PASSWORD},
            clear=False,
        ):
            master = auth.ensure_master_admin(auth.MASTER_BOOTSTRAP_USERNAME, MASTER_TEST_PASSWORD)

        self.assertEqual(master.id, reserved_id)
        self.assertEqual(master.role, auth.ROLE_MEZZOLD_MASTER)
        self.assertTrue(master.is_active)
        self.assertFalse(master.must_change_password)
        self.assertTrue(auth.verify_user_password(master.id, MASTER_TEST_PASSWORD))
        self.assertIsNone(auth.authenticate(master.username, MASTER_TEST_PASSWORD))
        with self.assertRaisesRegex(auth.AuthError, "rebaixado"):
            auth.update_user_role(master.id, auth.ROLE_ADMIN)
        with self.assertRaisesRegex(auth.AuthError, "desativado"):
            auth.deactivate_user(master.id)
        with self.assertRaisesRegex(auth.AuthError, "bootstrap interno"):
            auth.reset_user_password(master.id, "SenhaTemp123!")

    def test_master_bootstrap_rejects_unconfigured_or_invalid_attempts_and_reserved_creation(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(auth.MASTER_BOOTSTRAP_PASSWORD_ENV, None)
            with self.assertRaisesRegex(auth.AuthError, "Credencial master"):
                auth.ensure_master_admin(auth.MASTER_BOOTSTRAP_USERNAME, MASTER_TEST_PASSWORD)

        with mock.patch.dict(
            os.environ,
            {auth.MASTER_BOOTSTRAP_PASSWORD_ENV: MASTER_TEST_PASSWORD},
            clear=False,
        ):
            with self.assertRaisesRegex(auth.AuthError, "Usuário master inválido"):
                auth.ensure_master_admin("001", MASTER_TEST_PASSWORD)
            with self.assertRaisesRegex(auth.AuthError, "Senha master inválida"):
                auth.ensure_master_admin(auth.MASTER_BOOTSTRAP_USERNAME, "senha-errada")

        with self.assertRaisesRegex(auth.AuthError, "000"):
            auth.create_user(auth.MASTER_BOOTSTRAP_USERNAME, "SenhaTemp123!", role=auth.ROLE_ADMIN)
        with self.assertRaisesRegex(auth.AuthError, "Mezzold Master"):
            auth.create_user("master-irregular", "SenhaTemp123!", role=auth.ROLE_MEZZOLD_MASTER)

    def test_inactive_password_reset_role_listing_and_rbac_matrix(self) -> None:
        admin = auth.create_user("admin", "Senha123!", role=auth.ROLE_ADMIN)
        equipe = auth.create_user("equipe", "Senha123!", role=auth.ROLE_EQUIPE)
        cliente = auth.create_user("cliente", "Senha123!", role=auth.ROLE_CLIENTE)

        auth.deactivate_user(equipe.id)
        self.assertIsNone(auth.authenticate("equipe", "Senha123!"))
        auth.activate_user(equipe.id)
        self.assertEqual(auth.authenticate("equipe", "Senha123!").role, auth.ROLE_EQUIPE)

        auth.reset_user_password(cliente.id, "SenhaTemp123!", must_change_password=True)
        self.assertTrue(auth.get_user(cliente.id).must_change_password)
        auth.update_user_role(cliente.id, auth.ROLE_EQUIPE)
        listed = {item["username"]: item for item in auth.list_users()}
        self.assertEqual(listed["cliente"]["role"], auth.ROLE_EQUIPE)
        self.assertTrue(auth.can_manage_users(admin.role))
        self.assertFalse(auth.can_manage_users(equipe.role))

        expected_health_access = {
            auth.ROLE_CLIENTE: False,
            auth.ROLE_EQUIPE: True,
            auth.ROLE_ADMIN: True,
            auth.ROLE_MEZZOLD_MASTER: True,
        }
        for role, has_health in expected_health_access.items():
            with self.subTest(role=role):
                routes = {item.route for item in common.sidebar_items_for_role(role)}
                self.assertEqual(common.ROUTE_HEALTH in routes, has_health)
                flags = settings_flags_for_role(role)
                self.assertEqual(flags["advanced"], role != auth.ROLE_CLIENTE)
                self.assertEqual(flags["technical"], role != auth.ROLE_CLIENTE)
                self.assertEqual(
                    flags["manage_users"],
                    role in {auth.ROLE_ADMIN, auth.ROLE_MEZZOLD_MASTER},
                )


class ComplianceRegressions(unittest.TestCase):
    def test_normalization_and_all_risk_boundaries_match_v1(self) -> None:
        self.assertEqual(compliance._normalize_text("Olá Mundo"), "ola mundo")
        self.assertEqual(compliance._normalize_text("Ação e Reação"), "acao e reacao")
        self.assertEqual(compliance._normalize_text("TÊxto com   vários espaços"), "texto com varios espacos")
        expected = {
            100: "crítico",
            75: "crítico",
            74: "alto",
            50: "alto",
            49: "moderado",
            25: "moderado",
            24: "baixo",
            0: "baixo",
        }
        self.assertEqual({score: compliance.risk_level(score) for score in expected}, expected)


class WarmupRegressions(TemporaryDatabaseTestCase):
    def _number(self, name: str, phone: str, **kwargs: object) -> int:
        return warmup.add_number(
            name,
            phone,
            rest_start="00:00",
            rest_end="00:00",
            **kwargs,
        )

    def _contact(self, name: str, phone: str) -> int:
        return contact_service.create_contact(
            name,
            phone,
            group_name="Aquecimento",
            opt_in=1,
            opt_in_source="teste",
        )

    def test_daily_target_starts_at_20_grows_20_percent_and_respects_cap(self) -> None:
        number_id = self._number(
            "Número quota",
            "+551199990050",
            daily_target=20,
            max_daily_target=25,
        )
        number = warmup.get_number(number_id)
        self.assertEqual(warmup.current_daily_target(number), 20)

        with database.connect() as conn:
            conn.execute(
                "UPDATE whatsapp_numbers SET created_at = ? WHERE id = ?",
                ((date.today() - timedelta(days=1)).isoformat(), number_id),
            )
        self.assertEqual(warmup.current_daily_target(warmup.get_number(number_id)), 24)

        with database.connect() as conn:
            conn.execute(
                "UPDATE whatsapp_numbers SET created_at = ? WHERE id = ?",
                ((date.today() - timedelta(days=10)).isoformat(), number_id),
            )
        self.assertEqual(warmup.current_daily_target(warmup.get_number(number_id)), 25)

    def test_rest_window_blocks_a_rampup_before_selecting_contacts(self) -> None:
        now = datetime.now().replace(second=0, microsecond=0)
        start = (now - timedelta(minutes=1)).strftime("%H:%M")
        end = (now + timedelta(minutes=1)).strftime("%H:%M")
        self.assertTrue(warmup._inside_rest_window(start, end))
        self.assertFalse(warmup._inside_rest_window("00:00", "00:00"))

        number_id = warmup.add_number(
            "Número em repouso",
            "+551199990051",
            rest_start=start,
            rest_end=end,
        )
        with self.assertRaisesRegex(warmup.WarmupError, "horário de descanso"):
            warmup.run_number_rampup(number_id, group_name="Aquecimento")

    def test_contact_used_today_is_excluded_only_for_the_same_number(self) -> None:
        first_contact = self._contact("Primeiro", "+551199990060")
        second_contact = self._contact("Segundo", "+551199990061")
        first_number = self._number("Número A", "+551199990062")
        second_number = self._number("Número B", "+551199990063")
        with database.connect() as conn:
            conn.execute(
                """
                INSERT INTO number_rampup_events
                    (whatsapp_number_id, contact_id, phone, recipient_name, status, created_at)
                VALUES (?, ?, ?, ?, 'simulado', ?)
                """,
                (
                    first_number,
                    first_contact,
                    "5511999990060",
                    "Primeiro",
                    database.now_text(),
                ),
            )

        selected_for_first = {
            int(item["id"])
            for item in warmup._select_contacts(first_number, 20, "Aquecimento")
        }
        selected_for_second = {
            int(item["id"])
            for item in warmup._select_contacts(second_number, 20, "Aquecimento")
        }
        self.assertNotIn(first_contact, selected_for_first)
        self.assertIn(second_contact, selected_for_first)
        self.assertEqual(selected_for_second, {first_contact, second_contact})

    def test_health_score_auto_pauses_failures_and_releases_a_healthy_number(self) -> None:
        failed_number = self._number("Número falhando", "+551199990070")
        healthy_number = self._number("Número saudável", "+551199990071")
        failed_contact = self._contact("Falha", "+551199990072")
        healthy_contact = self._contact("Sucesso", "+551199990073")
        with database.connect() as conn:
            for index in range(5):
                conn.execute(
                    """
                    INSERT INTO number_rampup_events
                        (whatsapp_number_id, contact_id, phone, recipient_name, status,
                         error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        failed_number,
                        failed_contact,
                        "5511999990072",
                        "Falha",
                        "falhou",
                        f"falha {index}",
                        database.now_text(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO number_rampup_events
                        (whatsapp_number_id, contact_id, phone, recipient_name, status, created_at)
                    VALUES (?, ?, ?, ?, 'simulado', ?)
                    """,
                    (
                        healthy_number,
                        healthy_contact,
                        "5511999990073",
                        "Sucesso",
                        database.now_text(),
                    ),
                )

        failed_health = warmup.refresh_number_health(failed_number)
        healthy_health = warmup.refresh_number_health(healthy_number)

        self.assertLess(failed_health["score"], warmup.AUTO_PAUSE_SCORE)
        self.assertEqual(failed_health["ready_for_campaigns"], 0)
        self.assertEqual(warmup.get_number(failed_number)["status"], "auto_paused")
        self.assertGreaterEqual(healthy_health["score"], 70)
        self.assertEqual(healthy_health["ready_for_campaigns"], 1)
        self.assertEqual(warmup.get_number(healthy_number)["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
