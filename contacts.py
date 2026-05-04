from __future__ import annotations

import csv
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from database import connect, now_text, row_to_dict, rows_to_dicts


PHONE_RE = re.compile(r"\D+")
XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ContactError(ValueError):
    pass


@dataclass
class ImportSummary:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def normalize_phone(phone: str) -> str:
    digits = PHONE_RE.sub("", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    digits = digits.lstrip("0")
    if digits.startswith("550") and len(digits) >= 13:
        digits = "55" + digits[3:]
    if digits and not digits.startswith("55"):
        digits = "55" + digits
    return digits


def is_valid_phone(phone: str) -> bool:
    phone = normalize_phone(phone)
    if not phone.startswith("55"):
        return False
    return phone.isdigit() and len(phone) in {12, 13}


def parse_opt_in(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    text = normalize_text(str(value or "sim"))
    if text in {"nao", "n", "no", "false", "0", "sem_permissao", "descadastrado"}:
        return 0
    return 1


def add_contact(
    name: str,
    phone: str,
    email: str = "",
    group_name: str = "",
    opt_in: int = 1,
    opt_in_source: str = "manual",
    opt_in_category: str = "marketing",
    opt_in_at: str = "",
    consent_notes: str = "",
    notes: str = "",
) -> int:
    name = name.strip() or "Cliente"
    phone = normalize_phone(phone)
    if not is_valid_phone(phone):
        raise ContactError("Número inválido. Use DDD e telefone, com ou sem +55.")

    timestamp = now_text()
    opt_in_at = opt_in_at.strip() or (timestamp if opt_in else "")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO contacts
                (name, phone, email, group_name, opt_in, opt_in_source,
                 opt_in_category, opt_in_at, consent_notes, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                email.strip(),
                group_name.strip(),
                int(bool(opt_in)),
                opt_in_source.strip(),
                opt_in_category.strip() or "marketing",
                opt_in_at,
                consent_notes.strip(),
                notes,
                timestamp,
                timestamp,
            ),
        )
    return int(cursor.lastrowid)


def upsert_contact(
    name: str,
    phone: str,
    email: str = "",
    group_name: str = "",
    opt_in: int = 1,
    opt_in_source: str = "",
    opt_in_category: str = "marketing",
    opt_in_at: str = "",
    consent_notes: str = "",
    notes: str = "",
) -> tuple[int, bool]:
    name = name.strip() or "Cliente"
    phone = normalize_phone(phone)
    if not is_valid_phone(phone):
        raise ContactError(f"Número inválido: {phone or 'vazio'}")

    timestamp = now_text()
    opt_in_at = opt_in_at.strip() or (timestamp if opt_in else "")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM contacts WHERE phone = ?", (phone,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE contacts
                SET name = ?, email = ?, group_name = ?, opt_in = ?,
                    opt_in_source = ?, opt_in_category = ?, opt_in_at = ?,
                    opt_out_at = CASE WHEN ? = 1 THEN NULL ELSE COALESCE(opt_out_at, ?) END,
                    consent_notes = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    email.strip(),
                    group_name.strip(),
                    int(bool(opt_in)),
                    opt_in_source.strip(),
                    opt_in_category.strip() or "marketing",
                    opt_in_at,
                    int(bool(opt_in)),
                    timestamp,
                    consent_notes.strip(),
                    notes,
                    timestamp,
                    existing["id"],
                ),
            )
            return int(existing["id"]), True

        cursor = conn.execute(
            """
            INSERT INTO contacts
                (name, phone, email, group_name, opt_in, opt_in_source,
                 opt_in_category, opt_in_at, consent_notes, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                email.strip(),
                group_name.strip(),
                int(bool(opt_in)),
                opt_in_source.strip(),
                opt_in_category.strip() or "marketing",
                opt_in_at,
                consent_notes.strip(),
                notes,
                timestamp,
                timestamp,
            ),
        )
    return int(cursor.lastrowid), False


def update_contact(contact_id: int, **fields: object) -> None:
    allowed = {
        "name",
        "phone",
        "email",
        "group_name",
        "opt_in",
        "opt_in_source",
        "opt_in_category",
        "opt_in_at",
        "opt_out_at",
        "last_inbound_at",
        "blacklisted",
        "consent_notes",
        "notes",
    }
    updates: list[str] = []
    values: list[object] = []
    timestamp = now_text()

    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "phone":
            value = normalize_phone(str(value))
            if not is_valid_phone(str(value)):
                raise ContactError("Número inválido. Use DDD e telefone, com ou sem +55.")
        if key in {"opt_in", "blacklisted"}:
            value = int(bool(value))
            if key == "opt_in":
                if value:
                    updates.append("opt_out_at = ?")
                    values.append(None)
                    updates.append("opt_in_at = COALESCE(opt_in_at, ?)")
                    values.append(timestamp)
                else:
                    updates.append("opt_out_at = COALESCE(opt_out_at, ?)")
                    values.append(timestamp)
        updates.append(f"{key} = ?")
        values.append(value)

    if not updates:
        return

    updates.append("updated_at = ?")
    values.append(timestamp)
    values.append(contact_id)

    with connect() as conn:
        conn.execute(
            f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )


def delete_contact(contact_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def set_blacklist(contact_id: int, blocked: bool) -> None:
    update_contact(contact_id, blacklisted=int(blocked))


def mark_opt_out(contact_id: int, reason: str = "") -> None:
    contact = get_contact(contact_id)
    notes = str(contact.get("consent_notes") or "") if contact else ""
    if reason.strip():
        notes = f"{notes}\nOpt-out: {reason.strip()}".strip()
    update_contact(contact_id, opt_in=0, blacklisted=1, consent_notes=notes)


def register_inbound_message(phone: str, opted_in: bool = True, source: str = "whatsapp") -> None:
    phone = normalize_phone(phone)
    if not is_valid_phone(phone):
        raise ContactError("Número inválido.")
    timestamp = now_text()
    with connect() as conn:
        row = conn.execute("SELECT id FROM contacts WHERE phone = ?", (phone,)).fetchone()
        if row:
            updates = "last_inbound_at = ?, updated_at = ?"
            values: list[object] = [timestamp, timestamp]
            if opted_in:
                updates += ", opt_in = 1, opt_out_at = NULL, opt_in_at = COALESCE(opt_in_at, ?), opt_in_source = ?"
                values.extend([timestamp, source])
            values.append(row["id"])
            conn.execute(f"UPDATE contacts SET {updates} WHERE id = ?", tuple(values))


def list_contacts(search: str = "", group_name: str = "") -> list[dict[str, object]]:
    query = """
        SELECT *
        FROM contacts
        WHERE 1 = 1
    """
    params: list[object] = []
    if search.strip():
        term = f"%{search.strip()}%"
        query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        params.extend([term, term, term])
    if group_name.strip():
        query += " AND group_name = ?"
        params.append(group_name.strip())
    query += " ORDER BY name COLLATE NOCASE"

    with connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return rows_to_dicts(rows)


def get_contact(contact_id: int) -> dict[str, object] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return row_to_dict(row)


def list_groups() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT group_name
            FROM contacts
            WHERE group_name <> ''
            ORDER BY group_name COLLATE NOCASE
            """
        ).fetchall()
    return [str(row["group_name"]) for row in rows]


