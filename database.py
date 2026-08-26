from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


APP_TITLE = "Mezzold Connect"
APP_VERSION = "2.1.0"
APP_DOWNLOAD_URL = "https://github.com/ViniciusNoetzold/MezzoldConnect/releases"
DEFAULT_CONTACT_FOLDER = "Importados"
LATEST_SCHEMA_VERSION = 4
INSTALLED_DATA_DIR = Path("C:/MezzoldConnect/data")

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    DEFAULT_DATA_DIR = INSTALLED_DATA_DIR
else:
    BASE_DIR = Path(__file__).resolve().parent
    DEFAULT_DATA_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("MEZZOLD_DATA_DIR", DEFAULT_DATA_DIR))
DB_PATH = Path(os.environ.get("MEZZOLD_DB_PATH", DATA_DIR / "mezzold_connect.sqlite3"))


def legacy_data_dir() -> Path | None:
    """Return the v1 per-user data directory without creating or changing it."""
    override = os.environ.get("MEZZOLD_LEGACY_DATA_DIR", "").strip()
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None
    return Path(local_app_data) / "Mezzold Connect" / "data"


def legacy_db_path() -> Path | None:
    directory = legacy_data_dir()
    if directory is None:
        return None
    return directory / "mezzold_connect.sqlite3"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _open_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    return sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)


def check_database_integrity(path: str | Path | None = None) -> tuple[bool, str]:
    """Run SQLite's integrity check without mutating the database."""
    source = Path(path) if path is not None else DB_PATH
    if not source.is_file():
        return False, f"Banco nao encontrado: {source}"
    try:
        with closing(_open_read_only(source)) as conn:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as exc:
        return False, str(exc)
    messages = [str(row[0]) for row in rows]
    ok = len(messages) == 1 and messages[0].lower() == "ok"
    return ok, "\n".join(messages)


def _assert_database_integrity(path: Path, label: str) -> None:
    ok, detail = check_database_integrity(path)
    if not ok:
        raise RuntimeError(f"{label} falhou na verificacao de integridade: {detail}")


def _publish_new_file(temp_path: Path, target_path: Path) -> None:
    """Publish a new file atomically without ever overwriting an existing target."""
    try:
        os.link(temp_path, target_path)
    except FileExistsError:
        raise
    except OSError:
        descriptor = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
        try:
            os.replace(temp_path, target_path)
        except Exception:
            target_path.unlink(missing_ok=True)
            raise
    else:
        temp_path.unlink()


def create_backup(
    destination: str | Path | None = None,
    *,
    source_path: str | Path | None = None,
    verify: bool = True,
) -> Path:
    """Create a consistent SQLite backup and optionally verify the result.

    SQLite's online backup API is used instead of a raw file copy, so a WAL-mode
    database can be backed up safely while the application is open.
    """
    source = Path(source_path) if source_path is not None else DB_PATH
    if not source.is_file():
        raise FileNotFoundError(f"Banco nao encontrado: {source}")
    if destination is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = DATA_DIR / "backups" / f"mezzold-connect-{stamp}.sqlite3"
    else:
        target = Path(destination)
        if target.exists() and target.is_dir():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            target = target / f"mezzold-connect-{stamp}.sqlite3"
    source_resolved = source.expanduser().resolve()
    target_resolved = target.expanduser().resolve()
    if source_resolved == target_resolved:
        raise ValueError("O destino do backup precisa ser diferente do banco ativo.")
    if verify:
        _assert_database_integrity(source_resolved, "Banco de origem")
    target_resolved.parent.mkdir(parents=True, exist_ok=True)
    if target_resolved.exists():
        raise FileExistsError(f"O backup ja existe: {target_resolved}")

    temp_target = target_resolved.with_name(
        f".{target_resolved.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with closing(_open_read_only(source_resolved)) as source_conn:
            with closing(sqlite3.connect(temp_target)) as target_conn:
                source_conn.backup(target_conn)
        if verify:
            _assert_database_integrity(temp_target, "Backup SQLite")
        _publish_new_file(temp_target, target_resolved)
    finally:
        try:
            temp_target.unlink(missing_ok=True)
        except OSError:
            pass
    return target_resolved


backup_database = create_backup


def migrate_legacy_database_once(
    source_path: str | Path | None = None,
    target_path: str | Path | None = None,
) -> Path | None:
    """Copy the v1 per-user database once, leaving the source untouched.

    The import only runs while the v2 target does not exist. Both the source and
    the copied database are integrity checked; the final name is installed with
    an atomic replace after a successful SQLite backup.
    """
    source_candidate = Path(source_path) if source_path is not None else legacy_db_path()
    target = Path(target_path) if target_path is not None else DB_PATH
    if source_candidate is None or not source_candidate.is_file() or target.exists():
        return None
    source = source_candidate.expanduser().resolve()
    target = target.expanduser().resolve()
    if source == target:
        return None

    _assert_database_integrity(source, "Banco legado")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f".{target.name}.{uuid.uuid4().hex}.legacy.tmp")
    try:
        with closing(_open_read_only(source)) as source_conn:
            with closing(sqlite3.connect(temp_target)) as target_conn:
                source_conn.backup(target_conn)
        _assert_database_integrity(temp_target, "Copia do banco legado")
        try:
            _publish_new_file(temp_target, target)
        except FileExistsError:
            return None
    finally:
        try:
            temp_target.unlink(missing_ok=True)
        except OSError:
            pass
    return target


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


