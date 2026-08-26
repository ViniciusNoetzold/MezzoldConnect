from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from data_export import export_sqlite_to_firebird_sql
from installer import installer_app


class DataExportTests(unittest.TestCase):
    def test_export_quotes_identifiers_values_and_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            destination = root / "export.sql"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute(
                    'CREATE TABLE "sample table" (id INTEGER PRIMARY KEY, note TEXT, payload BLOB)'
                )
                connection.execute(
                    'INSERT INTO "sample table" (note, payload) VALUES (?, ?)',
                    ("Cliente d'Ávila", b"\x01\x02"),
                )
                connection.commit()
            result = export_sqlite_to_firebird_sql(source, destination)
            self.assertEqual(result, destination.resolve())
            text = destination.read_text(encoding="utf-8")
            self.assertIn('CREATE TABLE "sample table"', text)
            self.assertIn("Cliente d''Ávila", text)
            self.assertIn("x'0102'", text)
            self.assertIn("COMMIT;", text)

    def test_export_rejects_database_as_its_own_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            sqlite3.connect(source).close()
            with self.assertRaises(ValueError):
                export_sqlite_to_firebird_sql(source, source)


class InstallerContractTests(unittest.TestCase):
    def test_database_initialization_uses_application_cli(self) -> None:
        with patch.object(installer_app, "run_app_cli") as runner:
            installer_app.initialize_database_file()
        runner.assert_called_once_with("--initialize-database")

    def test_maintenance_scripts_require_no_global_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            installer_app, "SCRIPTS_DIR", Path(directory)
        ):
            installer_app.write_maintenance_scripts()
            backup = (Path(directory) / "backup_banco.bat").read_text(encoding="utf-8")
            export = (Path(directory) / "exportar_dados_firebird_sql.bat").read_text(encoding="utf-8")
        self.assertIn("MezzoldConnect.exe", backup)
        self.assertIn("--backup-database", backup)
        self.assertIn("MezzoldConnect.exe", export)
        self.assertIn("--export-firebird", export)
        self.assertNotIn("python ", (backup + export).lower())


if __name__ == "__main__":
    unittest.main()