def _read_csv(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ContactError("Não foi possível ler o arquivo CSV.")

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    return [dict(row) for row in reader if any(row.values())]


def _column_index(cell_reference: str) -> int:
    letters = "".join(char for char in cell_reference if char.isalpha()).upper()
    total = 0
    for char in letters:
        total = total * 26 + (ord(char) - ord("A") + 1)
    return max(total - 1, 0)


def _read_xlsx(path: Path) -> list[dict[str, str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall("x:si", XLSX_NS):
                    shared_strings.append("".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")))

            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in archive.namelist():
                raise ContactError("A planilha precisa ter dados na primeira aba.")

            root = ElementTree.fromstring(archive.read(sheet_name))
    except zipfile.BadZipFile as exc:
        raise ContactError("Arquivo Excel inválido.") from exc

    rows: list[list[str]] = []
    for row_node in root.findall(".//x:sheetData/x:row", XLSX_NS):
        values: list[str] = []
        for cell in row_node.findall("x:c", XLSX_NS):
            index = _column_index(cell.attrib.get("r", "A1"))
            while len(values) <= index:
                values.append("")

            value = ""
            if cell.attrib.get("t") == "inlineStr":
                inline = cell.find("x:is", XLSX_NS)
                if inline is not None:
                    value = "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t"))
            else:
                node = cell.find("x:v", XLSX_NS)
                value = node.text if node is not None and node.text is not None else ""
                if cell.attrib.get("t") == "s" and value.isdigit():
                    value = shared_strings[int(value)]

            values[index] = value.strip()
        if any(values):
            rows.append(values)

    if not rows:
        return []

    headers = [header.strip() for header in rows[0]]
    result: list[dict[str, str]] = []
    for values in rows[1:]:
        item = {}
        for index, header in enumerate(headers):
            if header:
                item[header] = values[index] if index < len(values) else ""
        if any(item.values()):
            result.append(item)
    return result


def _pick(row: dict[str, str], aliases: set[str]) -> str:
    normalized = {normalize_text(str(key)): value for key, value in row.items() if key is not None}
    for alias in aliases:
        if alias in normalized:
            return str(normalized[alias] or "").strip()
    return ""


def import_contacts(path_text: str) -> ImportSummary:
    path = Path(path_text)
    if not path.exists():
        raise ContactError("Arquivo não encontrado.")

    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        rows = _read_csv(path)
    elif suffix == ".xlsx":
        rows = _read_xlsx(path)
    else:
        raise ContactError("Use um arquivo CSV ou Excel (.xlsx).")

    summary = ImportSummary()
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        name = _pick(row, {"nome", "name", "cliente", "contato"}) or "Cliente"
        phone = normalize_phone(_pick(row, {"numero", "número", "telefone", "phone", "celular", "whatsapp"}))
        email = _pick(row, {"email", "e_mail"})
        group_name = _pick(row, {"grupo", "lista", "group", "group_name"})
        opt_in = parse_opt_in(_pick(row, {"opt_in", "permissao", "permissão", "autorizacao", "autorização"}))
        opt_in_source = _pick(row, {"origem", "fonte", "source", "opt_in_source"}) or "importacao"
        opt_in_category = _pick(row, {"categoria", "category", "opt_in_category"}) or "marketing"
        opt_in_at = _pick(row, {"data_opt_in", "opt_in_at", "consentimento_em", "autorizado_em"})
        consent_notes = _pick(row, {"prova", "proof", "consent_notes", "observacao_consentimento"})

        if not phone or not is_valid_phone(phone):
            summary.skipped += 1
            summary.errors.append(f"Linha {index}: número inválido.")
            continue

        if phone in seen:
            summary.duplicates += 1
            continue
        seen.add(phone)

        try:
            _, updated = upsert_contact(
                name,
                phone,
                email,
                group_name,
                opt_in,
                opt_in_source,
                opt_in_category,
                opt_in_at,
                consent_notes,
            )
        except ContactError as exc:
            summary.skipped += 1
            summary.errors.append(f"Linha {index}: {exc}")
            continue

        if updated:
            summary.updated += 1
        else:
            summary.imported += 1

    return summary
