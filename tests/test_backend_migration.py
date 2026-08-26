from __future__ import annotations

import csv
import logging
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock


_TEMP = tempfile.TemporaryDirectory(prefix="mezzold-v2-backend-tests-")
_ROOT = Path(_TEMP.name)
os.environ["MEZZOLD_DATA_DIR"] = str(_ROOT / "bootstrap")
os.environ["MEZZOLD_DB_PATH"] = str(_ROOT / "bootstrap" / "database.sqlite3")
os.environ["MEZZOLD_LEGACY_DATA_DIR"] = str(_ROOT / "missing-legacy")

import auth
import background_worker
import campaigns
import contact_service
import contacts
import database
import warmup
import whatsapp


def tearDownModule() -> None:
    for logger_name in ("campaigns", "background_worker"):
        logger = logging.getLogger(logger_name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
    _TEMP.cleanup()


class BackendMigrationTests(unittest.TestCase):
    def _use_database(self, name: str, initialize: bool = True) -> Path:
        data_dir = _ROOT / name
        data_dir.mkdir(parents=True, exist_ok=True)
        database.DATA_DIR = data_dir
        database.DB_PATH = data_dir / "mezzold_connect.sqlite3"
        if initialize:
            database.initialize_database()
        auth.clear_session()
        return database.DB_PATH

    def _add_contact(self, name: str, phone: str, group: str = "Importados") -> int:
        return contacts.add_contact(
            name=name,
            phone=phone,
            group_name=group,
            opt_in=1,
            opt_in_source="teste",
        )

    def test_fresh_schema_is_versioned_and_backup_is_consistent(self) -> None:
        self._use_database("fresh")
        self.assertEqual(database.get_schema_version(), database.LATEST_SCHEMA_VERSION)
        self.assertEqual(database.APP_VERSION, "2.1.0")
        self.assertEqual(database.check_database_integrity(), (True, "ok"))
        report = database.get_migration_report()
        self.assertTrue(database.migration_report_path().is_file())
        self.assertTrue(report["integrity_ok"])
        self.assertEqual(report["schema_before"], 0)
        self.assertEqual(report["schema_after"], database.LATEST_SCHEMA_VERSION)
        self.assertEqual(
            [row["version"] for row in report["applied_migrations"]],
            list(range(1, database.LATEST_SCHEMA_VERSION + 1)),
        )

        backup = database.create_backup()
        self.assertTrue(backup.is_file())
        self.assertEqual(database.check_database_integrity(backup), (True, "ok"))

    def test_copy_once_legacy_database_checks_and_preserves_source(self) -> None:
        source_dir = _ROOT / "legacy-copy-source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source = source_dir / "mezzold_connect.sqlite3"
        with closing(sqlite3.connect(source)) as conn:
            conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
            conn.execute("INSERT INTO sample VALUES ('preservado')")
            conn.commit()
        source_bytes = source.read_bytes()

        target = _ROOT / "legacy-copy-target" / "mezzold_connect.sqlite3"
        copied = database.migrate_legacy_database_once(source, target)
        self.assertEqual(copied, target.resolve())
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(database.check_database_integrity(target), (True, "ok"))
        with closing(sqlite3.connect(target)) as conn:
            self.assertEqual(conn.execute("SELECT value FROM sample").fetchone()[0], "preservado")

        with closing(sqlite3.connect(source)) as conn:
            conn.execute("INSERT INTO sample VALUES ('novo')")
            conn.commit()
        self.assertIsNone(database.migrate_legacy_database_once(source, target))
        with closing(sqlite3.connect(target)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sample").fetchone()[0], 1)

    def test_recovers_reduced_installer_schema_without_dropping_legacy_rows(self) -> None:
        db_path = self._use_database("installer-recovery", initialize=False)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.executescript(
                """
                CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'cliente',
                    must_change_password INTEGER NOT NULL DEFAULT 0, is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')), last_login_at TEXT);
                CREATE TABLE contact_folders (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL,
                    email TEXT, group_name TEXT, opt_in INTEGER NOT NULL DEFAULT 1, opt_in_source TEXT,
                    opt_in_category TEXT, opt_in_at TEXT, consent_notes TEXT, notes TEXT,
                    blacklisted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, message TEXT NOT NULL,
                    message_category TEXT DEFAULT 'marketing', template_name TEXT, template_language TEXT DEFAULT 'pt_BR',
                    folder_name TEXT, media_path TEXT, scheduled_at TEXT, delay_min_seconds INTEGER DEFAULT 60,
                    delay_max_seconds INTEGER DEFAULT 120, delivery_mode TEXT DEFAULT 'official_api',
                    status TEXT NOT NULL DEFAULT 'rascunho', risk_score INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE campaign_contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL,
                    contact_id INTEGER NOT NULL, phone TEXT NOT NULL, recipient_name TEXT,
                    status TEXT NOT NULL DEFAULT 'pendente', attempts INTEGER DEFAULT 0,
                    last_error TEXT, sent_at TEXT);
                CREATE TABLE campaign_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER,
                    campaign_name TEXT, recipient_name TEXT, phone TEXT NOT NULL, status TEXT NOT NULL,
                    delivery_mode TEXT, action_url TEXT, error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE warmup_numbers (id INTEGER PRIMARY KEY AUTOINCREMENT, display_name TEXT NOT NULL,
                    phone TEXT NOT NULL UNIQUE, phone_number_id TEXT, provider TEXT DEFAULT 'oficial',
                    status TEXT DEFAULT 'testing', quality_rating TEXT DEFAULT 'unknown', health_score INTEGER DEFAULT 85,
                    messaging_limit TEXT DEFAULT '250', daily_target INTEGER DEFAULT 20, max_daily_target INTEGER DEFAULT 500,
                    current_daily_target INTEGER DEFAULT 20, sent_today INTEGER DEFAULT 0,
                    rest_start TEXT DEFAULT '00:00', rest_end TEXT DEFAULT '07:00', active INTEGER DEFAULT 1,
                    ready_for_campaigns INTEGER DEFAULT 0, notes TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE warmup_events (id INTEGER PRIMARY KEY AUTOINCREMENT, number_id INTEGER,
                    number_name TEXT, recipient_name TEXT, phone TEXT NOT NULL, status TEXT NOT NULL,
                    error_message TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO users(username,password_hash,role) VALUES('legado','hash','operator');
                INSERT INTO contact_folders(name,is_default) VALUES('Importados',1);
                INSERT INTO contacts(name,phone,group_name) VALUES('Ana','5511999999999','Importados');
                INSERT INTO campaigns(name,message) VALUES('Campanha antiga','Oi');
                INSERT INTO campaign_contacts(campaign_id,contact_id,phone,recipient_name)
                    VALUES(1,1,'5511999999999','Ana');
                INSERT INTO campaign_logs(campaign_id,campaign_name,recipient_name,phone,status,delivery_mode)
                    VALUES(1,'Campanha antiga','Ana','5511999999999','enviado','official_api');
                INSERT INTO warmup_numbers(display_name,phone,provider,ready_for_campaigns)
                    VALUES('Numero 1','5511888888888','oficial',1);
                INSERT INTO warmup_events(number_id,number_name,recipient_name,phone,status)
                    VALUES(1,'Numero 1','Ana','5511999999999','enviado');
                INSERT INTO settings(key,value) VALUES('company_name','Empresa legada');
                """
            )
            conn.commit()

        database.initialize_database()
        database.initialize_database()
        self.assertEqual(database.get_schema_version(), database.LATEST_SCHEMA_VERSION)
        self.assertEqual(database.check_database_integrity(), (True, "ok"))
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM campaign_contacts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT status FROM campaign_contacts").fetchone()[0], "aguardando")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM campaign_contacts_installer_legacy").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM message_logs").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT provider FROM whatsapp_numbers").fetchone()[0], "official_api")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM number_rampup_events").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT value FROM settings WHERE key='company_name'").fetchone()[0], "Empresa legada")
        self.assertEqual(len(list((database.DATA_DIR / "backups").glob("*.sqlite3"))), 1)

    def test_auth_keeps_full_user_in_session_and_exposes_compatibility_helpers(self) -> None:
        self._use_database("auth")
        user = auth.create_user("operador", "senha-segura", role=auth.ROLE_CLIENTE)
        authenticated = auth.authenticate("operador", "senha-segura")
        self.assertIsNotNone(authenticated)
        auth.set_current_user(authenticated)
        self.assertEqual(auth.get_current_user(), "operador")
        self.assertEqual(auth.get_current_user_id(), user.id)
        self.assertEqual(auth.get_current_user_record(), authenticated)
        self.assertTrue(auth.verify_user_password(user.id, "senha-segura"))
        auth.change_password("operador", "senha-segura", "senha-alterada")
        self.assertIsNotNone(auth.authenticate("operador", "senha-alterada"))
        auth.clear_session()
        self.assertIsNone(auth.get_current_user_record())

    def test_contact_import_overrides_and_lead_helpers(self) -> None:
        self._use_database("contacts")
        source = database.DATA_DIR / "contatos.csv"
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["nome", "telefone", "opt_in", "origem"])
            writer.writeheader()
            writer.writerow({"nome": "Ana", "telefone": "11999999999", "opt_in": "sim", "origem": "arquivo"})
        summary = contact_service.import_contacts(
            str(source),
            "Clientes",
            default_opt_in=0,
            opt_in_source="interface_v2",
            opt_in_category="utility",
            consent_notes="sem consentimento",
        )
        self.assertEqual(summary.imported, 1)
        item = contacts.list_contacts(group_name="Clientes")[0]
        self.assertEqual(item["opt_in"], 0)
        self.assertEqual(item["opt_in_source"], "interface_v2")
        self.assertEqual(item["opt_in_category"], "utility")
        self.assertEqual(item["consent_notes"], "sem consentimento")

        leads = contacts.extract_leads_from_text("Padaria Central\nTelefone (11) 98888-7777")
        self.assertEqual(leads[0]["name"], "Padaria Central")
        imported = contacts.import_leads(leads, "Leads")
        self.assertEqual(imported.imported, 1)

    def test_campaign_schedule_resume_simulation_resend_and_cooperative_cancel(self) -> None:
        self._use_database("campaigns")
        database.set_setting("block_high_risk_campaigns", "0")
        first = self._add_contact("Ana", "11999999999")
        second = self._add_contact("Bia", "11888888888")

        campaign_id = campaigns.create_campaign(
            "Teste",
            "Ola",
            [first, second],
            scheduled_at="2030-01-02 03:04",
            delay_min_seconds=30,
            delay_max_seconds=30,
        )
        self.assertEqual(campaigns.get_campaign(campaign_id)["scheduled_at"], "2030-01-02T03:04:00")
        campaigns.schedule_campaign(campaign_id, "2020-01-02 03:04")
        self.assertIn(campaign_id, {int(item["id"]) for item in campaigns.get_due_campaigns()})
        campaigns.pause_campaign(campaign_id)

        class Client:
            def send_campaign_message(self, _contact, _campaign):
                return whatsapp.SendResult(status="enviado", delivery_mode=whatsapp.DELIVERY_MODE_OFFICIAL_API)

        def cancel_after_first(index: int, _total: int, _message: str) -> None:
            if index == 1:
                campaigns.cancel_campaign(campaign_id)

        started = time.monotonic()
        totals = campaigns.send_campaign(
            campaign_id,
            client=Client(),
            progress_callback=cancel_after_first,
            allow_resume=True,
        )
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(totals["enviado"], 1)
        self.assertEqual(campaigns.get_campaign(campaign_id)["status"], campaigns.CAMPAIGN_STATUS_CANCELLED)

        simulated_id = campaigns.create_campaign("Simulada", "Oi", [first])
        simulated = campaigns.send_campaign(
            simulated_id,
            client=type(
                "DryClient",
                (),
                {"send_campaign_message": lambda self, contact, campaign: whatsapp.SendResult(status="simulado", dry_run=True)},
            )(),
        )
        self.assertEqual(simulated["simulado"], 1)
        self.assertEqual(campaigns.get_campaign_contacts(simulated_id)[0]["campaign_status"], "simulado")
        resend_id = campaigns.duplicate_campaign_for_resend(simulated_id)
        self.assertEqual(campaigns.get_campaign(resend_id)["name"], "Simulada + envio 2")

    def test_warmup_uses_number_provider_ready_flag_and_interruptible_sleep(self) -> None:
        self._use_database("warmup")
        contact_id = self._add_contact("Ana", "11999999999", "Clientes")
        contacts.add_contact_to_folder(contact_id, "Aquecimento")
        number_id = warmup.add_number(
            "Web",
            "11888888888",
            provider="web",
            ready_for_campaigns=True,
        )
        number = warmup.get_number(number_id)
        self.assertEqual(number["provider"], whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL)
        self.assertEqual(number["ready_for_campaigns"], 1)

        captured: list[dict[str, object]] = []

        class Client:
            def send_campaign_message(self, _contact, campaign):
                captured.append(dict(campaign))
                return whatsapp.SendResult(status="simulado", dry_run=True, delivery_mode=campaign["delivery_mode"])

        # This test validates provider propagation, not the wall-clock rest
        # policy.  Keep it deterministic even when the suite runs overnight.
        with mock.patch("warmup._inside_rest_window", return_value=False):
            totals = warmup.run_number_rampup(
                number_id,
                group_name="Aquecimento",
                client=Client(),
                explicit_user_confirmation=True,
            )
        self.assertEqual(totals["simulated"], 1)
        self.assertEqual(captured[0]["delivery_mode"], whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL)
        self.assertTrue(captured[0]["explicit_user_confirmation"])
        self.assertEqual(len(warmup.list_recent_runs(number_id=number_id)), 1)

        stop = threading.Event()
        stop.set()
        self.assertTrue(warmup._sleep_between_messages(1, 2, stop_event=stop))

    def test_worker_skips_real_web_campaign_without_confirmation(self) -> None:
        self._use_database("worker")
        campaign = {"id": 7, "status": campaigns.CAMPAIGN_STATUS_SCHEDULED,
                    "delivery_mode": whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL}
        real_web = whatsapp.WhatsAppConfig(
            delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
            dry_run=False,
        )
        with (
            mock.patch.object(background_worker.network, "has_internet", return_value=True),
            mock.patch.object(background_worker.campaigns, "get_resumable_campaigns", return_value=[]),
            mock.patch.object(background_worker.campaigns, "get_due_campaigns", return_value=[campaign]),
            mock.patch.object(background_worker, "load_config", return_value=real_web),
            mock.patch.object(background_worker.campaigns, "send_campaign") as send,
            mock.patch.object(background_worker, "_log") as log,
        ):
            background_worker._run_pending_campaigns()
        send.assert_not_called()
        self.assertTrue(any("confirmacao explicita" in str(call) for call in log.call_args_list))

        dry_web = whatsapp.WhatsAppConfig(
            delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
            dry_run=True,
        )
        with (
            mock.patch.object(background_worker.network, "has_internet", return_value=True),
            mock.patch.object(background_worker.campaigns, "get_resumable_campaigns", return_value=[]),
            mock.patch.object(background_worker.campaigns, "get_due_campaigns", return_value=[campaign]),
            mock.patch.object(background_worker, "load_config", return_value=dry_web),
            mock.patch.object(background_worker.campaigns, "can_start_campaign", return_value=(True, "")),
            mock.patch.object(background_worker.campaigns, "send_campaign", return_value={"simulado": 1}) as send,
        ):
            background_worker._run_pending_campaigns()
        send.assert_called_once_with(
            7,
            progress_callback=mock.ANY,
            stop_event=None,
            runner="background_worker",
            allow_resume=False,
        )


if __name__ == "__main__":
    unittest.main()
