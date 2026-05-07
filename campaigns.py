from __future__ import annotations

import random
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from threading import Event
from typing import Any, Callable

import compliance
from database import DATA_DIR, connect, now_text, row_to_dict, rows_to_dicts
from database import get_setting
from whatsapp import WhatsAppAPIError, WhatsAppBusinessClient, load_config


class CampaignError(ValueError):
    pass


ProgressCallback = Callable[[int, int, str], None]

SEND_LOG_PATH = DATA_DIR / "send_flow.log"
LOCK_STALE_MINUTES = 120
CAMPAIGN_STATUS_DRAFT = "rascunho"
CAMPAIGN_STATUS_SCHEDULED = "agendada"
CAMPAIGN_STATUS_SENDING = "enviando"
CAMPAIGN_STATUS_PAUSED = "pausada"
CAMPAIGN_STATUS_CANCELLED = "cancelada"
CAMPAIGN_STATUS_DONE = "concluída"
CAMPAIGN_STATUS_DONE_LEGACY = "concluida"
CAMPAIGN_STATUS_MANUAL_PENDING = "aguardando_manual"
CAMPAIGN_STATUS_ERROR = "erro"
CAMPAIGN_STATUS_FAILED = "falhou"
CAMPAIGN_STARTABLE_STATUSES = {CAMPAIGN_STATUS_DRAFT, CAMPAIGN_STATUS_SCHEDULED, CAMPAIGN_STATUS_PAUSED}
CAMPAIGN_TERMINAL_STATUSES = {
    CAMPAIGN_STATUS_CANCELLED,
    CAMPAIGN_STATUS_DONE,
    CAMPAIGN_STATUS_DONE_LEGACY,
    CAMPAIGN_STATUS_ERROR,
    CAMPAIGN_STATUS_FAILED,
    CAMPAIGN_STATUS_MANUAL_PENDING,
}
CONTACT_STATUS_WAITING = "aguardando"
CONTACT_STATUS_SENT = "enviado"
CONTACT_STATUS_BLOCKED = "bloqueado"
CONTACT_STATUS_NO_PERMISSION = "sem_autorizacao"
CONTACT_STATUS_MANUAL_PENDING = "aguardando_manual"
CONTACT_FINAL_STATUSES = {
    CONTACT_STATUS_SENT,
    CONTACT_STATUS_BLOCKED,
    CONTACT_STATUS_NO_PERMISSION,
    CONTACT_STATUS_MANUAL_PENDING,
}


def create_campaign(
    name: str,
    message: str,
    contact_ids: list[int],
    media_path: str = "",
    template_name: str = "",
    template_language: str = "pt_BR",
    message_category: str = "marketing",
    message_variants: list[str] | None = None,
    media_variants: list[str] | None = None,
    scheduled_at: str | None = None,
    folder_name: str = "",
) -> int:
    name = name.strip()
    message = message.strip()
    folder_name = folder_name.strip()
    contact_ids = sorted(set(int(contact_id) for contact_id in contact_ids))
    if not name:
        raise CampaignError("Dê um nome para a campanha.")
    if not message and not template_name.strip():
        raise CampaignError("Escreva a mensagem ou informe o modelo aprovado na Meta.")
    if not contact_ids:
        raise CampaignError("Escolha pelo menos um cliente autorizado.")

    timestamp = now_text()
    status = CAMPAIGN_STATUS_SCHEDULED if scheduled_at else CAMPAIGN_STATUS_DRAFT
    variants = _normalize_variants(message, message_variants or [])
    media_options = [item.strip() for item in (media_variants or []) if item.strip()]
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO campaigns
                (name, message, media_path, template_name, template_language,
                 message_category, folder_name, status, scheduled_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                message,
                media_path.strip(),
                template_name.strip(),
                template_language.strip() or "pt_BR",
                message_category.strip() or "marketing",
                folder_name,
                status,
                scheduled_at,
                timestamp,
                timestamp,
            ),
        )
        campaign_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO campaign_contacts (campaign_id, contact_id, status, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [(campaign_id, contact_id, CONTACT_STATUS_WAITING, timestamp) for contact_id in contact_ids],
        )
        conn.executemany(
            """
            INSERT INTO campaign_variants (campaign_id, body, media_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    campaign_id,
                    variant,
                    media_options[index % len(media_options)] if media_options else media_path.strip(),
                    timestamp,
                )
                for index, variant in enumerate(variants)
            ],
        )
    compliance.refresh_campaign_risk(campaign_id)
    return campaign_id


def _normalize_variants(primary_message: str, message_variants: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in [primary_message, *message_variants]:
        item = raw.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result or [primary_message.strip()]


def get_campaign_variants(campaign_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT body, media_path
            FROM campaign_variants
            WHERE campaign_id = ?
            ORDER BY id
            """,
            (campaign_id,),
        ).fetchall()
    variants = rows_to_dicts(rows)
    if variants:
        return variants

    campaign = get_campaign(campaign_id)
    if not campaign:
        return []
    return [{"body": campaign.get("message") or "", "media_path": campaign.get("media_path") or ""}]


