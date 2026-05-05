from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from contacts import normalize_phone
from database import get_setting, set_settings


class WhatsAppAPIError(RuntimeError):
    pass


@dataclass
class WhatsAppConfig:
    api_version: str = "v24.0"
    token: str = ""
    phone_number_id: str = ""
    business_account_id: str = ""
    webhook_url: str = ""
    default_template: str = ""
    default_language: str = "pt_BR"
    delivery_mode: str = "official_api"
    dry_run: bool = True
    send_interval_seconds: float = 2.0
    daily_send_limit: int = 500


@dataclass
class SendResult:
    status: str
    provider_message_id: str = ""
    error_message: str = ""
    action_url: str = ""
    dry_run: bool = False


def _dpapi_blob(data: bytes):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return DATA_BLOB, blob, buffer


def _protect_secret(secret: str) -> str:
    if not secret:
        return ""
    if os.name != "nt":
        raise WhatsAppAPIError("Não consegui salvar o token com segurança neste Windows.")

    import ctypes

    DATA_BLOB, blob_in, _buffer = _dpapi_blob(secret.encode("utf-8"))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        protected = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return "dpapi:" + base64.b64encode(protected).decode("ascii")


def _unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("dpapi:"):
        return ""
    if os.name != "nt":
        return ""

    import ctypes

    protected = base64.b64decode(value.removeprefix("dpapi:"))
    DATA_BLOB, blob_in, _buffer = _dpapi_blob(protected)
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        return ""
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def load_config() -> WhatsAppConfig:
    token = os.environ.get("MEZZOLD_WHATSAPP_TOKEN", "").strip()
    if not token:
        token = _unprotect_secret(get_setting("whatsapp_token_protected", ""))

    return WhatsAppConfig(
        api_version=get_setting("whatsapp_api_version", "v24.0").strip() or "v24.0",
        token=token,
        phone_number_id=get_setting("whatsapp_phone_number_id", "").strip(),
        business_account_id=get_setting("whatsapp_business_account_id", "").strip(),
        webhook_url=get_setting("whatsapp_webhook_url", "").strip(),
        default_template=get_setting("whatsapp_default_template", "").strip(),
        default_language=get_setting("whatsapp_default_language", "pt_BR").strip() or "pt_BR",
        delivery_mode=get_setting("delivery_mode", "official_api").strip() or "official_api",
        dry_run=get_setting("whatsapp_dry_run", "1") == "1",
        send_interval_seconds=float(get_setting("send_interval_seconds", "2") or 2),
        daily_send_limit=int(float(get_setting("daily_send_limit", "500") or 500)),
    )


def save_config(config: WhatsAppConfig, token_to_save: str | None = None) -> None:
    values = {
        "whatsapp_api_version": config.api_version.strip() or "v24.0",
        "whatsapp_phone_number_id": config.phone_number_id.strip(),
        "whatsapp_business_account_id": config.business_account_id.strip(),
        "whatsapp_webhook_url": config.webhook_url.strip(),
        "whatsapp_default_template": config.default_template.strip(),
        "whatsapp_default_language": config.default_language.strip() or "pt_BR",
        "delivery_mode": config.delivery_mode.strip() or "official_api",
        "whatsapp_dry_run": "1" if config.dry_run else "0",
        "send_interval_seconds": str(max(config.send_interval_seconds, 0.5)),
        "daily_send_limit": str(max(config.daily_send_limit, 1)),
    }
    if token_to_save:
        values["whatsapp_token_protected"] = _protect_secret(token_to_save.strip())
    set_settings(values)


