from __future__ import annotations

import socket
import traceback
from threading import Event

import campaigns
import network
from database import initialize_database
from logger import setup_logger
from whatsapp import (
    DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
    load_config,
    normalize_delivery_mode,
)


LOCK_PORT = 38741
logger = setup_logger("background_worker", "background_worker.log")


def _log(message: str) -> None:
    logger.info(message)


def _acquire_single_instance_lock() -> socket.socket | None:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
        lock.listen(1)
        return lock
    except OSError:
        lock.close()
        return None


def _progress(campaign_id: int):
    def callback(index: int, total: int, message: str) -> None:
        _log(f"Campanha {campaign_id}: {index}/{total} - {message}")

    return callback


def _run_pending_campaigns(stop_event: Event | None = None) -> None:
    if not network.has_internet():
        _log("Sem internet. Vou tentar de novo na proxima verificacao.")
        return

    resumable = [
        item
        for item in campaigns.get_resumable_campaigns()
        if campaigns.has_pending_contacts(int(item["id"]))
    ]
    due = campaigns.get_due_campaigns()
    to_run: dict[int, tuple[dict, bool]] = {}

    for campaign in resumable + due:
        campaign_id = int(campaign["id"])
        allow_resume = str(campaign.get("status") or "") == campaigns.CAMPAIGN_STATUS_SENDING
        to_run[campaign_id] = (campaign, allow_resume)

    if not to_run:
        return

    for campaign_id, (_campaign, allow_resume) in to_run.items():
        if stop_event and stop_event.is_set():
            return
        config = load_config()
        mode = normalize_delivery_mode(_campaign.get("delivery_mode") or config.delivery_mode)
        if mode == DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL and not config.dry_run:
            _log(
                f"Campanha {campaign_id} ignorada: WhatsApp Web real exige confirmacao "
                "explicita na interface e nao pode ser iniciado pelo worker."
            )
            continue
        _log(f"Iniciando envio da campanha {campaign_id}.")
        try:
            can_start, reason = campaigns.can_start_campaign(campaign_id, allow_resume=allow_resume)
            if not can_start:
                _log(f"Campanha {campaign_id} ignorada: {reason}")
                continue
            totals = campaigns.send_campaign(
                campaign_id,
                progress_callback=_progress(campaign_id),
                stop_event=stop_event,
                runner="background_worker",
                allow_resume=allow_resume,
            )
            _log(f"Campanha {campaign_id} concluida: {totals}.")
        except Exception as exc:
            _log(f"Erro na campanha {campaign_id}: {exc}")
            _log(traceback.format_exc())


def run_background_worker(poll_seconds: int = 60, stop_event: Event | None = None) -> None:
    initialize_database()
    lock = _acquire_single_instance_lock()
    if lock is None:
        _log("Worker ja esta em execucao. Encerrando esta instancia.")
        return

    _log("Envios em segundo plano iniciados.")
    try:
        import app_log as _app_log

        _app_log.app_started()
        _app_log.agent_started()
    except Exception:
        pass
    try:
        while not (stop_event and stop_event.is_set()):
            try:
                _run_pending_campaigns(stop_event=stop_event)
            except Exception as exc:
                _log(f"Erro na verificacao de envios: {exc}")
                _log(traceback.format_exc())
            delay = max(poll_seconds, 5)
            if stop_event:
                if stop_event.wait(delay):
                    break
            else:
                Event().wait(delay)
    finally:
        lock.close()
        _log("Envios em segundo plano encerrados.")
        try:
            import app_log as _app_log

            _app_log.app_closed()
        except Exception:
            pass
