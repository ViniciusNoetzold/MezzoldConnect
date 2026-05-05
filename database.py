from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


APP_TITLE = "Mezzold Connect"
APP_VERSION = "1.0.0"

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("MEZZOLD_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("MEZZOLD_DB_PATH", DATA_DIR / "mezzold_connect.sqlite3"))


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect() -> Iterable[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def initialize_database() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                email TEXT DEFAULT '',
                group_name TEXT DEFAULT '',
                opt_in INTEGER NOT NULL DEFAULT 1,
                opt_in_source TEXT DEFAULT '',
                opt_in_category TEXT DEFAULT 'marketing',
                opt_in_at TEXT,
                opt_out_at TEXT,
                last_inbound_at TEXT,
                blacklisted INTEGER NOT NULL DEFAULT 0,
                consent_notes TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                media_path TEXT DEFAULT '',
                template_name TEXT DEFAULT '',
                template_language TEXT NOT NULL DEFAULT 'pt_BR',
                message_category TEXT NOT NULL DEFAULT 'marketing',
                risk_score INTEGER NOT NULL DEFAULT 0,
                risk_level TEXT DEFAULT 'pendente',
                risk_notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'rascunho',
                scheduled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_contacts (
                campaign_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'aguardando',
                last_error TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, contact_id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS campaign_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                media_path TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS message_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER,
                contact_id INTEGER,
                phone TEXT NOT NULL,
                recipient_name TEXT DEFAULT '',
                status TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                provider_message_id TEXT DEFAULT '',
                action_url TEXT DEFAULT '',
                message_body TEXT DEFAULT '',
                media_path TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS whatsapp_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                phone_number_id TEXT DEFAULT '',
                provider TEXT DEFAULT 'official_api',
                status TEXT NOT NULL DEFAULT 'testing',
                quality_rating TEXT NOT NULL DEFAULT 'unknown',
                messaging_limit INTEGER NOT NULL DEFAULT 250,
                daily_target INTEGER NOT NULL DEFAULT 20,
                max_daily_target INTEGER NOT NULL DEFAULT 500,
                ready_for_campaigns INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                rest_start TEXT NOT NULL DEFAULT '00:00',
                rest_end TEXT NOT NULL DEFAULT '07:00',
                notes TEXT DEFAULT '',
                last_health_check_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS number_rampup_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whatsapp_number_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                group_name TEXT DEFAULT '',
                target_contacts INTEGER NOT NULL DEFAULT 0,
                sent INTEGER NOT NULL DEFAULT 0,
                simulated INTEGER NOT NULL DEFAULT 0,
                manual INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                notes TEXT DEFAULT '',
                FOREIGN KEY (whatsapp_number_id) REFERENCES whatsapp_numbers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS number_rampup_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                whatsapp_number_id INTEGER NOT NULL,
                contact_id INTEGER,
                phone TEXT NOT NULL,
                recipient_name TEXT DEFAULT '',
                status TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                provider_message_id TEXT DEFAULT '',
                action_url TEXT DEFAULT '',
                message_body TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES number_rampup_runs(id) ON DELETE SET NULL,
                FOREIGN KEY (whatsapp_number_id) REFERENCES whatsapp_numbers(id) ON DELETE CASCADE,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS license (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                license_key TEXT DEFAULT '',
                plan_name TEXT DEFAULT '',
                valid_until TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pendente',
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_group ON contacts(group_name);
            CREATE INDEX IF NOT EXISTS idx_contacts_opt_in ON contacts(opt_in);
            CREATE INDEX IF NOT EXISTS idx_logs_created ON message_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
            CREATE INDEX IF NOT EXISTS idx_numbers_status ON whatsapp_numbers(status);
            CREATE INDEX IF NOT EXISTS idx_rampup_events_number ON number_rampup_events(whatsapp_number_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_rampup_events_contact ON number_rampup_events(contact_id);
            """
        )

        _ensure_column(conn, "contacts", "opt_in_source", "TEXT DEFAULT ''")
        _ensure_column(conn, "contacts", "opt_in_category", "TEXT DEFAULT 'marketing'")
        _ensure_column(conn, "contacts", "opt_in_at", "TEXT")
        _ensure_column(conn, "contacts", "opt_out_at", "TEXT")
        _ensure_column(conn, "contacts", "last_inbound_at", "TEXT")
        _ensure_column(conn, "contacts", "consent_notes", "TEXT DEFAULT ''")
        _ensure_column(conn, "campaigns", "message_category", "TEXT NOT NULL DEFAULT 'marketing'")
        _ensure_column(conn, "campaigns", "risk_score", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "campaigns", "risk_level", "TEXT DEFAULT 'pendente'")
        _ensure_column(conn, "campaigns", "risk_notes", "TEXT DEFAULT ''")
        _ensure_column(conn, "message_logs", "action_url", "TEXT DEFAULT ''")
        _ensure_column(conn, "message_logs", "message_body", "TEXT DEFAULT ''")
        _ensure_column(conn, "message_logs", "media_path", "TEXT DEFAULT ''")

        defaults = {
            "whatsapp_api_version": "v24.0",
            "whatsapp_phone_number_id": "",
            "whatsapp_business_account_id": "",
            "whatsapp_webhook_url": "",
            "whatsapp_default_template": "",
            "whatsapp_default_language": "pt_BR",
            "whatsapp_token_protected": "",
            "delivery_mode": "official_api",
            "whatsapp_dry_run": "1",
            "send_interval_seconds": "2",
            "daily_send_limit": "500",
            "smart_send_enabled": "0",
            "smart_min_interval_seconds": "30",
            "smart_max_interval_seconds": "45",
            "smart_pause_every": "10",
            "smart_pause_min_seconds": "120",
            "smart_pause_max_seconds": "300",
            "smart_daily_limit": "100",
            "smart_max_session_minutes": "90",
            "rampup_min_interval_seconds": "45",
            "rampup_max_interval_seconds": "180",
            "rampup_daily_floor": "5",
            "block_high_risk_campaigns": "1",
            "company_name": "Mezzold",
        }
        for key, value in defaults.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, now_text()),
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO license
                (id, license_key, plan_name, valid_until, status, updated_at)
            VALUES (1, '', '', '', 'pendente', ?)
            """,
            (now_text(),),
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {str(row["name"]) for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return str(row["value"])


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, now_text()),
        )


def set_settings(values: dict[str, str]) -> None:
    with connect() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now_text()),
            )