def _database_needs_migration_backup(path: Path) -> bool:
    try:
        with closing(_open_read_only(path)) as conn:
            user_tables = int(
                conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
            )
            if user_tables == 0:
                return False
            has_versions = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
            ).fetchone()
            if not has_versions:
                return True
            current = int(conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0])
            return current < LATEST_SCHEMA_VERSION
    except sqlite3.Error:
        return True


def _should_auto_migrate_legacy_database() -> bool:
    return bool(
        getattr(sys, "frozen", False)
        or os.environ.get("MEZZOLD_LEGACY_DATA_DIR", "").strip()
        or os.environ.get("MEZZOLD_MIGRATE_LEGACY", "").strip() == "1"
    )


def initialize_database() -> None:
    legacy_source = legacy_db_path()
    legacy_copy: Path | None = None
    if _should_auto_migrate_legacy_database():
        legacy_copy = migrate_legacy_database_once()
    schema_before = get_schema_version() if DB_PATH.is_file() else 0
    pre_migration_backup: Path | None = None
    if DB_PATH.is_file():
        _assert_database_integrity(DB_PATH, "Banco ativo")
        if _database_needs_migration_backup(DB_PATH):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            destination = DATA_DIR / "backups" / f"pre-migration-v2-{stamp}.sqlite3"
            pre_migration_backup = create_backup(destination, source_path=DB_PATH)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'cliente',
                is_active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT,
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

            CREATE TABLE IF NOT EXISTS contact_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contact_folder_members (
                contact_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (contact_id, folder_id),
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES contact_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                media_path TEXT DEFAULT '',
                template_name TEXT DEFAULT '',
                template_language TEXT NOT NULL DEFAULT 'pt_BR',
                message_category TEXT NOT NULL DEFAULT 'marketing',
                folder_name TEXT DEFAULT '',
                delay_min_seconds INTEGER NOT NULL DEFAULT 30,
                delay_max_seconds INTEGER NOT NULL DEFAULT 45,
                delivery_mode TEXT NOT NULL DEFAULT 'official_api',
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
                delivery_mode TEXT NOT NULL DEFAULT 'official_api',
                message_body TEXT DEFAULT '',
                media_path TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_send_locks (
                campaign_id INTEGER PRIMARY KEY,
                owner TEXT NOT NULL,
                locked_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
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

            """
        )

        _apply_schema_migrations(conn)
        _upsert_current_app_version(conn)

    _write_migration_report(
        schema_before=schema_before,
        legacy_source=legacy_source,
        legacy_copy=legacy_copy,
        pre_migration_backup=pre_migration_backup,
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _schema_version(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "schema_version"):
        return 0
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_version").fetchone()
    return int(row["version"] or 0)


def get_schema_version() -> int:
    if not DB_PATH.is_file():
        return 0
    with connect() as conn:
        return _schema_version(conn)


def migration_report_path() -> Path:
    return DATA_DIR / "migration-report.json"


def get_migration_report() -> dict[str, Any]:
    """Return the last human-readable compatibility/migration report."""

    path = migration_report_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_migration_report(
    *,
    schema_before: int,
    legacy_source: Path | None,
    legacy_copy: Path | None,
    pre_migration_backup: Path | None,
) -> None:
    ok, integrity = check_database_integrity(DB_PATH)
    with connect() as conn:
        migrations = [
            dict(row)
            for row in conn.execute(
                "SELECT version, name, applied_at FROM schema_version ORDER BY version"
            ).fetchall()
        ]
    report = {
        "reported_at": now_text(),
        "app_version": APP_VERSION,
        "database_path": str(DB_PATH.resolve()),
        "legacy_source": str(legacy_source.resolve()) if legacy_source else "",
        "legacy_database_copied": bool(legacy_copy),
        "schema_before": int(schema_before),
        "schema_after": get_schema_version(),
        "pre_migration_backup": str(pre_migration_backup.resolve()) if pre_migration_backup else "",
        "integrity_ok": bool(ok),
        "integrity_detail": integrity,
        "applied_migrations": migrations,
    }
    path = migration_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _apply_schema_migrations(conn: sqlite3.Connection) -> None:
    migrations = (
        (1, "compatibility_columns", _migration_compatibility_columns),
        (2, "recover_installer_schema", _migration_recover_installer_schema),
        (3, "normalize_legacy_data", _migration_normalize_legacy_data),
        (4, "defaults_and_indexes", _migration_defaults_and_indexes),
    )
    current = _schema_version(conn)
    for version, name, migration in migrations:
        if version <= current:
            continue
        conn.execute("SAVEPOINT mezzold_schema_migration")
        try:
            migration(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, now_text()),
            )
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("RELEASE SAVEPOINT mezzold_schema_migration")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT mezzold_schema_migration")
            conn.execute("RELEASE SAVEPOINT mezzold_schema_migration")
            raise
        current = version


def _migration_compatibility_columns(conn: sqlite3.Connection) -> None:
    columns = {
        "users": {
            "role": "TEXT NOT NULL DEFAULT 'cliente'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "must_change_password": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT",
            "last_login_at": "TEXT",
        },
        "contacts": {
            "email": "TEXT DEFAULT ''",
            "group_name": "TEXT DEFAULT ''",
            "opt_in": "INTEGER NOT NULL DEFAULT 1",
            "opt_in_source": "TEXT DEFAULT ''",
            "opt_in_category": "TEXT DEFAULT 'marketing'",
            "opt_in_at": "TEXT",
            "opt_out_at": "TEXT",
            "last_inbound_at": "TEXT",
            "blacklisted": "INTEGER NOT NULL DEFAULT 0",
            "consent_notes": "TEXT DEFAULT ''",
            "notes": "TEXT DEFAULT ''",
            "updated_at": "TEXT",
        },
        "contact_folders": {
            "is_default": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT",
        },
        "campaigns": {
            "media_path": "TEXT DEFAULT ''",
            "template_name": "TEXT DEFAULT ''",
            "template_language": "TEXT NOT NULL DEFAULT 'pt_BR'",
            "message_category": "TEXT NOT NULL DEFAULT 'marketing'",
            "folder_name": "TEXT DEFAULT ''",
            "delay_min_seconds": "INTEGER NOT NULL DEFAULT 30",
            "delay_max_seconds": "INTEGER NOT NULL DEFAULT 45",
            "delivery_mode": "TEXT NOT NULL DEFAULT 'official_api'",
            "risk_score": "INTEGER NOT NULL DEFAULT 0",
            "risk_level": "TEXT DEFAULT 'pendente'",
            "risk_notes": "TEXT DEFAULT ''",
            "image_path": "TEXT DEFAULT ''",
            "security_preset": "TEXT NOT NULL DEFAULT 'Moderado'",
            "status": "TEXT NOT NULL DEFAULT 'rascunho'",
            "scheduled_at": "TEXT",
            "updated_at": "TEXT",
        },
        "campaign_contacts": {
            "last_error": "TEXT DEFAULT ''",
            "updated_at": "TEXT",
        },
        "message_logs": {
            "action_url": "TEXT DEFAULT ''",
            "delivery_mode": "TEXT NOT NULL DEFAULT 'official_api'",
            "message_body": "TEXT DEFAULT ''",
            "media_path": "TEXT DEFAULT ''",
        },
        "settings": {"updated_at": "TEXT"},
    }
    for table, definitions in columns.items():
        for column, definition in definitions.items():
            _ensure_column(conn, table, column, definition)

    timestamp = now_text()
    conn.execute(
        "UPDATE users SET updated_at = COALESCE(NULLIF(updated_at, ''), created_at, ?)",
        (timestamp,),
    )
    conn.execute(
        "UPDATE contacts SET updated_at = COALESCE(NULLIF(updated_at, ''), created_at, ?)",
        (timestamp,),
    )
    conn.execute(
        "UPDATE contact_folders SET updated_at = COALESCE(NULLIF(updated_at, ''), created_at, ?)",
        (timestamp,),
    )
    conn.execute(
        "UPDATE campaigns SET updated_at = COALESCE(NULLIF(updated_at, ''), created_at, ?)",
        (timestamp,),
    )
    conn.execute(
        "UPDATE campaign_contacts SET updated_at = COALESCE(NULLIF(updated_at, ''), sent_at, ?)",
        (timestamp,),
    ) if "sent_at" in _table_columns(conn, "campaign_contacts") else conn.execute(
        "UPDATE campaign_contacts SET updated_at = COALESCE(NULLIF(updated_at, ''), ?)",
        (timestamp,),
    )
    conn.execute(
        "UPDATE settings SET updated_at = COALESCE(NULLIF(updated_at, ''), ?)",
        (timestamp,),
    )


def _migration_recover_installer_schema(conn: sqlite3.Connection) -> None:
    _recover_installer_campaign_contacts(conn)
    _recover_installer_campaign_logs(conn)
    _recover_installer_warmup(conn)


def _recover_installer_campaign_contacts(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "campaign_contacts")
    installer_layout = bool({"id", "phone", "attempts", "sent_at"} & columns)
    if not installer_layout:
        return

    backup_table = "campaign_contacts_installer_legacy"
    if not _table_exists(conn, backup_table):
        conn.execute(
            f'CREATE TABLE "{backup_table}" AS SELECT * FROM campaign_contacts'
        )
    elif int(conn.execute(f'SELECT COUNT(*) FROM "{backup_table}"').fetchone()[0]) == 0:
        conn.execute(f'INSERT INTO "{backup_table}" SELECT * FROM campaign_contacts')

    conn.execute("DROP TABLE campaign_contacts")
    conn.execute(
        """
        CREATE TABLE campaign_contacts (
            campaign_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'aguardando',
            last_error TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (campaign_id, contact_id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
        )
        """
    )
    backup_columns = _table_columns(conn, backup_table)
    updated_expression = "COALESCE(NULLIF(l.updated_at, ''), NULLIF(l.sent_at, ''), ?)"
    if "sent_at" not in backup_columns:
        updated_expression = "COALESCE(NULLIF(l.updated_at, ''), ?)"
    conn.execute(
        f"""
        INSERT OR IGNORE INTO campaign_contacts
            (campaign_id, contact_id, status, last_error, updated_at)
        SELECT
            l.campaign_id,
            l.contact_id,
            CASE WHEN COALESCE(NULLIF(TRIM(l.status), ''), 'pendente') = 'pendente'
                 THEN 'aguardando' ELSE l.status END,
            COALESCE(l.last_error, ''),
            {updated_expression}
        FROM "{backup_table}" l
        WHERE EXISTS (SELECT 1 FROM campaigns c WHERE c.id = l.campaign_id)
          AND EXISTS (SELECT 1 FROM contacts c WHERE c.id = l.contact_id)
        ORDER BY l.rowid
        """,
        (now_text(),),
    )


def _recover_installer_campaign_logs(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "campaign_logs"):
        return
    columns = _table_columns(conn, "campaign_logs")
    required = {"phone", "status", "created_at"}
    if not required.issubset(columns):
        return
    conn.execute(
        """
        INSERT INTO message_logs
            (campaign_id, contact_id, phone, recipient_name, status, error_message,
             provider_message_id, action_url, delivery_mode, message_body, media_path, created_at)
        SELECT
            CASE WHEN EXISTS (SELECT 1 FROM campaigns c WHERE c.id = l.campaign_id)
                 THEN l.campaign_id ELSE NULL END,
            NULL,
            l.phone,
            COALESCE(l.recipient_name, ''),
            l.status,
            COALESCE(l.error_message, ''),
            '',
            COALESCE(l.action_url, ''),
            COALESCE(NULLIF(l.delivery_mode, ''), 'official_api'),
            '',
            '',
            l.created_at
        FROM campaign_logs l
        """
    )


def _recover_installer_warmup(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "warmup_numbers"):
        conn.execute(
            """
            INSERT OR IGNORE INTO whatsapp_numbers
                (id, display_name, phone, phone_number_id, provider, status, quality_rating,
                 messaging_limit, daily_target, max_daily_target, ready_for_campaigns,
                 active, rest_start, rest_end, notes, last_health_check_at, created_at, updated_at)
            SELECT
                id,
                display_name,
                phone,
                COALESCE(phone_number_id, ''),
                CASE LOWER(COALESCE(provider, ''))
                    WHEN 'oficial' THEN 'official_api'
                    WHEN 'api oficial' THEN 'official_api'
                    WHEN 'manual' THEN 'manual_assisted'
                    ELSE COALESCE(NULLIF(provider, ''), 'official_api')
                END,
                COALESCE(NULLIF(status, ''), 'testing'),
                COALESCE(NULLIF(quality_rating, ''), 'unknown'),
                MAX(CAST(COALESCE(NULLIF(messaging_limit, ''), '250') AS INTEGER), 1),
                MAX(COALESCE(daily_target, 20), 1),
                MAX(COALESCE(max_daily_target, 500), COALESCE(daily_target, 20)),
                COALESCE(ready_for_campaigns, 0),
                COALESCE(active, 1),
                COALESCE(NULLIF(rest_start, ''), '00:00'),
                COALESCE(NULLIF(rest_end, ''), '07:00'),
                COALESCE(notes, ''),
                NULL,
                COALESCE(NULLIF(created_at, ''), ?),
                COALESCE(NULLIF(created_at, ''), ?)
            FROM warmup_numbers
            """,
            (now_text(), now_text()),
        )
    if _table_exists(conn, "warmup_events"):
        conn.execute(
            """
            INSERT INTO number_rampup_events
                (run_id, whatsapp_number_id, contact_id, phone, recipient_name, status,
                 error_message, provider_message_id, action_url, message_body, created_at)
            SELECT
                NULL,
                e.number_id,
                NULL,
                e.phone,
                COALESCE(e.recipient_name, ''),
                e.status,
                COALESCE(e.error_message, ''),
                '',
                '',
                '',
                e.created_at
            FROM warmup_events e
            WHERE EXISTS (SELECT 1 FROM whatsapp_numbers n WHERE n.id = e.number_id)
            """
        )


def _migration_normalize_legacy_data(conn: sqlite3.Connection) -> None:
    timestamp = now_text()
    conn.execute(
        """
        UPDATE users
        SET updated_at = COALESCE(NULLIF(updated_at, ''), created_at, ?),
            role = CASE
                WHEN username = '000' THEN 'mezzold_master'
                WHEN COALESCE(TRIM(role), '') IN ('', 'user', 'usuario', 'usuário', 'client', 'operator', 'operador') THEN 'cliente'
                WHEN COALESCE(TRIM(role), '') IN ('client_admin', 'cliente_admin', 'administrador_cliente', 'administrator', 'administrador') THEN 'admin'
                WHEN COALESCE(TRIM(role), '') IN ('master', 'mezzold master') THEN 'mezzold_master'
                ELSE LOWER(TRIM(role))
            END
        """,
        (timestamp,),
    )
    _migrate_contact_folders(conn)
    duplicate_phones = int(
        conn.execute(
            "SELECT COUNT(*) FROM (SELECT phone FROM contacts GROUP BY phone HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    )
    if duplicate_phones == 0:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_phone ON contacts(phone)")
    else:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)")


def _migration_defaults_and_indexes(conn: sqlite3.Connection) -> None:
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
        "app_theme": "light",
        "ui_font_size": "10",
        "ui_density": "normal",
        "app_update_manifest_url": "",
        "app_update_download_url": APP_DOWNLOAD_URL,
        "app_update_channel": "stable",
    }
    timestamp = now_text()
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, timestamp),
        )
    conn.execute(
        """
        INSERT OR IGNORE INTO license
            (id, license_key, plan_name, valid_until, status, updated_at)
        VALUES (1, '', '', '', 'pendente', ?)
        """,
        (timestamp,),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_group ON contacts(group_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_opt_in ON contacts(opt_in)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_folder_members_folder ON contact_folder_members(folder_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON message_logs(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_numbers_status ON whatsapp_numbers(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rampup_events_number ON number_rampup_events(whatsapp_number_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rampup_events_contact ON number_rampup_events(contact_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_contacts_status ON campaign_contacts(campaign_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_phone_created ON message_logs(phone, created_at)")


def _upsert_current_app_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ('app_current_version', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (APP_VERSION, now_text()),
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = _table_columns(conn, table)
    if not existing:
        return
    if column not in existing:
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _migrate_contact_folders(conn: sqlite3.Connection) -> None:
    timestamp = now_text()
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folders (name, is_default, created_at, updated_at)
        VALUES (?, 1, ?, ?)
        """,
        (DEFAULT_CONTACT_FOLDER, timestamp, timestamp),
    )
    conn.execute(
        """
        UPDATE contact_folders
        SET is_default = CASE WHEN name = ? THEN 1 ELSE 0 END,
            updated_at = CASE WHEN name = ? THEN ? ELSE updated_at END
        """,
        (DEFAULT_CONTACT_FOLDER, DEFAULT_CONTACT_FOLDER, timestamp),
    )
    conn.execute(
        """
        UPDATE contacts
        SET group_name = ?
        WHERE COALESCE(TRIM(group_name), '') = ''
        """,
        (DEFAULT_CONTACT_FOLDER,),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folders (name, is_default, created_at, updated_at)
        SELECT DISTINCT TRIM(group_name), 0, ?, ?
        FROM contacts
        WHERE COALESCE(TRIM(group_name), '') <> ''
        """,
        (timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folder_members (contact_id, folder_id, created_at)
        SELECT contacts.id, contact_folders.id, ?
        FROM contacts
        JOIN contact_folders ON contact_folders.name = TRIM(contacts.group_name)
        WHERE COALESCE(TRIM(contacts.group_name), '') <> ''
        """,
        (timestamp,),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folder_members (contact_id, folder_id, created_at)
        SELECT contacts.id, contact_folders.id, ?
        FROM contacts
        JOIN contact_folders ON contact_folders.name = ?
        WHERE NOT EXISTS (
            SELECT 1
            FROM contact_folder_members
            WHERE contact_folder_members.contact_id = contacts.id
        )
        """,
        (timestamp, DEFAULT_CONTACT_FOLDER),
    )


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
