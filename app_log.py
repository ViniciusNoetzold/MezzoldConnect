"""Registro unificado de eventos do aplicativo desktop."""
from __future__ import annotations

from datetime import datetime

from database import DATA_DIR


LOG_PATH = DATA_DIR / "app.log"


def log(event: str, detail: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"[{timestamp}] {event}" + (f" | {detail}" if detail else "")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        # Logging must never prevent the application from opening or closing.
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


def campaign_done(campaign_id: int, totals: dict[str, int]) -> None:
    log("CAMPAIGN_DONE", f"id={campaign_id} totals={totals}")


def message_sent(phone: str, campaign_id: int) -> None:
    log("MESSAGE_SENT", f"phone={phone} campaign_id={campaign_id}")


def message_failed(phone: str, campaign_id: int, error: str = "") -> None:
    log("MESSAGE_FAILED", f"phone={phone} campaign_id={campaign_id} error={error}")
