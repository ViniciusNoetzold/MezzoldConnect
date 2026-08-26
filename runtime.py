"""Process runtime shared by every Flet view.

Campaign and warmup jobs must survive route changes.  Keeping their stop events
inside an individual screen made Cancel/Pause unreliable as soon as the user
navigated away, so the desktop process owns them here instead.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import app_log
import campaigns
import warmup
import whatsapp


ProgressCallback = Callable[[int, int, str], None]
CompletionCallback = Callable[[dict[str, int] | None, Exception | None], None]


def requires_real_web_confirmation(campaign: dict[str, Any]) -> bool:
    config = whatsapp.load_config()
    mode = whatsapp.normalize_delivery_mode(
        campaign.get("delivery_mode") or config.delivery_mode
    )
    return (
        mode == whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL
        and not bool(config.dry_run)
    )


class AppRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._campaign_events: dict[int, threading.Event] = {}
        self._warmup_events: dict[int, threading.Event] = {}

    def campaign_is_running(self, campaign_id: int) -> bool:
        with self._lock:
            return int(campaign_id) in self._campaign_events

    def warmup_is_running(self, number_id: int) -> bool:
        with self._lock:
            return int(number_id) in self._warmup_events

    def start_campaign(
        self,
        campaign_id: int,
        *,
        allow_resume: bool = False,
        explicit_user_confirmation: bool = False,
        runner: str = "ui",
        progress_callback: ProgressCallback | None = None,
        completion_callback: CompletionCallback | None = None,
    ) -> bool:
        campaign_id = int(campaign_id)
        with self._lock:
            if campaign_id in self._campaign_events:
                return False
            stop_event = threading.Event()
            self._campaign_events[campaign_id] = stop_event

        def worker() -> None:
            totals: dict[str, int] | None = None
            error: Exception | None = None
            try:
                campaign = campaigns.get_campaign(campaign_id) or {}
                app_log.campaign_started(campaign_id, str(campaign.get("name") or ""))
                if allow_resume:
                    app_log.campaign_resumed(campaign_id)
                totals = campaigns.send_campaign(
                    campaign_id,
                    progress_callback=progress_callback,
                    stop_event=stop_event,
                    runner=runner,
                    allow_resume=allow_resume,
                    explicit_user_confirmation=explicit_user_confirmation,
                )
                app_log.campaign_done(campaign_id, totals)
            except Exception as exc:  # surfaced to the screen callback
                error = exc
                app_log.log("CAMPAIGN_ERROR", f"id={campaign_id} error={exc}")
            finally:
                with self._lock:
                    self._campaign_events.pop(campaign_id, None)
                if completion_callback:
                    try:
                        completion_callback(totals, error)
                    except Exception as callback_error:
                        app_log.log("UI_CALLBACK_ERROR", repr(callback_error))

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"campaign-{campaign_id}",
        ).start()
        return True

    def pause_campaign(self, campaign_id: int) -> None:
        campaign_id = int(campaign_id)
        with self._lock:
            event = self._campaign_events.get(campaign_id)
            if event:
                event.set()
        campaigns.pause_campaign(campaign_id)
        app_log.campaign_paused(campaign_id)

    def cancel_campaign(self, campaign_id: int) -> None:
        campaign_id = int(campaign_id)
        with self._lock:
            event = self._campaign_events.get(campaign_id)
            if event:
                event.set()
        campaigns.cancel_campaign(campaign_id)
        app_log.campaign_cancelled(campaign_id)

    def pause_all_campaigns(self) -> int:
        with self._lock:
            campaign_ids = list(self._campaign_events)
        for campaign_id in campaign_ids:
            try:
                self.pause_campaign(campaign_id)
            except Exception as exc:
                app_log.log("CAMPAIGN_PAUSE_ERROR", f"id={campaign_id} error={exc}")
        return len(campaign_ids)

    def resume_pending_campaigns(self) -> int:
        candidates: dict[int, dict[str, Any]] = {}
        paused = [
            item
            for item in campaigns.list_campaigns()
            if str(item.get("status") or "").strip().lower()
            == campaigns.CAMPAIGN_STATUS_PAUSED
        ]
        for item in [*campaigns.get_resumable_campaigns(), *campaigns.get_due_campaigns(), *paused]:
            campaign_id = int(item["id"])
            if campaigns.has_pending_contacts(campaign_id):
                candidates[campaign_id] = item

        started = 0
        for campaign_id, item in candidates.items():
            if requires_real_web_confirmation(item):
                app_log.log(
                    "CAMPAIGN_AUTO_RESUME_SKIPPED",
                    f"id={campaign_id} reason=whatsapp_web_confirmation_required",
                )
                continue
            status = str(item.get("status") or "").strip().lower()
            allow_resume = status in {
                campaigns.CAMPAIGN_STATUS_PAUSED,
                campaigns.CAMPAIGN_STATUS_SENDING,
            }
            if self.start_campaign(
                campaign_id,
                allow_resume=allow_resume,
                runner="runtime_resume",
            ):
                started += 1
        return started

    def start_warmup(
        self,
        number_id: int,
        group_name: str,
        *,
        progress_callback: ProgressCallback | None = None,
        completion_callback: CompletionCallback | None = None,
        explicit_user_confirmation: bool = False,
    ) -> bool:
        number_id = int(number_id)
        with self._lock:
            if number_id in self._warmup_events:
                return False
            stop_event = threading.Event()
            self._warmup_events[number_id] = stop_event

        def worker() -> None:
            totals: dict[str, int] | None = None
            error: Exception | None = None
            try:
                kwargs: dict[str, Any] = {
                    "group_name": group_name,
                    "progress_callback": progress_callback,
                    "stop_event": stop_event,
                }
                # Newer backend accepts the same explicit confirmation used by
                # real WhatsApp Web campaigns; older compatible versions do not.
                if "explicit_user_confirmation" in warmup.run_number_rampup.__code__.co_varnames:
                    kwargs["explicit_user_confirmation"] = explicit_user_confirmation
                totals = warmup.run_number_rampup(number_id, **kwargs)
            except Exception as exc:
                error = exc
                app_log.log("WARMUP_ERROR", f"id={number_id} error={exc}")
            finally:
                with self._lock:
                    self._warmup_events.pop(number_id, None)
                if completion_callback:
                    try:
                        completion_callback(totals, error)
                    except Exception as callback_error:
                        app_log.log("UI_CALLBACK_ERROR", repr(callback_error))

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"warmup-{number_id}",
        ).start()
        return True

    def stop_warmup(self, number_id: int) -> bool:
        with self._lock:
            event = self._warmup_events.get(int(number_id))
            if not event:
                return False
            event.set()
            return True


app_runtime = AppRuntime()
