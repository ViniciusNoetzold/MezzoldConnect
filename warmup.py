from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time
from threading import Event
from typing import Any, Callable

from campaigns import log_message
from contacts import is_valid_phone, normalize_phone
from database import connect, get_setting, now_text, row_to_dict, rows_to_dicts
from whatsapp import WhatsAppAPIError, WhatsAppBusinessClient, load_config


class WarmupError(ValueError):
    pass


ProgressCallback = Callable[[int, int, str], None]


@dataclass
class WarmupTotals:
    sent: int = 0
    simulated: int = 0
    manual: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "sent": self.sent,
            "simulated": self.simulated,
            "manual": self.manual,
            "failed": self.failed,
            "skipped": self.skipped,
        }


MESSAGE_BANK = [
    "Ola {name}, passando para confirmar seu cadastro com a {company}.",
    "Oi {name}, tudo certo? Esta e uma mensagem de verificacao da {company}.",
    "{name}, confirmando por aqui que seu numero esta ativo para receber novidades da {company}.",
    "Bom dia, {name}. A {company} esta validando os contatos autorizados nesta lista.",
    "Ola, {name}. Se quiser parar de receber mensagens, responda SAIR a qualquer momento.",
]

INITIAL_DAILY_TARGET = 20
DEFAULT_MAX_DAILY_TARGET = 500
RAMP_RATE = 0.20
AUTO_PAUSE_SCORE = 40


def add_number(
    display_name: str,
    phone: str,
    phone_number_id: str = "",
    provider: str = "official_api",
    status: str = "testing",
    quality_rating: str = "unknown",
    messaging_limit: int = 250,
    daily_target: int = INITIAL_DAILY_TARGET,
    max_daily_target: int = DEFAULT_MAX_DAILY_TARGET,
    active: bool = True,
    rest_start: str = "00:00",
    rest_end: str = "07:00",
    notes: str = "",
) -> int:
    display_name = display_name.strip() or "Numero WhatsApp"
    phone = normalize_phone(phone)
    if not is_valid_phone(phone):
        raise WarmupError("Telefone inválido. Use DDD e número, com ou sem +55.")
    _validate_time(rest_start, "Inicio do descanso")
    _validate_time(rest_end, "Fim do descanso")
    messaging_limit = max(int(messaging_limit), 1)
    daily_target = _clamp(int(daily_target), INITIAL_DAILY_TARGET, messaging_limit)
    max_daily_target = max(int(max_daily_target), daily_target)
    timestamp = now_text()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO whatsapp_numbers
                (display_name, phone, phone_number_id, provider, status, quality_rating,
                 messaging_limit, daily_target, max_daily_target, active, rest_start,
                 rest_end, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                display_name,
                phone,
                phone_number_id.strip(),
                provider.strip() or "official_api",
                status.strip() or "testing",
                quality_rating.strip() or "unknown",
                messaging_limit,
                daily_target,
                max_daily_target,
                int(bool(active)),
                rest_start.strip(),
                rest_end.strip(),
                notes.strip(),
                timestamp,
                timestamp,
            ),
        )
    return int(cursor.lastrowid)


