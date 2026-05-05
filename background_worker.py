from __future__ import annotations

import socket
import time
import traceback
from datetime import datetime
from pathlib import Path

import campaigns
import network
from database import DATA_DIR, initialize_database


LOCK_PORT = 38741
LOG_PATH = DATA_DIR / "background_worker.log"


def _log(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")


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


def _run_pending_campaigns() -> None:
    if not network.has_internet():
        _log("Sem internet. Vou tentar de novo na proxima verificacao.")
        return

    resumable = [
        item
        for item in campaigns.get_resumable_campaigns()
        if campaigns.has_pending_contacts(int(item["id"]))
    ]
    due = campaigns.get_due_campaigns()
    to_run: dict[int, dict] = {}

    for campaign in resumable + due:
        to_run[int(campaign["id"])] = campaign

    if not to_run:
        return

    for campaign_id in to_run:
        _log(f"Iniciando envio da campanha {campaign_id}.")
        try:
            totals = campaigns.send_campaign(campaign_id, progress_callback=_progress(campaign_id))
            _log(f"Campanha {campaign_id} concluida: {totals}.")
        except Exception as exc:
            _log(f"Erro na campanha {campaign_id}: {exc}")
            _log(traceback.format_exc())


def run_background_worker(poll_seconds: int = 60) -> None:
    initialize_database()
    lock = _acquire_single_instance_lock()
    if lock is None:
        _log("Worker ja esta em execucao. Encerrando esta instancia.")
        return

    _log("Envios em segundo plano iniciados.")
    try:
        while True:
            try:
                _run_pending_campaigns()
            except Exception as exc:
                _log(f"Erro na verificacao de envios: {exc}")
                _log(traceback.format_exc())
            time.sleep(max(poll_seconds, 5))
    finally:
        lock.close()
        _log("Envios em segundo plano encerrados.")
