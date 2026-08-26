"""Compatibilidade: encaminha exportações antigas ao exportador único da v2."""
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_export import export_sqlite_to_firebird_sql  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    source = Path(args[0]) if args else Path("C:/MezzoldConnect/data/mezzold_connect.sqlite3")
    destination = (
        Path(args[1])
        if len(args) > 1
        else Path("C:/MezzoldConnect/data/mezzold_connect_firebird.sql")
    )
    try:
        print(export_sqlite_to_firebird_sql(source, destination))
        return 0
    except Exception as exc:
        print(f"Falha na exportação: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
