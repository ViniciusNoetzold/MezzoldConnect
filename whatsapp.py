from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from contacts import normalize_phone
from database import DATA_DIR, get_setting, set_settings


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
    delivery_mode: str = ""


DELIVERY_MODE_OFFICIAL_API = "official_api"
DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL = "whatsapp_web_experimental"
DELIVERY_MODE_MANUAL_ASSISTED = "manual_assisted"

VALID_DELIVERY_MODES = {
    DELIVERY_MODE_OFFICIAL_API,
    DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
    DELIVERY_MODE_MANUAL_ASSISTED,
}

DELIVERY_MODE_LABELS = {
    DELIVERY_MODE_OFFICIAL_API: "API Oficial Meta/WhatsApp Business (recomendado)",
    DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL: "WhatsApp Web Experimental via QR Code (nao oficial)",
    DELIVERY_MODE_MANUAL_ASSISTED: "Manual assistido por link (legado)",
}

WEB_STATUS_NOT_CONNECTED = "not_connected"
WEB_STATUS_WAITING_QR = "waiting_qr"
WEB_STATUS_CONNECTED = "connected"
WEB_STATUS_ERROR = "error"
WEB_STATUS_DISCONNECTED = "disconnected"

WEB_STATUS_LABELS = {
    WEB_STATUS_NOT_CONNECTED: "nao conectado",
    WEB_STATUS_WAITING_QR: "aguardando QR Code",
    WEB_STATUS_CONNECTED: "conectado",
    WEB_STATUS_ERROR: "erro",
    WEB_STATUS_DISCONNECTED: "desconectado",
}

WEB_PROFILE_DIR = DATA_DIR / "whatsapp_web_experimental_profile"
WEB_LOG_PATH = DATA_DIR / "whatsapp_web.log"


class WhatsAppWebSessionError(WhatsAppAPIError):
    pass


def _web_log(message: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="seconds")
        with WEB_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def _browser_label(browser_name: str) -> str:
    return {"chrome": "Chrome", "edge": "Edge"}.get(browser_name.lower(), browser_name.capitalize())


def normalize_delivery_mode(value: object) -> str:
    mode = str(value or DELIVERY_MODE_OFFICIAL_API).strip() or DELIVERY_MODE_OFFICIAL_API
    if mode not in VALID_DELIVERY_MODES:
        raise WhatsAppAPIError(f"Modo de envio desconhecido: {mode}.")
    return mode


def delivery_mode_label(value: object) -> str:
    try:
        mode = normalize_delivery_mode(value)
    except WhatsAppAPIError:
        return str(value or "")
    return DELIVERY_MODE_LABELS.get(mode, mode)


def web_connection_status_label(value: object) -> str:
    status = str(value or WEB_STATUS_NOT_CONNECTED)
    return WEB_STATUS_LABELS.get(status, status)


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
        delivery_mode=normalize_delivery_mode(get_setting("delivery_mode", DELIVERY_MODE_OFFICIAL_API)),
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
        "delivery_mode": normalize_delivery_mode(config.delivery_mode),
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
        delivery_mode = normalize_delivery_mode(campaign.get("delivery_mode") or self.config.delivery_mode)

        if self.config.dry_run:
            return SendResult(
                status="simulado",
                provider_message_id=f"dryrun-{int(time.time() * 1000)}",
                dry_run=True,
                delivery_mode=delivery_mode,
            )

        if delivery_mode == DELIVERY_MODE_MANUAL_ASSISTED:
            return SendResult(
                status="pendente_manual",
                action_url=build_click_to_chat_link(phone, message),
                delivery_mode=delivery_mode,
            )

        if delivery_mode == DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL:
            if not bool(campaign.get("explicit_user_confirmation")):
                raise WhatsAppAPIError(
                    "Envio real via WhatsApp Web Experimental exige confirmacao explicita do usuario."
                )
            return get_whatsapp_web_provider(self.config).send_campaign_message(contact, campaign)

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
        return SendResult(
            status="enviado",
            provider_message_id=provider_id,
            delivery_mode=DELIVERY_MODE_OFFICIAL_API,
        )

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
        return SendResult(
            status="enviado",
            provider_message_id=provider_id,
            delivery_mode=DELIVERY_MODE_OFFICIAL_API,
        )

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