def list_campaigns() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.*,
                COUNT(cc.contact_id) AS total_contacts,
                SUM(CASE WHEN cc.status = 'enviado' THEN 1 ELSE 0 END) AS sent_contacts,
                SUM(CASE WHEN cc.status = 'falhou' THEN 1 ELSE 0 END) AS failed_contacts
            FROM campaigns c
            LEFT JOIN campaign_contacts cc ON cc.campaign_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def has_pending_contacts(campaign_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM campaign_contacts
            WHERE campaign_id = ?
              AND status NOT IN (?, ?, ?, ?)
            """,
            (
                campaign_id,
                CONTACT_STATUS_SENT,
                CONTACT_STATUS_BLOCKED,
                CONTACT_STATUS_NO_PERMISSION,
                CONTACT_STATUS_MANUAL_PENDING,
            ),
        ).fetchone()
    return int(row["total"]) > 0


def get_campaign(campaign_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    return row_to_dict(row)


def get_campaign_contacts(campaign_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                cc.status AS campaign_status,
                cc.last_error,
                contacts.*
            FROM campaign_contacts cc
            JOIN contacts ON contacts.id = cc.contact_id
            WHERE cc.campaign_id = ?
            ORDER BY contacts.name COLLATE NOCASE
            """,
            (campaign_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def schedule_campaign(campaign_id: int, scheduled_at: str) -> None:
    if not scheduled_at.strip():
        raise CampaignError("Informe a data e o horário do envio.")
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise CampaignError("Não encontrei essa campanha.")
    status = str(campaign.get("status") or "")
    if status in CAMPAIGN_TERMINAL_STATUSES or status == CAMPAIGN_STATUS_SENDING:
        raise CampaignError(f"Campanha com status '{status}' não pode ser agendada novamente.")
    with connect() as conn:
        conn.execute(
            """
            UPDATE campaigns
            SET status = ?, scheduled_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (CAMPAIGN_STATUS_SCHEDULED, scheduled_at.strip(), now_text(), campaign_id),
        )


def pause_campaign(campaign_id: int) -> None:
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise CampaignError("Não encontrei essa campanha.")
    status = str(campaign.get("status") or "")
    if status in CAMPAIGN_TERMINAL_STATUSES:
        raise CampaignError(f"Campanha com status '{status}' não pode ser pausada.")
    _set_campaign_status(campaign_id, CAMPAIGN_STATUS_PAUSED)


def cancel_campaign(campaign_id: int) -> None:
    _set_campaign_status(campaign_id, CAMPAIGN_STATUS_CANCELLED)


def mark_draft(campaign_id: int) -> None:
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise CampaignError("Não encontrei essa campanha.")
    status = str(campaign.get("status") or "")
    if status in CAMPAIGN_TERMINAL_STATUSES or status == CAMPAIGN_STATUS_SENDING:
        raise CampaignError(f"Campanha com status '{status}' não pode voltar para rascunho.")
    _set_campaign_status(campaign_id, CAMPAIGN_STATUS_DRAFT)


def _set_campaign_status(campaign_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE campaigns SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_text(), campaign_id),
        )


def get_due_campaigns() -> list[dict[str, Any]]:
    current = now_text()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM campaigns
            WHERE status = ?
              AND scheduled_at IS NOT NULL
              AND scheduled_at <= ?
            ORDER BY scheduled_at
            """,
            (CAMPAIGN_STATUS_SCHEDULED, current),
        ).fetchall()
    return rows_to_dicts(rows)


def get_resumable_campaigns() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM campaigns
            WHERE status = ?
            ORDER BY updated_at
            """,
            (CAMPAIGN_STATUS_SENDING,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_logs(limit: int = 300) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                message_logs.*,
                campaigns.name AS campaign_name
            FROM message_logs
            LEFT JOIN campaigns ON campaigns.id = message_logs.campaign_id
            ORDER BY message_logs.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_sent_numbers(limit: int = 1000) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                phone,
                recipient_name,
                message_logs.status AS status,
                campaigns.name AS campaign_name,
                MAX(message_logs.created_at) AS last_sent_at,
                COUNT(*) AS attempts
            FROM message_logs
            LEFT JOIN campaigns ON campaigns.id = message_logs.campaign_id
            WHERE message_logs.status IN ('enviado', 'simulado', 'pendente_manual')
            GROUP BY phone, recipient_name, message_logs.status, campaigns.name
            ORDER BY last_sent_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def dashboard_stats() -> dict[str, int]:
    with connect() as conn:
        contacts = conn.execute("SELECT COUNT(*) AS total FROM contacts").fetchone()["total"]
        opt_in = conn.execute("SELECT COUNT(*) AS total FROM contacts WHERE opt_in = 1").fetchone()["total"]
        blocked = conn.execute("SELECT COUNT(*) AS total FROM contacts WHERE blacklisted = 1").fetchone()["total"]
        campaigns = conn.execute("SELECT COUNT(*) AS total FROM campaigns").fetchone()["total"]
        scheduled = conn.execute("SELECT COUNT(*) AS total FROM campaigns WHERE status = 'agendada'").fetchone()["total"]
        sent = conn.execute("SELECT COUNT(*) AS total FROM message_logs WHERE status IN ('enviado', 'simulado')").fetchone()["total"]
        failed = conn.execute("SELECT COUNT(*) AS total FROM message_logs WHERE status = 'falhou'").fetchone()["total"]
    return {
        "contacts": int(contacts),
        "opt_in": int(opt_in),
        "blocked": int(blocked),
        "campaigns": int(campaigns),
        "scheduled": int(scheduled),
        "sent": int(sent),
        "failed": int(failed),
    }


def log_message(
    campaign_id: int | None,
    contact_id: int | None,
    phone: str,
    recipient_name: str,
    status: str,
    error_message: str = "",
    provider_message_id: str = "",
    action_url: str = "",
    message_body: str = "",
    media_path: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO message_logs
                (campaign_id, contact_id, phone, recipient_name, status,
                 error_message, provider_message_id, action_url, message_body, media_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                contact_id,
                phone,
                recipient_name,
                status,
                error_message,
                provider_message_id,
                action_url,
                message_body,
                media_path,
                now_text(),
            ),
        )


def _sent_today_count() -> int:
    today = now_text()[:10]
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM message_logs
            WHERE status IN ('enviado', 'simulado', 'pendente_manual')
              AND created_at LIKE ?
            """,
            (today + "%",),
        ).fetchone()
    return int(row["total"])


def smart_send_enabled() -> bool:
    return get_setting("smart_send_enabled", "0") == "1"


def _setting_int(key: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(float(get_setting(key, str(default)).replace(",", ".")))
    except ValueError:
        value = default
    return max(value, minimum)


def _smart_daily_limit(config_daily_limit: int) -> int:
    if not smart_send_enabled():
        return config_daily_limit
    smart_limit = _setting_int("smart_daily_limit", 100, 1)
    return min(config_daily_limit, smart_limit)


def _smart_session_deadline() -> datetime | None:
    if not smart_send_enabled():
        return None
    minutes = _setting_int("smart_max_session_minutes", 90, 5)
    return datetime.now() + timedelta(minutes=minutes)


def _sleep_between_sends(counter: int, total: int, config_interval: float) -> None:
    if counter >= total:
        return
    if not smart_send_enabled():
        time.sleep(max(config_interval, 0.5))
        return

    minimum = _setting_int("smart_min_interval_seconds", 30, 1)
    maximum = _setting_int("smart_max_interval_seconds", 45, minimum)
    if maximum < minimum:
        maximum = minimum
    delay = random.uniform(minimum, maximum)
    time.sleep(delay)

    pause_every = _setting_int("smart_pause_every", 10, 1)
    if pause_every and counter % pause_every == 0:
        pause_min = _setting_int("smart_pause_min_seconds", 120, 0)
        pause_max = _setting_int("smart_pause_max_seconds", 300, pause_min)
        if pause_max < pause_min:
            pause_max = pause_min
        time.sleep(random.uniform(pause_min, pause_max))


def _send_log(message: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="seconds")
        with SEND_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def _preview(value: object, limit: int = 600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _pending_contact_count(conn, campaign_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM campaign_contacts
        WHERE campaign_id = ?
          AND status NOT IN (?, ?, ?, ?)
        """,
        (
            campaign_id,
            CONTACT_STATUS_SENT,
            CONTACT_STATUS_BLOCKED,
            CONTACT_STATUS_NO_PERMISSION,
            CONTACT_STATUS_MANUAL_PENDING,
        ),
    ).fetchone()
    return int(row["total"] or 0)


def _start_block_reason(campaign: dict[str, Any], pending_contacts: int, allow_resume: bool) -> str:
    status = str(campaign.get("status") or "").strip()
    if status in CAMPAIGN_TERMINAL_STATUSES:
        return f"Campanha com status '{status}' não pode ser reiniciada."
    if status == CAMPAIGN_STATUS_SENDING:
        if allow_resume and pending_contacts > 0:
            return ""
        return "Campanha já está em andamento."
    if status not in CAMPAIGN_STARTABLE_STATUSES:
        return f"Campanha com status '{status}' não está liberada para início."
    if pending_contacts <= 0:
        return "Campanha não tem contatos pendentes para envio."
    return ""


def can_start_campaign(campaign_id: int, allow_resume: bool = False) -> tuple[bool, str]:
    with connect() as conn:
        conn.execute(
            "DELETE FROM campaign_send_locks WHERE locked_at <= ?",
            ((datetime.now() - timedelta(minutes=LOCK_STALE_MINUTES)).isoformat(timespec="seconds"),),
        )
        campaign = row_to_dict(conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone())
        if not campaign:
            return False, "Não encontrei essa campanha."
        lock = conn.execute(
            "SELECT owner, locked_at FROM campaign_send_locks WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if lock:
            return False, f"Campanha já está em envio por {lock['owner']} desde {lock['locked_at']}."
        reason = _start_block_reason(campaign, _pending_contact_count(conn, campaign_id), allow_resume)
        if reason:
            return False, reason
    return True, ""


def _acquire_campaign_lock(campaign_id: int, runner: str, allow_resume: bool) -> str:
    owner = f"{runner}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    stale_before = (datetime.now() - timedelta(minutes=LOCK_STALE_MINUTES)).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            "DELETE FROM campaign_send_locks WHERE campaign_id = ? AND locked_at <= ?",
            (campaign_id, stale_before),
        )
        campaign = row_to_dict(conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone())
        if not campaign:
            raise CampaignError("Não encontrei essa campanha.")
        reason = _start_block_reason(campaign, _pending_contact_count(conn, campaign_id), allow_resume)
        if reason:
            _send_log(f"BLOCK campaign_id={campaign_id} runner={runner} reason={_preview(reason)}")
            raise CampaignError(reason)
        try:
            conn.execute(
                """
                INSERT INTO campaign_send_locks (campaign_id, owner, locked_at)
                VALUES (?, ?, ?)
                """,
                (campaign_id, owner, now_text()),
            )
        except sqlite3.IntegrityError as exc:
            row = conn.execute(
                "SELECT owner, locked_at FROM campaign_send_locks WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            current_owner = row["owner"] if row else "outro processo"
            locked_at = row["locked_at"] if row else ""
            _send_log(
                f"BLOCK campaign_id={campaign_id} runner={runner} "
                f"reason=locked owner={current_owner} locked_at={locked_at}"
            )
            raise CampaignError(
                f"Esta campanha ja esta em envio por {current_owner} desde {locked_at}."
            ) from exc
    _send_log(f"LOCK campaign_id={campaign_id} owner={owner}")
    return owner


def _release_campaign_lock(campaign_id: int, owner: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM campaign_send_locks WHERE campaign_id = ? AND owner = ?",
            (campaign_id, owner),
        )
    _send_log(f"UNLOCK campaign_id={campaign_id} owner={owner}")


def _campaign_contact_status_counts(campaign_id: int) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM campaign_contacts
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
    return {str(row["status"]): int(row["total"]) for row in rows}


def _final_status_for_campaign(campaign_id: int, stopped: bool) -> str:
    if stopped:
        return CAMPAIGN_STATUS_PAUSED
    counts = _campaign_contact_status_counts(campaign_id)
    if counts.get(CONTACT_STATUS_WAITING, 0) > 0:
        return CAMPAIGN_STATUS_PAUSED
    if counts.get(CONTACT_STATUS_MANUAL_PENDING, 0) > 0:
        return CAMPAIGN_STATUS_MANUAL_PENDING
    return CAMPAIGN_STATUS_DONE


def send_campaign(
    campaign_id: int,
    client: WhatsAppBusinessClient | None = None,
    progress_callback: ProgressCallback | None = None,
    stop_event: Event | None = None,
    runner: str = "desktop",
    allow_resume: bool = False,
) -> dict[str, int]:
    lock_owner = _acquire_campaign_lock(campaign_id, runner, allow_resume)
    try:
        return _send_campaign_locked(
            campaign_id,
            client=client,
            progress_callback=progress_callback,
            stop_event=stop_event,
            runner=runner,
        )
    except Exception as exc:
        _send_log(f"ABORT campaign_id={campaign_id} owner={lock_owner} error={_preview(exc)}")
        raise
    finally:
        _release_campaign_lock(campaign_id, lock_owner)


def _send_campaign_locked(
    campaign_id: int,
    client: WhatsAppBusinessClient | None = None,
    progress_callback: ProgressCallback | None = None,
    stop_event: Event | None = None,
    runner: str = "desktop",
) -> dict[str, int]:
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise CampaignError("Não encontrei essa campanha.")
    if str(campaign["status"]) in CAMPAIGN_TERMINAL_STATUSES:
        raise CampaignError(f"Campanha com status '{campaign['status']}' não pode ser enviada.")

    risk = compliance.refresh_campaign_risk(campaign_id)
    if get_setting("block_high_risk_campaigns", "1") == "1" and int(risk["score"]) >= 75:
        raise CampaignError(
            f"Campanha bloqueada por risco alto: {risk['score']}% ({risk['level']}). "
            "Revise autorizações, contatos bloqueados, mensagem e quantidade antes de enviar."
        )

    config = load_config()
    client = client or WhatsAppBusinessClient(config)
    contacts = get_campaign_contacts(campaign_id)
    if not contacts:
        raise CampaignError("Essa campanha não tem clientes selecionados.")

    variants = get_campaign_variants(campaign_id)
    if smart_send_enabled() and len({str(item.get("body") or "").strip() for item in variants if item.get("body")}) < 3:
        raise CampaignError("Para usar pausas automáticas, cadastre pelo menos 3 versões de mensagem.")

    totals = {
        "enviado": 0,
        "simulado": 0,
        "pendente_manual": 0,
        "falhou": 0,
        "bloqueado": 0,
        "sem_autorizacao": 0,
    }
    _set_campaign_status(campaign_id, CAMPAIGN_STATUS_SENDING)
    total = len(contacts)
    session_deadline = _smart_session_deadline()
    sender_number = config.phone_number_id or "nao_configurado"
    _send_log(
        "START "
        f"campaign_id={campaign_id} campaign={_preview(campaign.get('name'))} runner={runner} "
        f"contacts={total} mode={config.delivery_mode} dry_run={config.dry_run} "
        f"sender_number_id={sender_number} template={_preview(campaign.get('template_name') or config.default_template)} "
        f"risk={risk['score']}%"
    )

    for index, contact in enumerate(contacts, start=1):
        if stop_event and stop_event.is_set():
            _set_campaign_status(campaign_id, CAMPAIGN_STATUS_PAUSED)
            _send_log(f"STOP_REQUEST campaign_id={campaign_id} at={index}/{total}")
            break

        contact_id = int(contact["id"])
        phone = str(contact["phone"])
        name = str(contact["name"])
        previous_status = str(contact.get("campaign_status") or "")
        if previous_status in CONTACT_FINAL_STATUSES:
            _send_log(
                f"SKIP campaign_id={campaign_id} contact_id={contact_id} phone={phone} "
                f"reason=already_final previous_status={previous_status}"
            )
            continue

        if int(contact.get("blacklisted") or 0):
            _update_campaign_contact(campaign_id, contact_id, "bloqueado", "Contato na blacklist.")
            log_message(campaign_id, contact_id, phone, name, "bloqueado", "Contato na blacklist.")
            totals["bloqueado"] += 1
            _send_log(f"SKIP campaign_id={campaign_id} contact_id={contact_id} phone={phone} reason=blacklisted")
            continue

        if not int(contact.get("opt_in") or 0):
            _update_campaign_contact(campaign_id, contact_id, "sem_autorizacao", "Contato sem opt-in.")
            log_message(campaign_id, contact_id, phone, name, "sem_autorizacao", "Contato sem opt-in.")
            totals["sem_autorizacao"] += 1
            _send_log(f"SKIP campaign_id={campaign_id} contact_id={contact_id} phone={phone} reason=no_opt_in")
            continue

        if session_deadline and datetime.now() >= session_deadline:
            _set_campaign_status(campaign_id, CAMPAIGN_STATUS_PAUSED)
            message = "Janela máxima de envio inteligente atingida."
            _send_log(f"PAUSE campaign_id={campaign_id} reason=smart_session_deadline")
            if progress_callback:
                progress_callback(index, total, message)
            break

        if _sent_today_count() >= _smart_daily_limit(config.daily_send_limit):
            _set_campaign_status(campaign_id, CAMPAIGN_STATUS_PAUSED)
            message = "Limite diário de envio atingido."
            _send_log(f"PAUSE campaign_id={campaign_id} reason=daily_limit")
            if progress_callback:
                progress_callback(index, total, message)
            break

        try:
            variant = random.choice(variants) if variants else {"body": campaign["message"], "media_path": campaign["media_path"]}
            campaign_for_send = dict(campaign)
            campaign_for_send["message"] = str(variant.get("body") or campaign["message"])
            campaign_for_send["media_path"] = str(variant.get("media_path") or campaign["media_path"] or "")
            _send_log(
                "CONTACT "
                f"campaign_id={campaign_id} index={index}/{total} contact_id={contact_id} "
                f"name={_preview(name, 120)} phone={phone} sender_number_id={sender_number} "
                f"mode={config.delivery_mode} dry_run={config.dry_run} "
                f"message={_preview(campaign_for_send['message'])}"
            )
            result = client.send_campaign_message(contact, campaign_for_send)
            status = "simulado" if result.dry_run else result.status
            contact_status = CONTACT_STATUS_MANUAL_PENDING if status == "pendente_manual" else CONTACT_STATUS_SENT
            _update_campaign_contact(campaign_id, contact_id, contact_status, "")
            log_message(
                campaign_id,
                contact_id,
                phone,
                name,
                status,
                provider_message_id=result.provider_message_id,
                action_url=result.action_url,
                message_body=campaign_for_send["message"],
                media_path=campaign_for_send["media_path"],
            )
            totals[status] += 1
            _send_log(
                "SUCCESS "
                f"campaign_id={campaign_id} contact_id={contact_id} phone={phone} "
                f"status={status} contact_status={contact_status} mode={result.delivery_mode or config.delivery_mode} "
                f"provider_message_id={result.provider_message_id or '-'} "
                f"manual_link={'yes' if result.action_url else 'no'}"
            )
            message = f"{name}: {status}"
        except (WhatsAppAPIError, OSError, ValueError) as exc:
            error = str(exc)
            _update_campaign_contact(campaign_id, contact_id, "falhou", error)
            log_message(campaign_id, contact_id, phone, name, "falhou", error)
            totals["falhou"] += 1
            _send_log(
                f"ERROR campaign_id={campaign_id} contact_id={contact_id} phone={phone} "
                f"mode={config.delivery_mode} error={_preview(error)}"
            )
            message = f"{name}: falhou - {error}"

        if progress_callback:
            progress_callback(index, total, message)

        _sleep_between_sends(index, total, config.send_interval_seconds)

    final_status = _final_status_for_campaign(campaign_id, bool(stop_event and stop_event.is_set()))
    current = get_campaign(campaign_id)
    if current and current["status"] == CAMPAIGN_STATUS_SENDING:
        _set_campaign_status(campaign_id, final_status)
    _send_log(f"FINAL campaign_id={campaign_id} status={final_status} totals={totals}")
    return totals


def _update_campaign_contact(campaign_id: int, contact_id: int, status: str, error: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE campaign_contacts
            SET status = ?, last_error = ?, updated_at = ?
            WHERE campaign_id = ? AND contact_id = ?
            """,
            (status, error, now_text(), campaign_id, contact_id),
        )
