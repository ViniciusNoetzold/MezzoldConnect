"""Exportador SQL usado pela interface, pelo executável e pelo instalador."""
from __future__ import annotations

import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _constraint_name(prefix: str, table: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", table).upper()
    return f"{prefix}_{normalized}"[:63]


def _firebird_type(declared_type: str) -> str:
    value = (declared_type or "").strip().upper()
    if "INT" in value:
        return "BIGINT"
    if any(token in value for token in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
        return "DOUBLE PRECISION"
    if "BLOB" in value:
        return "BLOB"
    return "VARCHAR(8191)"


def _sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "x'" + bytes(value).hex().upper() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def export_sqlite_to_firebird_sql(
    db_path: str | Path,
    output_sql_path: str | Path,
) -> Path:
    """Export all application tables to a UTF-8 Firebird/ANSI SQL script."""
    source = Path(db_path).expanduser().resolve()
    destination = Path(output_sql_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Banco de dados não encontrado: {source}")
    if source == destination:
        raise ValueError("O arquivo SQL não pode substituir o banco ativo.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    uri = f"{source.as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            table_rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            tables = [str(row[0]) for row in table_rows]

            lines = [
                "/* Mezzold Connect - exportação SQLite para Firebird/ANSI SQL",
                f"   Gerado em: {datetime.now().isoformat(timespec='seconds')}",
                f"   Origem: {source}",
                "*/",
                "SET NAMES UTF8;",
                "",
            ]

            for table in tables:
                columns = connection.execute(
                    f"PRAGMA table_info({_identifier(table)})"
                ).fetchall()
                definitions: list[str] = []
                primary_keys: list[tuple[int, str]] = []
                for column in columns:
                    name = str(column[1])
                    declaration = f"    {_identifier(name)} {_firebird_type(str(column[2] or ''))}"
                    if int(column[3] or 0):
                        declaration += " NOT NULL"
                    definitions.append(declaration)
                    if int(column[5] or 0):
                        primary_keys.append((int(column[5]), name))
                if primary_keys:
                    ordered = [_identifier(name) for _, name in sorted(primary_keys)]
                    definitions.append(
                        f"    CONSTRAINT {_identifier(_constraint_name('PK', table))} "
                        f"PRIMARY KEY ({', '.join(ordered)})"
                    )

                lines.extend(
                    [
                        f"/* Tabela: {table} */",
                        f"CREATE TABLE {_identifier(table)} (",
                        ",\n".join(definitions),
                        ");",
                    ]
                )

                records = connection.execute(
                    f"SELECT * FROM {_identifier(table)}"
                ).fetchall()
                column_names = [str(item[1]) for item in columns]
                quoted_columns = ", ".join(_identifier(name) for name in column_names)
                for record in records:
                    values = ", ".join(_sql_value(record[name]) for name in column_names)
                    lines.append(
                        f"INSERT INTO {_identifier(table)} ({quoted_columns}) VALUES ({values});"
                    )
                lines.extend(["COMMIT;", ""])

        temp.write_text("\n".join(lines), encoding="utf-8")
        os.replace(temp, destination)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return destination


__all__ = ["export_sqlite_to_firebird_sql"]
