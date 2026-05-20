from __future__ import annotations

import csv
import re
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from database import DEFAULT_CONTACT_FOLDER, connect, now_text, row_to_dict, rows_to_dicts


PHONE_RE = re.compile(r"\D+")
LEAD_PHONE_RE = re.compile(r"(?:\+?55[\s().-]*)?(?:\(?\d{2}\)?[\s().-]*)?(?:9?\d{4})[\s().-]?\d{4}")
XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LEAD_NAME_BLOCKLIST = {
    "aberto",
    "agora",
    "fechado",
    "telefone",
    "whatsapp",
    "site",
    "rotas",
    "compartilhar",
    "salvar",
    "avaliacoes",
    "avaliacao",
    "horarios",
    "horario",
}


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


def normalize_folder_name(name: str) -> str:
    return (name or "").strip() or DEFAULT_CONTACT_FOLDER


def _get_or_create_folder_id(conn, folder_name: str) -> int:
    folder_name = normalize_folder_name(folder_name)
    timestamp = now_text()
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folders (name, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            folder_name,
            1 if folder_name.casefold() == DEFAULT_CONTACT_FOLDER.casefold() else 0,
            timestamp,
            timestamp,
        ),
    )
    row = conn.execute("SELECT id FROM contact_folders WHERE name = ?", (folder_name,)).fetchone()
    if not row:
        raise ContactError("Não consegui criar a pasta de contatos.")
    return int(row["id"])


def _set_contact_primary_folder(conn, contact_id: int, folder_name: str) -> None:
    folder_name = normalize_folder_name(folder_name)
    folder_id = _get_or_create_folder_id(conn, folder_name)
    timestamp = now_text()
    conn.execute("DELETE FROM contact_folder_members WHERE contact_id = ?", (contact_id,))
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folder_members (contact_id, folder_id, created_at)
        VALUES (?, ?, ?)
        """,
        (contact_id, folder_id, timestamp),
    )
    conn.execute(
        "UPDATE contacts SET group_name = ?, updated_at = ? WHERE id = ?",
        (folder_name, timestamp, contact_id),
    )


def _add_contact_to_folder(conn, contact_id: int, folder_name: str) -> None:
    folder_id = _get_or_create_folder_id(conn, folder_name)
    conn.execute(
        """
        INSERT OR IGNORE INTO contact_folder_members (contact_id, folder_id, created_at)
        VALUES (?, ?, ?)
        """,
        (contact_id, folder_id, now_text()),
    )


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
        raise ContactError("Telefone inválido. Use DDD e número, com ou sem +55.")

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
        contact_id = int(cursor.lastrowid)
        _set_contact_primary_folder(conn, contact_id, group_name)
    return contact_id


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
        raise ContactError(f"Telefone inválido: {phone or 'vazio'}")

    timestamp = now_text()
    opt_in_at = opt_in_at.strip() or (timestamp if opt_in else "")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM contacts WHERE phone = ?", (phone,)).fetchone()
        if existing:
            contact_id = int(existing["id"])
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
                    contact_id,
                ),
            )
            _set_contact_primary_folder(conn, contact_id, group_name)
            return contact_id, True

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
        contact_id = int(cursor.lastrowid)
        _set_contact_primary_folder(conn, contact_id, group_name)
    return contact_id, False


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
    folder_name_to_apply: str | None = None

    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "phone":
            value = normalize_phone(str(value))
            if not is_valid_phone(str(value)):
                raise ContactError("Telefone inválido. Use DDD e número, com ou sem +55.")
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
        if key == "group_name":
            value = normalize_folder_name(str(value))
            folder_name_to_apply = str(value)
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
        if folder_name_to_apply is not None:
            _set_contact_primary_folder(conn, contact_id, folder_name_to_apply)


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
        raise ContactError("Telefone inválido. Confira DDD e número.")
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
        SELECT DISTINCT contacts.*
        FROM contacts
        WHERE 1 = 1
    """
    params: list[object] = []
    if search.strip():
        term = f"%{search.strip()}%"
        query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        params.extend([term, term, term])
    if group_name.strip():
        query += """
            AND EXISTS (
                SELECT 1
                FROM contact_folder_members cfm
                JOIN contact_folders cf ON cf.id = cfm.folder_id
                WHERE cfm.contact_id = contacts.id
                  AND cf.name = ?
            )
        """
        params.append(normalize_folder_name(group_name))
    query += " ORDER BY contacts.name COLLATE NOCASE"

    with connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return rows_to_dicts(rows)


