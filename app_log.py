"""Unified structured application log for Mezzold Connect (Etapa 6)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from database import DATA_DIR

LOG_PATH = DATA_DIR / "app.log"


def log(event: str, detail: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {event}" + (f" | {detail}" if detail else "")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def app_started() -> None:
    log("APP_STARTED")


def agent_started() -> None:
    log("AGENT_STARTED")


def app_minimized_to_tray() -> None:
    log("APP_MINIMIZED_TO_TRAY")


def app_restored_from_tray() -> None:
    log("APP_RESTORED_FROM_TRAY")


def app_closed() -> None:
    log("APP_CLOSED")


def campaign_started(campaign_id: int, name: str = "") -> None:
    log("CAMPAIGN_STARTED", f"id={campaign_id} name={name}")


def campaign_paused(campaign_id: int) -> None:
    log("CAMPAIGN_PAUSED", f"id={campaign_id}")


def campaign_resumed(campaign_id: int) -> None:
    log("CAMPAIGN_RESUMED", f"id={campaign_id}")


def campaign_cancelled(campaign_id: int) -> None:
    log("CAMPAIGN_CANCELLED", f"id={campaign_id}")


def campaign_done(campaign_id: int, totals: dict) -> None:
    log("CAMPAIGN_DONE", f"id={campaign_id} totals={totals}")


def chrome_opened() -> None:
    log("CHROME_OPENED")


def whatsapp_connected() -> None:
    log("WHATSAPP_CONNECTED")


def whatsapp_disconnected() -> None:
    log("WHATSAPP_DISCONNECTED")


def whatsapp_qr_needed() -> None:
    log("WHATSAPP_QR_NEEDED")


def message_sent(phone: str, campaign_id: int) -> None:
    log("MESSAGE_SENT", f"phone={phone} campaign_id={campaign_id}")


def message_failed(phone: str, campaign_id: int, error: str = "") -> None:
    log("MESSAGE_FAILED", f"phone={phone} campaign_id={campaign_id} error={error}")