def _media_component(media_path: str) -> dict[str, Any] | None:
    if not media_path:
        return None
    if not media_path.startswith(("http://", "https://")):
        raise WhatsAppAPIError("Para enviar imagem ou arquivo de verdade, use um link público ou envie antes pela Meta.")

    suffix = Path(media_path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return {"type": "header", "parameters": [{"type": "image", "image": {"link": media_path}}]}
    if suffix in {".mp4", ".3gp"}:
        return {"type": "header", "parameters": [{"type": "video", "video": {"link": media_path}}]}
    return {"type": "header", "parameters": [{"type": "document", "document": {"link": media_path}}]}


class WhatsAppBusinessClient:
    def __init__(self, config: WhatsAppConfig | None = None):
        self.config = config or load_config()

    @property
    def is_configured(self) -> bool:
        return bool(self.config.token and self.config.phone_number_id)

    def send_campaign_message(self, contact: dict[str, Any], campaign: dict[str, Any]) -> SendResult:
        phone = normalize_phone(str(contact["phone"]))
        template_name = str(campaign.get("template_name") or self.config.default_template).strip()
        language = str(campaign.get("template_language") or self.config.default_language or "pt_BR").strip()
        message = str(campaign.get("message") or "")
        media_path = str(campaign.get("media_path") or "")
        category = str(campaign.get("message_category") or "marketing")

        if self.config.delivery_mode == "manual_assisted":
            return SendResult(
                status="pendente_manual",
                action_url=build_click_to_chat_link(phone, message),
            )

        if self.config.dry_run:
            return SendResult(
                status="simulado",
                provider_message_id=f"dryrun-{int(time.time() * 1000)}",
                dry_run=True,
            )

        if not self.is_configured:
            raise WhatsAppAPIError("Preencha o token e o ID do número do WhatsApp Business.")
        if not template_name:
            if category == "service" and _inside_customer_service_window(contact.get("last_inbound_at")):
                return self.send_text_message(phone, message)
            raise WhatsAppAPIError(
                "Para envio automático real, use um modelo aprovado pela Meta."
            )

        return self.send_template_message(
            to=phone,
            template_name=template_name,
            language=language,
            variables=[message] if message else [],
            media_path=media_path,
        )

    def send_template_message(
        self,
        to: str,
        template_name: str,
        language: str = "pt_BR",
        variables: list[str] | None = None,
        media_path: str = "",
    ) -> SendResult:
        components: list[dict[str, Any]] = []
        media = _media_component(media_path)
        if media:
            components.append(media)
        if variables:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(value)} for value in variables],
                }
            )

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_phone(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language or "pt_BR"},
            },
        }
        if components:
            payload["template"]["components"] = components

        response = self._post_json(
            f"https://graph.facebook.com/{self.config.api_version}/{self.config.phone_number_id}/messages",
            payload,
        )
        provider_id = ""
        messages = response.get("messages") if isinstance(response, dict) else None
        if isinstance(messages, list) and messages:
            provider_id = str(messages[0].get("id", ""))
        return SendResult(status="enviado", provider_message_id=provider_id)

    def send_text_message(self, to: str, body: str, preview_url: bool = False) -> SendResult:
        if not body.strip():
            raise WhatsAppAPIError("A mensagem está vazia.")

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_phone(to),
            "type": "text",
            "text": {
                "preview_url": bool(preview_url),
                "body": body,
            },
        }
        response = self._post_json(
            f"https://graph.facebook.com/{self.config.api_version}/{self.config.phone_number_id}/messages",
            payload,
        )
        provider_id = ""
        messages = response.get("messages") if isinstance(response, dict) else None
        if isinstance(messages, list) and messages:
            provider_id = str(messages[0].get("id", ""))
        return SendResult(status="enviado", provider_message_id=provider_id)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise WhatsAppAPIError(_format_meta_error(exc.code, body)) from exc
        except urllib.error.URLError as exc:
            raise WhatsAppAPIError(f"Não consegui conectar com a Meta: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise WhatsAppAPIError("A Meta retornou uma resposta que o app não conseguiu entender.") from exc


def _format_meta_error(status_code: int, body: str) -> str:
    try:
        data = json.loads(body)
        error = data.get("error", {})
        message = error.get("message") or body
        code = error.get("code")
        details = f" Código {code}." if code else ""
        return f"Meta API HTTP {status_code}: {message}.{details}"
    except json.JSONDecodeError:
        return f"Meta API HTTP {status_code}: {body[:300]}"


def _inside_customer_service_window(value: object) -> bool:
    if not value:
        return False
    try:
        inbound_at = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    return datetime.now() - inbound_at <= timedelta(hours=24)


def build_click_to_chat_link(to: str, message: str) -> str:
    phone = normalize_phone(to)
    encoded = urllib.parse.quote(message or "")
    return f"https://wa.me/{phone}?text={encoded}"