class WhatsAppWebExperimentalProvider:
    def __init__(self, config: WhatsAppConfig | None = None):
        self.config = config or load_config()
        self._driver: Any | None = None
        self._status = WEB_STATUS_NOT_CONNECTED
        self._message = "Sessao local ainda nao aberta."
        self._browser_name = ""
        self._profile_dir = WEB_PROFILE_DIR

    def status_snapshot(self, refresh: bool = True) -> dict[str, str]:
        if refresh:
            self.refresh_status()
        return {
            "status": self._status,
            "label": web_connection_status_label(self._status),
            "message": self._message,
            "profile_dir": str(self._profile_dir),
        }

    def open_session(self) -> dict[str, str]:
        _web_log("open_session requested")
        driver = self._ensure_driver()
        try:
            driver.get("https://web.whatsapp.com/")
            self._wait_for_login_or_qr(driver)
            self.refresh_status()
            _web_log(
                f"open_session ready status={self._status} browser={self._browser_name or '-'} "
                f"profile_dir={self._profile_dir}"
            )
            return self.status_snapshot(refresh=False)
        except WhatsAppWebSessionError:
            raise
        except Exception as exc:
            self._set_status(WEB_STATUS_ERROR, f"Erro ao abrir WhatsApp Web: {exc}")
            _web_log(f"open_session error={exc}")
            raise WhatsAppWebSessionError(self._message) from exc

    def refresh_status(self) -> None:
        if self._driver is None:
            self._set_status(WEB_STATUS_NOT_CONNECTED, "Sessao local ainda nao aberta.")
            return
        try:
            status, message = self._page_state(self._driver)
            self._set_status(status, message)
        except Exception as exc:
            self._driver = None
            self._set_status(WEB_STATUS_DISCONNECTED, f"Navegador desconectado: {exc}")
            _web_log(f"refresh_status disconnected error={exc}")

    def send_campaign_message(self, contact: dict[str, Any], campaign: dict[str, Any]) -> SendResult:
        phone = normalize_phone(str(contact["phone"]))
        message = str(campaign.get("message") or "").strip()
        media_path = str(campaign.get("media_path") or "").strip()
        if not message:
            raise WhatsAppAPIError("A mensagem esta vazia.")
        if media_path:
            raise WhatsAppAPIError(
                "O modo WhatsApp Web Experimental envia apenas texto nesta versao. "
                "Use a API oficial para midias ou documentos."
            )

        driver = self._ensure_connected_driver()
        url = f"https://web.whatsapp.com/send?phone={phone}&text={urllib.parse.quote(message)}&app_absent=0"
        try:
            driver.get(url)
            button = self._wait_for_send_button(driver)
            time.sleep(random.uniform(1.5, 3.5))
            button.click()
            time.sleep(random.uniform(0.8, 1.8))
        except WhatsAppWebSessionError:
            raise
        except Exception as exc:
            status, _message = self._safe_page_state(driver)
            if status != WEB_STATUS_CONNECTED:
                self._set_status(status, "Sessao do WhatsApp Web indisponivel durante o envio.")
                raise WhatsAppWebSessionError(self._message) from exc
            raise WhatsAppAPIError(f"Nao consegui enviar pelo WhatsApp Web: {exc}") from exc

        return SendResult(
            status="enviado",
            provider_message_id=f"web-{int(time.time() * 1000)}",
            delivery_mode=DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
        )

    def _ensure_driver(self) -> Any:
        if self._driver is not None:
            return self._driver

        WEB_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        for browser_name in ("chrome", "edge"):
            try:
                self._driver = self._start_browser_driver(browser_name)
                self._browser_name = browser_name
                self._set_status(
                    WEB_STATUS_WAITING_QR,
                    f"{_browser_label(browser_name)} aberto. Leia o QR Code se ele aparecer.",
                )
                _web_log(
                    f"driver_ready browser={browser_name} profile_dir={self._profile_dir}"
                )
                return self._driver
            except WhatsAppWebSessionError as exc:
                errors.append(f"{_browser_label(browser_name)}: {exc}")
                _web_log(f"driver_failed browser={browser_name} error={exc}")

        detail = " | ".join(errors) if errors else "Nenhum navegador compativel foi iniciado."
        message = f"Nao consegui abrir o navegador local do WhatsApp Web. {detail}"
        self._set_status(WEB_STATUS_ERROR, message)
        raise WhatsAppWebSessionError(message)

    def _start_browser_driver(self, browser_name: str) -> Any:
        try:
            from selenium import webdriver
            if browser_name == "chrome":
                from selenium.webdriver.chrome.service import Service as BrowserService
            elif browser_name == "edge":
                from selenium.webdriver.edge.service import Service as BrowserService
            else:
                raise WhatsAppWebSessionError(f"Navegador nao suportado: {browser_name}.")
        except ImportError as exc:
            self._set_status(WEB_STATUS_ERROR, "Instale a biblioteca opcional selenium para usar o WhatsApp Web.")
            raise WhatsAppWebSessionError(
                "Biblioteca selenium nao encontrada. Instale com: py -m pip install selenium"
            ) from exc

        driver_path, browser_path = self._resolve_browser_paths(browser_name)
        options = self._build_browser_options(webdriver, browser_name, browser_path)
        service = BrowserService(executable_path=driver_path)
        try:
            if browser_name == "chrome":
                return webdriver.Chrome(service=service, options=options)
            return webdriver.Edge(service=service, options=options)
        except Exception as exc:
            raise WhatsAppWebSessionError(
                f"Nao consegui iniciar o {_browser_label(browser_name)}: {exc}"
            ) from exc

    def _resolve_browser_paths(self, browser_name: str) -> tuple[str, str]:
        try:
            from selenium.webdriver.common.selenium_manager import SeleniumManager
        except ImportError as exc:
            raise WhatsAppWebSessionError("Biblioteca selenium incompleta para localizar o navegador.") from exc

        try:
            result = SeleniumManager().binary_paths(["--browser", browser_name])
        except Exception as exc:
            raise WhatsAppWebSessionError(
                f"Nao consegui localizar {_browser_label(browser_name)} e WebDriver neste computador."
            ) from exc

        driver_path = str(result.get("driver_path") or "").strip()
        browser_path = str(result.get("browser_path") or "").strip()
        if not driver_path or not browser_path:
            raise WhatsAppWebSessionError(
                f"Nao encontrei {_browser_label(browser_name)} e WebDriver neste computador."
            )
        if not Path(driver_path).exists():
            raise WhatsAppWebSessionError(f"Driver do {_browser_label(browser_name)} nao foi encontrado.")
        if not Path(browser_path).exists():
            raise WhatsAppWebSessionError(f"Navegador {_browser_label(browser_name)} nao foi encontrado.")

        _web_log(
            f"driver_paths browser={browser_name} driver_path={driver_path} browser_path={browser_path}"
        )
        return driver_path, browser_path

    def _build_browser_options(self, webdriver_module: Any, browser_name: str, browser_path: str) -> Any:
        self._profile_dir = WEB_PROFILE_DIR / browser_name
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        if browser_name == "chrome":
            options = webdriver_module.ChromeOptions()
        else:
            options = webdriver_module.EdgeOptions()
        options.binary_location = browser_path
        for argument in (
            f"--user-data-dir={self._profile_dir}",
            "--profile-directory=Default",
            "--start-maximized",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-notifications",
            "--remote-allow-origins=*",
        ):
            options.add_argument(argument)
        return options

    def _ensure_connected_driver(self) -> Any:
        driver = self._ensure_driver()
        if not str(getattr(driver, "current_url", "")).startswith("https://web.whatsapp.com"):
            driver.get("https://web.whatsapp.com/")
        self._wait_until_connected(driver)
        return driver

    def _wait_for_login_or_qr(self, driver: Any) -> None:
        try:
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise WhatsAppWebSessionError("Biblioteca selenium incompleta.") from exc

        WebDriverWait(driver, 45).until(
            lambda current_driver: self._page_state(current_driver)[0]
            in {WEB_STATUS_WAITING_QR, WEB_STATUS_CONNECTED}
        )

    def _wait_until_connected(self, driver: Any) -> None:
        try:
            from selenium.common.exceptions import TimeoutException
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise WhatsAppWebSessionError("Biblioteca selenium incompleta.") from exc

        try:
            WebDriverWait(driver, 60).until(
                lambda current_driver: self._page_state(current_driver)[0] == WEB_STATUS_CONNECTED
            )
        except TimeoutException as exc:
            status, message = self._safe_page_state(driver)
            self._set_status(status, message)
            raise WhatsAppWebSessionError(
                "WhatsApp Web nao esta conectado. Abra Configuracoes, conecte pelo QR Code e tente novamente."
            ) from exc

    def _wait_for_send_button(self, driver: Any) -> Any:
        try:
            from selenium.common.exceptions import TimeoutException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise WhatsAppWebSessionError("Biblioteca selenium incompleta.") from exc

        selectors = [
            (By.CSS_SELECTOR, "button[aria-label='Send']"),
            (By.CSS_SELECTOR, "button[aria-label='Enviar']"),
            (By.XPATH, "//span[@data-icon='send']/ancestor::button"),
        ]

        def find_button(current_driver: Any) -> Any:
            status, _message = self._page_state(current_driver)
            if status != WEB_STATUS_CONNECTED:
                raise WhatsAppWebSessionError("WhatsApp Web saiu do estado conectado.")
            for by, selector in selectors:
                for element in current_driver.find_elements(by, selector):
                    if element.is_displayed() and element.is_enabled():
                        return element
            return False

        try:
            return WebDriverWait(driver, 45).until(find_button)
        except TimeoutException as exc:
            status, _message = self._safe_page_state(driver)
            if status != WEB_STATUS_CONNECTED:
                raise WhatsAppWebSessionError("WhatsApp Web desconectou antes do envio.") from exc
            raise WhatsAppAPIError(
                "Nao encontrei o botao de enviar no WhatsApp Web. Confira o numero e a conversa aberta."
            ) from exc

    def _page_state(self, driver: Any) -> tuple[str, str]:
        from selenium.webdriver.common.by import By

        if driver.find_elements(By.CSS_SELECTOR, "#pane-side"):
            return WEB_STATUS_CONNECTED, "WhatsApp Web conectado neste computador."
        if driver.find_elements(By.CSS_SELECTOR, "canvas"):
            return WEB_STATUS_WAITING_QR, "Aguardando leitura do QR Code no WhatsApp Web."
        body_text = ""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            body_text = ""
        if "qr" in body_text or "code" in body_text or "codigo" in body_text:
            return WEB_STATUS_WAITING_QR, "Aguardando leitura do QR Code no WhatsApp Web."
        return WEB_STATUS_NOT_CONNECTED, "WhatsApp Web ainda nao confirmou a sessao."

    def _safe_page_state(self, driver: Any) -> tuple[str, str]:
        try:
            return self._page_state(driver)
        except Exception as exc:
            return WEB_STATUS_DISCONNECTED, f"Navegador desconectado: {exc}"

    def _set_status(self, status: str, message: str) -> None:
        self._status = status
        self._message = message


_WEB_PROVIDER: WhatsAppWebExperimentalProvider | None = None


def get_whatsapp_web_provider(config: WhatsAppConfig | None = None) -> WhatsAppWebExperimentalProvider:
    global _WEB_PROVIDER
    if _WEB_PROVIDER is None:
        _WEB_PROVIDER = WhatsAppWebExperimentalProvider(config or load_config())
    elif config is not None:
        _WEB_PROVIDER.config = config
    return _WEB_PROVIDER


def open_whatsapp_web_session() -> dict[str, str]:
    return get_whatsapp_web_provider().open_session()


def get_whatsapp_web_status() -> dict[str, str]:
    return get_whatsapp_web_provider().status_snapshot()


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