def update_number(number_id: int, **fields: object) -> None:
    allowed = {
        "display_name",
        "phone",
        "phone_number_id",
        "provider",
        "status",
        "quality_rating",
        "messaging_limit",
        "daily_target",
        "max_daily_target",
        "ready_for_campaigns",
        "active",
        "rest_start",
        "rest_end",
        "notes",
    }
    updates: list[str] = []
    values: list[object] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "phone":
            value = normalize_phone(str(value))
            if not is_valid_phone(str(value)):
                raise WarmupError("Telefone inválido. Use DDD e número, com ou sem +55.")
        elif key in {"messaging_limit", "daily_target", "max_daily_target"}:
            value = max(int(float(str(value).replace(",", "."))), 1)
        elif key in {"active", "ready_for_campaigns"}:
            value = int(bool(value))
        elif key in {"rest_start", "rest_end"}:
            value = str(value).strip()
            _validate_time(value, "Horario de descanso")
        else:
            value = str(value).strip()
        updates.append(f"{key} = ?")
        values.append(value)

    if not updates:
        return
    updates.append("updated_at = ?")
    values.append(now_text())
    values.append(number_id)
    with connect() as conn:
        conn.execute(
            f"UPDATE whatsapp_numbers SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )


def delete_number(number_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM whatsapp_numbers WHERE id = ?", (number_id,))


def get_number(number_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM whatsapp_numbers WHERE id = ?", (number_id,)).fetchone()
    return row_to_dict(row)


def list_numbers() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                n.*,
                COALESCE(today.sent_today, 0) AS sent_today,
                COALESCE(alltime.total_events, 0) AS total_events,
                COALESCE(alltime.failed_events, 0) AS failed_events
            FROM whatsapp_numbers n
            LEFT JOIN (
                SELECT whatsapp_number_id, COUNT(*) AS sent_today
                FROM number_rampup_events
                WHERE status IN ('enviado', 'simulado', 'pendente_manual')
                  AND created_at LIKE date('now', 'localtime') || '%'
                GROUP BY whatsapp_number_id
            ) today ON today.whatsapp_number_id = n.id
            LEFT JOIN (
                SELECT
                    whatsapp_number_id,
                    COUNT(*) AS total_events,
                    SUM(CASE WHEN status = 'falhou' THEN 1 ELSE 0 END) AS failed_events
                FROM number_rampup_events
                GROUP BY whatsapp_number_id
            ) alltime ON alltime.whatsapp_number_id = n.id
            ORDER BY n.display_name COLLATE NOCASE
            """
        ).fetchall()
    numbers = rows_to_dicts(rows)
    for number in numbers:
        number["current_daily_target"] = current_daily_target(number)
        number["health_score"] = calculate_health_score(int(number["id"]))["score"]
    return numbers


def list_recent_events(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                e.*,
                n.display_name AS number_name
            FROM number_rampup_events e
            JOIN whatsapp_numbers n ON n.id = e.whatsapp_number_id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def dashboard_stats() -> dict[str, int]:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS total FROM whatsapp_numbers").fetchone()["total"]
        active = conn.execute("SELECT COUNT(*) AS total FROM whatsapp_numbers WHERE active = 1").fetchone()["total"]
        ready = conn.execute("SELECT COUNT(*) AS total FROM whatsapp_numbers WHERE ready_for_campaigns = 1").fetchone()["total"]
        paused = conn.execute("SELECT COUNT(*) AS total FROM whatsapp_numbers WHERE status = 'paused'").fetchone()["total"]
    return {"total": int(total), "active": int(active), "ready": int(ready), "paused": int(paused)}


def run_number_rampup(
    number_id: int,
    group_name: str = "",
    client: WhatsAppBusinessClient | None = None,
    progress_callback: ProgressCallback | None = None,
    stop_event: Event | None = None,
) -> dict[str, int]:
    number = get_number(number_id)
    if not number:
        raise WarmupError("Não encontrei esse número.")
    if not int(number.get("active") or 0):
        raise WarmupError("Esse número está desativado.")
    if str(number.get("status") or "") in {"paused", "auto_paused"}:
        raise WarmupError("Esse número está pausado. Confira a saúde antes de retomar.")
    if str(number.get("status") or "") in {"banned", "restricted"}:
        raise WarmupError("Esse número está restrito ou banido. Não envie por ele antes de revisar a conta.")
    if _inside_rest_window(str(number.get("rest_start") or "22:00"), str(number.get("rest_end") or "08:00")):
        raise WarmupError("Agora é horário de descanso desse número. Tente novamente depois.")

    daily_target = current_daily_target(number)
    remaining_today = max(daily_target - _sent_today_count(number_id), 0)
    if remaining_today <= 0:
        raise WarmupError("Esse número já atingiu o limite de hoje.")

    contacts = _select_contacts(number_id, remaining_today, group_name)
    if not contacts:
        raise WarmupError("Não há clientes autorizados disponíveis para aquecer esse número.")

    config = load_config()
    if str(number.get("phone_number_id") or "").strip():
        config.phone_number_id = str(number["phone_number_id"]).strip()
    client = client or WhatsAppBusinessClient(config)
    totals = WarmupTotals()
    timestamp = now_text()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO number_rampup_runs
                (whatsapp_number_id, status, group_name, target_contacts, started_at)
            VALUES (?, 'running', ?, ?, ?)
            """,
            (number_id, group_name.strip(), len(contacts), timestamp),
        )
        run_id = int(cursor.lastrowid)

    try:
        for index, contact in enumerate(contacts, start=1):
            if stop_event and stop_event.is_set():
                totals.skipped += len(contacts) - index + 1
                _finish_run(run_id, "paused", totals)
                return totals.as_dict()
            if _inside_rest_window(str(number.get("rest_start") or "22:00"), str(number.get("rest_end") or "08:00")):
                totals.skipped += len(contacts) - index + 1
                _finish_run(run_id, "resting", totals)
                return totals.as_dict()

            message = _build_message(contact)
            status = "falhou"
            error = ""
            provider_id = ""
            action_url = ""
            try:
                result = client.send_campaign_message(
                    contact,
                    {
                        "message": message,
                        "media_path": "",
                        "template_name": config.default_template,
                        "template_language": config.default_language,
                        "message_category": "utility",
                    },
                )
                status = "simulado" if result.dry_run else result.status
                provider_id = result.provider_message_id
                action_url = result.action_url
                if status == "simulado":
                    totals.simulated += 1
                elif status == "pendente_manual":
                    totals.manual += 1
                else:
                    totals.sent += 1
            except (WhatsAppAPIError, OSError, ValueError) as exc:
                error = str(exc)
                totals.failed += 1

            _log_event(run_id, number_id, contact, status, error, provider_id, action_url, message)
            log_message(
                None,
                int(contact["id"]),
                str(contact["phone"]),
                str(contact["name"]),
                status,
                error_message=error,
                provider_message_id=provider_id,
                action_url=action_url,
                message_body=message,
            )
            if progress_callback:
                progress_callback(index, len(contacts), f"{contact['name']}: {status}")
            _sleep_between_messages(index, len(contacts))
    finally:
        refresh_number_health(number_id)

    _finish_run(run_id, "completed", totals)
    return totals.as_dict()


def refresh_number_health(number_id: int) -> dict[str, Any]:
    snapshot = calculate_health_score(number_id)
    with connect() as conn:
        total = int(snapshot["total"])
        success = int(snapshot["successful"])
        score = int(snapshot["score"])
        failure_rate = float(snapshot["failure_rate"])
        if total == 0:
            quality = "unknown"
            ready = 0
            status = "testing"
        elif score < AUTO_PAUSE_SCORE:
            quality = "low"
            ready = 0
            status = "auto_paused"
        elif score < 70:
            quality = "medium"
            ready = 0
            status = "testing"
        else:
            quality = "high"
            ready = 1 if success >= _setting_int("rampup_daily_floor", 5, 1) else 0
            status = "healthy" if ready else "testing"

        conn.execute(
            """
            UPDATE whatsapp_numbers
            SET quality_rating = ?, ready_for_campaigns = ?, status = ?,
                last_health_check_at = ?, updated_at = ?
            WHERE id = ?
              AND status NOT IN ('banned', 'restricted')
            """,
            (quality, ready, status, now_text(), now_text(), number_id),
        )
    return {
        "quality_rating": quality,
        "ready_for_campaigns": ready,
        "failure_rate": failure_rate,
        "score": score,
        "delivery_rate": snapshot["delivery_rate"],
        "response_rate": snapshot["response_rate"],
        "opt_out_rate": snapshot["opt_out_rate"],
    }


def current_daily_target(number: dict[str, Any]) -> int:
    base = max(_safe_int(number.get("daily_target"), INITIAL_DAILY_TARGET), INITIAL_DAILY_TARGET)
    cap = max(_safe_int(number.get("max_daily_target"), DEFAULT_MAX_DAILY_TARGET), base)
    created = _date_from_text(str(number.get("created_at") or ""))
    days = max((date.today() - created).days, 0)
    grown = int(base * ((1 + RAMP_RATE) ** days))
    return min(max(grown, base), cap)


def calculate_health_score(number_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'falhou' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status IN ('enviado', 'simulado', 'pendente_manual') THEN 1 ELSE 0 END) AS successful,
                SUM(CASE WHEN status = 'respondido' THEN 1 ELSE 0 END) AS responded,
                SUM(CASE WHEN status = 'opt_out' THEN 1 ELSE 0 END) AS opt_out
            FROM number_rampup_events
            WHERE whatsapp_number_id = ?
              AND created_at >= datetime('now', '-7 days', 'localtime')
            """,
            (number_id,),
        ).fetchone()

    total = int(row["total"] or 0)
    failed = int(row["failed"] or 0)
    successful = int(row["successful"] or 0)
    responded = int(row["responded"] or 0)
    opt_out = int(row["opt_out"] or 0)
    delivery_rate = successful / total if total else 1.0
    failure_rate = failed / total if total else 0.0
    response_rate = responded / successful if successful else 0.0
    opt_out_rate = opt_out / successful if successful else 0.0
    score = round(
        (delivery_rate * 50)
        + ((1 - failure_rate) * 25)
        + (response_rate * 15)
        + ((1 - opt_out_rate) * 10)
    )
    score = max(0, min(100, score))
    return {
        "total": total,
        "failed": failed,
        "successful": successful,
        "responded": responded,
        "opt_out": opt_out,
        "delivery_rate": delivery_rate,
        "failure_rate": failure_rate,
        "response_rate": response_rate,
        "opt_out_rate": opt_out_rate,
        "score": score,
    }


def _select_contacts(number_id: int, limit: int, group_name: str) -> list[dict[str, Any]]:
    query = """
        SELECT c.*
        FROM contacts c
        WHERE c.opt_in = 1
          AND c.blacklisted = 0
          AND NOT EXISTS (
              SELECT 1
              FROM number_rampup_events e
              WHERE e.whatsapp_number_id = ?
                AND e.contact_id = c.id
                AND e.created_at LIKE date('now', 'localtime') || '%'
          )
    """
    params: list[object] = [number_id]
    if group_name.strip():
        query += " AND c.group_name = ?"
        params.append(group_name.strip())
    query += " ORDER BY RANDOM() LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return rows_to_dicts(rows)


def _log_event(
    run_id: int,
    number_id: int,
    contact: dict[str, Any],
    status: str,
    error: str,
    provider_id: str,
    action_url: str,
    message: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO number_rampup_events
                (run_id, whatsapp_number_id, contact_id, phone, recipient_name, status,
                 error_message, provider_message_id, action_url, message_body, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                number_id,
                int(contact["id"]),
                str(contact["phone"]),
                str(contact["name"]),
                status,
                error,
                provider_id,
                action_url,
                message,
                now_text(),
            ),
        )


def _finish_run(run_id: int, status: str, totals: WarmupTotals) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE number_rampup_runs
            SET status = ?, sent = ?, simulated = ?, manual = ?, failed = ?,
                skipped = ?, finished_at = ?
            WHERE id = ?
            """,
            (
                status,
                totals.sent,
                totals.simulated,
                totals.manual,
                totals.failed,
                totals.skipped,
                now_text(),
                run_id,
            ),
        )


def _build_message(contact: dict[str, Any]) -> str:
    name = str(contact.get("name") or "tudo bem").strip().split()[0]
    company = get_setting("company_name", "Mezzold").strip() or "Mezzold"
    return random.choice(MESSAGE_BANK).format(name=name, company=company)


def _sent_today_count(number_id: int) -> int:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM number_rampup_events
            WHERE whatsapp_number_id = ?
              AND status IN ('enviado', 'simulado', 'pendente_manual')
              AND created_at LIKE date('now', 'localtime') || '%'
            """,
            (number_id,),
        ).fetchone()
    return int(row["total"] or 0)


def _sleep_between_messages(index: int, total: int) -> None:
    if index >= total:
        return
    minimum = _setting_int("rampup_min_interval_seconds", 45, 1)
    maximum = _setting_int("rampup_max_interval_seconds", 180, minimum)
    if maximum < minimum:
        maximum = minimum
    time.sleep(random.uniform(minimum, maximum))


def _inside_rest_window(rest_start: str, rest_end: str) -> bool:
    start = _parse_time(rest_start)
    end = _parse_time(rest_end)
    current = datetime.now().time().replace(second=0, microsecond=0)
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _validate_time(value: str, label: str) -> None:
    try:
        _parse_time(value)
    except ValueError as exc:
        raise WarmupError(f"{label}: use o formato HH:MM, por exemplo 07:00.") from exc


def _parse_time(value: str) -> clock_time:
    return datetime.strptime(value.strip(), "%H:%M").time().replace(second=0, microsecond=0)


def _safe_int(value: object, default: int) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return default


def _date_from_text(value: str) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return date.today()


def _setting_int(key: str, default: int, minimum: int) -> int:
    try:
        value = int(float(get_setting(key, str(default)).replace(",", ".")))
    except ValueError:
        value = default
    return max(value, minimum)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))