def get_contact(contact_id: int) -> dict[str, object] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return row_to_dict(row)


def create_folder(name: str) -> int:
    name = normalize_folder_name(name)
    with connect() as conn:
        return _get_or_create_folder_id(conn, name)


def list_folders() -> list[dict[str, object]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                cf.id,
                cf.name,
                cf.is_default,
                cf.created_at,
                cf.updated_at,
                COUNT(cfm.contact_id) AS total_contacts
            FROM contact_folders cf
            LEFT JOIN contact_folder_members cfm ON cfm.folder_id = cf.id
            GROUP BY cf.id
            ORDER BY cf.is_default DESC, cf.name COLLATE NOCASE
            """
        ).fetchall()
    return rows_to_dicts(rows)


def list_contacts_by_folder(folder_name: str, search: str = "") -> list[dict[str, object]]:
    return list_contacts(search=search, group_name=folder_name)


def list_used_contacts(folder_name: str = "", search: str = "", limit: int = 1000) -> list[dict[str, object]]:
    query = """
        SELECT
            message_logs.phone,
            COALESCE(NULLIF(contacts.name, ''), message_logs.recipient_name) AS recipient_name,
            contacts.id AS contact_id,
            contacts.group_name,
            message_logs.status AS status,
            campaigns.name AS campaign_name,
            MAX(message_logs.created_at) AS last_sent_at,
            COUNT(*) AS attempts
        FROM message_logs
        LEFT JOIN contacts ON contacts.id = message_logs.contact_id
        LEFT JOIN campaigns ON campaigns.id = message_logs.campaign_id
        WHERE message_logs.status IN ('enviado', 'simulado', 'pendente_manual')
    """
    params: list[object] = []
    if folder_name.strip():
        query += """
            AND EXISTS (
                SELECT 1
                FROM contact_folder_members cfm
                JOIN contact_folders cf ON cf.id = cfm.folder_id
                WHERE cfm.contact_id = contacts.id
                  AND cf.name = ?
            )
        """
        params.append(normalize_folder_name(folder_name))
    if search.strip():
        term = f"%{search.strip()}%"
        query += """
            AND (
                contacts.name LIKE ?
                OR message_logs.recipient_name LIKE ?
                OR message_logs.phone LIKE ?
                OR campaigns.name LIKE ?
            )
        """
        params.extend([term, term, term, term])
    query += """
        GROUP BY
            message_logs.phone,
            recipient_name,
            contacts.id,
            contacts.group_name,
            message_logs.status,
            campaigns.name
        ORDER BY last_sent_at DESC
        LIMIT ?
    """
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return rows_to_dicts(rows)


def list_groups() -> list[str]:
    return [str(row["name"]) for row in list_folders()]


def rename_folder(folder_id: int, new_name: str) -> None:
    new_name = normalize_folder_name(new_name)
    with connect() as conn:
        row = conn.execute("SELECT * FROM contact_folders WHERE id = ?", (folder_id,)).fetchone()
        if not row:
            raise ContactError("Pasta não encontrada.")
        old_name = str(row["name"])
        try:
            conn.execute(
                "UPDATE contact_folders SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, now_text(), folder_id),
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise ContactError("Já existe uma pasta com esse nome.") from exc
            raise
        conn.execute(
            "UPDATE contacts SET group_name = ?, updated_at = ? WHERE group_name = ?",
            (new_name, now_text(), old_name),
        )


def delete_folder(folder_id: int) -> int:
    with connect() as conn:
        row = conn.execute("SELECT * FROM contact_folders WHERE id = ?", (folder_id,)).fetchone()
        if not row:
            raise ContactError("Pasta não encontrada.")
        if int(row["is_default"] or 0):
            raise ContactError("A pasta padrão não pode ser excluída.")
        old_name = str(row["name"])
        default_id = _get_or_create_folder_id(conn, DEFAULT_CONTACT_FOLDER)
        members = conn.execute(
            "SELECT contact_id FROM contact_folder_members WHERE folder_id = ?",
            (folder_id,),
        ).fetchall()
        for member in members:
            conn.execute(
                """
                INSERT OR IGNORE INTO contact_folder_members (contact_id, folder_id, created_at)
                VALUES (?, ?, ?)
                """,
                (member["contact_id"], default_id, now_text()),
            )
        conn.execute("DELETE FROM contact_folders WHERE id = ?", (folder_id,))
        conn.execute(
            "UPDATE contacts SET group_name = ?, updated_at = ? WHERE group_name = ?",
            (DEFAULT_CONTACT_FOLDER, now_text(), old_name),
        )
    return len(members)


def add_contact_to_folder(contact_id: int, folder_name: str) -> None:
    if not get_contact(contact_id):
        raise ContactError("Contato não encontrado.")
    with connect() as conn:
        _add_contact_to_folder(conn, contact_id, folder_name)


def set_contact_primary_folder(contact_id: int, folder_name: str) -> None:
    if not get_contact(contact_id):
        raise ContactError("Contato não encontrado.")
    with connect() as conn:
        _set_contact_primary_folder(conn, contact_id, folder_name)


def _read_csv(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ContactError("Não consegui ler o CSV. Tente salvar a planilha como UTF-8 ou importar em Excel .xlsx.")

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
        raise ContactError("Não consegui ler esse arquivo Excel.") from exc

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


def import_contacts(path_text: str, folder_name: str = "") -> ImportSummary:
    path = Path(path_text)
    if not path.exists():
        raise ContactError("Arquivo não encontrado. Escolha a planilha novamente.")

    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        rows = _read_csv(path)
    elif suffix == ".xlsx":
        rows = _read_xlsx(path)
    else:
        raise ContactError("Use uma planilha CSV ou Excel .xlsx.")

    summary = ImportSummary()
    seen: set[str] = set()
    target_folder = normalize_folder_name(folder_name) if folder_name.strip() else ""
    for index, row in enumerate(rows, start=2):
        name = _pick(row, {"nome", "name", "cliente", "contato"}) or "Cliente"
        phone = normalize_phone(_pick(row, {"numero", "número", "telefone", "phone", "celular", "whatsapp"}))
        email = _pick(row, {"email", "e_mail"})
        group_name = target_folder or _pick(row, {"grupo", "lista", "group", "group_name", "pasta", "folder"}) or DEFAULT_CONTACT_FOLDER
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


def _is_probable_lead_name(value: str) -> bool:
    text = " ".join(str(value or "").split()).strip(" -|")
    if len(text) < 3:
        return False
    lowered = text.casefold()
    if lowered.startswith(("http://", "https://", "www.")):
        return False
    if any(token in lowered for token in LEAD_NAME_BLOCKLIST):
        return False
    if LEAD_PHONE_RE.search(text):
        return False
    letters = sum(char.isalpha() for char in text)
    digits = sum(char.isdigit() for char in text)
    if letters < 3 or digits > max(2, letters):
        return False
    return True


def _guess_lead_name(lines: list[str], index: int) -> str:
    for offset in range(1, 6):
        previous_index = index - offset
        if previous_index < 0:
            break
        candidate = lines[previous_index].strip()
        if _is_probable_lead_name(candidate):
            return candidate
    return ""


def extract_leads_from_text(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    for index, line in enumerate(lines):
        for raw_phone in LEAD_PHONE_RE.findall(line):
            phone = normalize_phone(raw_phone)
            if not is_valid_phone(phone) or phone in seen:
                continue
            seen.add(phone)
            name = _guess_lead_name(lines, index) or f"Lead {len(found) + 1}"
            found.append(
                {
                    "name": name,
                    "phone": phone,
                    "source": line,
                }
            )

    return found


def import_leads(leads: Iterable[dict[str, object]], folder_name: str = "") -> ImportSummary:
    summary = ImportSummary()
    target_folder = normalize_folder_name(folder_name) if folder_name.strip() else DEFAULT_CONTACT_FOLDER
    seen: set[str] = set()

    for index, lead in enumerate(leads, start=1):
        name = str(lead.get("name") or "").strip() or f"Lead {index}"
        phone = normalize_phone(str(lead.get("phone") or ""))
        if not phone or not is_valid_phone(phone):
            summary.skipped += 1
            summary.errors.append(f"Lead {index}: numero invalido.")
            continue
        if phone in seen:
            summary.duplicates += 1
            continue
        seen.add(phone)

        try:
            _, updated = upsert_contact(
                name=name,
                phone=phone,
                group_name=target_folder,
                opt_in=1,
                opt_in_source="google_maps",
                opt_in_category="marketing",
                consent_notes="Importado da tela Buscar leads.",
            )
        except ContactError as exc:
            summary.skipped += 1
            summary.errors.append(f"Lead {index}: {exc}")
            continue

        if updated:
            summary.updated += 1
        else:
            summary.imported += 1

    return summary
