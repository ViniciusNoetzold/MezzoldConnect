# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import webbrowser
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Callable

import flet as ft

import app_update
import auth
import database
import network
import startup
import whatsapp

try:
    from screens import common as screen_common  # type: ignore  # noqa: F401
except (ImportError, AttributeError):
    screen_common = None


WHATSAPP_POLICY_URL = "https://www.whatsapp.com/legal/business-policy/"
META_CLOUD_API_URL = "https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview"
APP_UPDATES_URL = getattr(app_update, "DEFAULT_DOWNLOAD_URL", "https://github.com/ViniciusNoetzold/MezzoldConnect/releases")
DAILY_LIMIT_OPTIONS = ("50", "100", "250", "500")
UPDATE_CHANNEL_OPTIONS = ("stable", "beta", "dev")
LANGUAGE_OPTIONS = ("pt_BR", "en_US")
FONT_SIZE_OPTIONS = tuple(str(value) for value in range(9, 15))
DELAY_PRESETS = {
    "Seguro": ("60", "120", "60"),
    "Moderado": ("30", "45", "30"),
    "Rápido": ("10", "20", "10"),
}
CUSTOM_DELAY_PRESET = "Personalizado"


def _options_with_current(options: tuple[str, ...], current: object) -> tuple[str, ...]:
    value = str(current or "").strip()
    return (*options, value) if value and value not in options else options


def _delay_preset_for_values(minimum: object, maximum: object) -> str:
    pair = (str(minimum or "").strip(), str(maximum or "").strip())
    for label, (preset_min, preset_max, _fallback) in DELAY_PRESETS.items():
        if pair == (preset_min, preset_max):
            return label
    return CUSTOM_DELAY_PRESET


def settings_flags_for_role(role: str) -> dict[str, bool]:
    normalized = str(role or "").strip().lower()
    administrators = {
        getattr(auth, "ROLE_ADMIN", "admin"),
        getattr(auth, "ROLE_MEZZOLD_MASTER", "mezzold_master"),
    }
    manage_users = normalized in administrators
    technical = normalized == getattr(auth, "ROLE_EQUIPE", "equipe") or manage_users
    return {"advanced": technical, "technical": technical, "manage_users": manage_users}


def _record_value(record: object, key: str, default: object = None) -> object:
    return record.get(key, default) if isinstance(record, dict) else getattr(record, key, default)


class SettingsScreen(ft.View):
    """Central de configurações da v1 montada no design Flet da v2."""

    def __init__(self, page: ft.Page):
        super().__init__(route="/settings", padding=0)
        self.app_page = page
        self.file_picker = ft.FilePicker()
        if hasattr(page, "services"):
            page.services.append(self.file_picker)
        self.current_user_record = self._resolve_current_user()
        self.user_id = self._resolve_user_id()
        self.user = str(
            _record_value(self.current_user_record, "username", "")
            or getattr(auth, "get_current_user", lambda: "")()
            or "Usuário"
        )
        self.role = str(
            _record_value(self.current_user_record, "role", "")
            or getattr(auth, "get_current_role", lambda: "")()
            or getattr(auth, "ROLE_CLIENTE", "cliente")
        ).strip().lower()
        self.flags = settings_flags_for_role(self.role)
        checker = getattr(auth, "can_manage_users", None)
        if callable(checker):
            try:
                self.flags["manage_users"] = bool(checker())
            except TypeError:
                self.flags["manage_users"] = bool(checker(self.role))
            except Exception:
                pass
        self.is_technical = bool(self.flags["technical"])
        self.can_manage_users = bool(self.flags["manage_users"])

        try:
            config = whatsapp.load_config()
        except Exception:
            config = whatsapp.WhatsAppConfig()
        self._loaded_config = config
        self._make_fields(config)
        self._make_tabs()

        body = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Configurações", size=28, weight=ft.FontWeight.BOLD),
                                    ft.Text("Conta, envio, aquecimento e manutenção do aplicativo.", color=ft.Colors.ON_SURFACE_VARIANT),
                                ],
                                spacing=2,
                            ),
                            ft.Container(expand=True),
                            ft.Text(f"{getattr(database, 'APP_TITLE', 'Mezzold Connect')} {getattr(database, 'APP_VERSION', '')}"),
                        ]
                    ),
                    ft.Divider(height=12),
                    ft.Row(self.tab_buttons, spacing=8, scroll=ft.ScrollMode.AUTO),
                    self.tab_container,
                ],
                expand=True,
            ),
        )
        self.controls = [ft.Row([self._sidebar(), body], expand=True, spacing=0)]
        self._switch_tab(0)

    # --------------------------------------------------------------- construction
    def _resolve_current_user(self) -> object | None:
        getter = getattr(auth, "get_current_user_record", None)
        if callable(getter):
            try:
                record = getter()
                if record is not None:
                    return record
            except Exception:
                pass
        raw = getattr(auth, "get_current_user", lambda: None)()
        if raw is not None and not isinstance(raw, (str, int)):
            return raw
        user_id_getter = getattr(auth, "get_current_user_id", None)
        try:
            user_id = user_id_getter() if callable(user_id_getter) else (raw if isinstance(raw, int) else None)
        except Exception:
            user_id = None
        if user_id is not None and hasattr(auth, "get_user"):
            try:
                record = auth.get_user(int(user_id))
                if record is not None:
                    return record
            except Exception:
                pass
        username = str(raw or "").strip()
        if username and hasattr(auth, "list_users"):
            try:
                for record in auth.list_users():
                    if str(_record_value(record, "username", "")).casefold() == username.casefold():
                        return record
            except Exception:
                pass
        return None

    def _resolve_user_id(self) -> int | None:
        value = _record_value(self.current_user_record, "id", None)
        getter = getattr(auth, "get_current_user_id", None)
        if value is None and callable(getter):
            try:
                value = getter()
            except Exception:
                value = None
        try:
            parsed = int(value) if value is not None else 0
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    def _setting(self, key: str, default: str = "") -> str:
        try:
            return str(database.get_setting(key, default))
        except Exception:
            return default

    def _make_fields(self, config: whatsapp.WhatsAppConfig) -> None:
        col3, col4, col6, col8, col12 = ({"sm": 12, "md": value} for value in (3, 4, 6, 8, 12))
        self.company_name = ft.TextField(label="Nome da empresa / negócio", value=self._setting("company_name", "Mezzold"), col=col6)
        self.theme = ft.Dropdown(label="Tema", value=self._setting("app_theme", "light"), options=[ft.dropdown.Option("light", "Claro"), ft.dropdown.Option("dark", "Escuro")], col=col4)
        self.density = ft.Dropdown(label="Densidade", value=self._setting("ui_density", "normal"), options=[ft.dropdown.Option("compact", "Compacta"), ft.dropdown.Option("normal", "Normal"), ft.dropdown.Option("comfortable", "Confortável")], col=col4)
        font = self._setting("ui_font_size", "10")
        self.font_size = ft.Dropdown(label="Tamanho da fonte", value=font, options=[ft.dropdown.Option(v) for v in _options_with_current(FONT_SIZE_OPTIONS, font)], col=col4)
        self.old_password = ft.TextField(label="Senha atual", password=True, can_reveal_password=True, col=col4)
        self.new_password = ft.TextField(label="Nova senha", password=True, can_reveal_password=True, col=col4)
        self.confirm_new_password = ft.TextField(label="Confirmar nova senha", password=True, can_reveal_password=True, col=col4)

        token_exists = bool(getattr(config, "token", "") or self._setting("whatsapp_token_protected", ""))
        self.cfg_token = ft.TextField(label="Novo token permanente da Meta (opcional)", password=True, can_reveal_password=True, helper="Configurado e oculto; deixe em branco para manter." if token_exists else "Ainda não configurado.", col=col8)
        self.cfg_api_version = ft.TextField(label="Versão da API Meta", value=str(getattr(config, "api_version", "v24.0") or "v24.0"), col=col4)
        self.cfg_phone_id = ft.TextField(label="Phone Number ID", value=str(getattr(config, "phone_number_id", "") or ""), col=col6)
        self.cfg_business_id = ft.TextField(label="Business Account ID", value=str(getattr(config, "business_account_id", "") or ""), col=col6)
        self.cfg_webhook = ft.TextField(label="URL do webhook / callback", value=str(getattr(config, "webhook_url", "") or ""), col=col12)
        self.cfg_template = ft.TextField(label="Template aprovado padrão", value=str(getattr(config, "default_template", "") or ""), col=col6)
        language = str(getattr(config, "default_language", "pt_BR") or "pt_BR")
        self.cfg_language = ft.Dropdown(label="Idioma padrão do template", value=language, options=[ft.dropdown.Option(v) for v in _options_with_current(LANGUAGE_OPTIONS, language)], col=col6)
        self.cfg_delivery_mode = ft.Dropdown(
            label="Modo de envio",
            value=str(getattr(config, "delivery_mode", "official_api") or "official_api"),
            options=[
                ft.dropdown.Option(getattr(whatsapp, "DELIVERY_MODE_OFFICIAL_API", "official_api"), "API Oficial Meta"),
                ft.dropdown.Option(getattr(whatsapp, "DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL", "whatsapp_web_experimental"), "WhatsApp Web Experimental"),
                ft.dropdown.Option(getattr(whatsapp, "DELIVERY_MODE_MANUAL_ASSISTED", "manual_assisted"), "Manual assistido"),
            ],
            disabled=not self.is_technical,
            on_select=self._update_delivery_warning,
            col=col6,
        )
        self.delivery_warning = ft.Text()
        self.web_status = ft.Text("WhatsApp Web: status ainda não consultado.", color=ft.Colors.ON_SURFACE_VARIANT)

        daily = str(getattr(config, "daily_send_limit", 500) or 500)
        self.cfg_daily_limit = ft.Dropdown(label="Máximo de envios por dia", value=daily, options=[ft.dropdown.Option(v) for v in _options_with_current(DAILY_LIMIT_OPTIONS, daily)], col=col4)
        smart_min = self._setting("smart_min_interval_seconds", "30")
        smart_max = self._setting("smart_max_interval_seconds", "45")
        preset = _delay_preset_for_values(smart_min, smart_max)
        self.delay_preset = ft.Dropdown(label="Preset de delay", value=preset, options=[ft.dropdown.Option(v) for v in (*DELAY_PRESETS.keys(), CUSTOM_DELAY_PRESET)], on_select=self._apply_delay_preset, col=col4)
        self.cfg_send_interval = ft.TextField(label="Fallback global (s)", value=str(getattr(config, "send_interval_seconds", 60.0) or 60.0), col=col4)
        self.delay_notice = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.cfg_dry_run = ft.Switch(label="Modo teste / dry-run (não envia mensagens reais)", value=bool(getattr(config, "dry_run", True)))
        self.cfg_block_high_risk = ft.Switch(label="Bloquear campanha com risco muito alto", value=self._setting("block_high_risk_campaigns", "1") == "1")
        self.cfg_smart_send = ft.Switch(label="Usar pausas inteligentes automáticas", value=self._setting("smart_send_enabled", "0") == "1")
        self.smart_min_interval = ft.TextField(label="Espera mínima (s)", value=smart_min, col=col3)
        self.smart_max_interval = ft.TextField(label="Espera máxima (s)", value=smart_max, col=col3)
        self.smart_pause_every = ft.TextField(label="Pausa a cada X envios", value=self._setting("smart_pause_every", "10"), col=col3)
        self.smart_pause_min = ft.TextField(label="Pausa mínima (s)", value=self._setting("smart_pause_min_seconds", "120"), col=col3)
        self.smart_pause_max = ft.TextField(label="Pausa máxima (s)", value=self._setting("smart_pause_max_seconds", "300"), col=col3)
        self.smart_daily_limit = ft.TextField(label="Máximo diário inteligente", value=self._setting("smart_daily_limit", "100"), col=col3)
        self.smart_max_session = ft.TextField(label="Sessão máxima (min)", value=self._setting("smart_max_session_minutes", "90"), col=col3)
        self.rampup_min_interval = ft.TextField(label="Espera mínima entre testes (s)", value=self._setting("rampup_min_interval_seconds", "45"), col=col4)
        self.rampup_max_interval = ft.TextField(label="Espera máxima entre testes (s)", value=self._setting("rampup_max_interval_seconds", "180"), col=col4)
        self.rampup_daily_floor = ft.TextField(label="Envios bons para liberar número", value=self._setting("rampup_daily_floor", "5"), col=col4)

        self.startup_switch = ft.Switch(label="Iniciar Mezzold Connect com o Windows", value=self._startup_enabled(), disabled=not self._startup_supported())
        self.startup_minimized = ft.Switch(label="Iniciar worker minimizado na bandeja", value=self._startup_minimized(), disabled=not self._startup_supported())
        self.backup_status = ft.Text("Nenhum backup criado nesta sessão.", color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)
        self.internet_status = ft.Text("Internet: ainda não testada.", color=ft.Colors.ON_SURFACE_VARIANT)
        channel = self._setting("app_update_channel", getattr(app_update, "DEFAULT_CHANNEL", "stable"))
        self.update_manifest_url = ft.TextField(label="URL/caminho do manifesto (opcional)", value=self._setting("app_update_manifest_url", ""), col=col8)
        self.update_download_url = ft.TextField(label="Página/instalador para download", value=self._setting("app_update_download_url", APP_UPDATES_URL), col=col8)
        self.update_channel = ft.Dropdown(label="Canal", value=channel, options=[ft.dropdown.Option(v) for v in _options_with_current(UPDATE_CHANNEL_OPTIONS, channel)], col=col4)
        self.update_status = ft.Text(f"Versão atual: {getattr(database, 'APP_VERSION', '')}", color=ft.Colors.ON_SURFACE_VARIANT)
        license_data = self._load_license()
        self.license_key = ft.TextField(label="Código da licença", value=str(license_data.get("license_key", "")), col=col4)
        self.license_plan = ft.TextField(label="Plano", value=str(license_data.get("plan_name", "")), col=col4)
        self.license_until = ft.TextField(label="Validade", value=str(license_data.get("valid_until", "")), col=col4)
        self._apply_delay_preset(initialize=True)
        self._update_delivery_warning()
        if self.is_technical:
            self.refresh_web_status(update_page=False)

    @staticmethod
    def _section(title: str, controls: list[ft.Control], note: str = "") -> ft.Card:
        children: list[ft.Control] = [ft.Text(title, size=18, weight=ft.FontWeight.BOLD)]
        if note:
            children.append(ft.Text(note, size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        children.extend(controls)
        return ft.Card(ft.Container(ft.Column(children, spacing=12), padding=18))

    def _make_tabs(self) -> None:
        account = ft.ListView(
            [
                self._section("Conta atual", [ft.Text(f"Usuário: {self.user}", weight=ft.FontWeight.BOLD), ft.Text(f"ID: {self.user_id if self.user_id is not None else 'não disponível'} • Perfil: {self._role_label(self.role)}")]),
                self._section("Empresa e aparência", [ft.ResponsiveRow([self.company_name]), ft.ResponsiveRow([self.theme, self.density, self.font_size], spacing=12, run_spacing=12), ft.FilledButton("Salvar aparência", icon=ft.Icons.SAVE, on_click=self.save_appearance)], "Preferências salvas no banco local; o tema é aplicado imediatamente."),
                self._section("Alterar senha", [ft.ResponsiveRow([self.old_password, self.new_password, self.confirm_new_password], spacing=12, run_spacing=12), ft.FilledButton("Atualizar senha", icon=ft.Icons.KEY, on_click=self.change_password)], "A senha nova precisa ter pelo menos 8 caracteres."),
            ], spacing=12, padding=2, expand=True,
        )
        sending: list[ft.Control] = [
            self._section("Segurança de envio", [ft.ResponsiveRow([self.cfg_daily_limit, self.delay_preset, self.cfg_send_interval], spacing=12, run_spacing=12), self.delay_notice, *([self.cfg_dry_run, self.cfg_block_high_risk, self.cfg_smart_send] if self.is_technical else [ft.Text("Dry-run, bloqueio de risco e pausas avançadas são gerenciados pela equipe.")])], "Delays inferiores a 10 segundos são recusados."),
            self._section("Modo de envio", [ft.ResponsiveRow([self.cfg_delivery_mode]), self.delivery_warning, *([self.web_status, ft.Row([ft.OutlinedButton("Atualizar status", icon=ft.Icons.REFRESH, on_click=lambda _: self.refresh_web_status()), ft.FilledButton("Conectar / abrir WhatsApp Web", icon=ft.Icons.QR_CODE, on_click=self.open_whatsapp_web)], wrap=True)] if self.is_technical else [ft.Text("O modo técnico é somente leitura para este perfil.")])], "A API Oficial Meta é o modo recomendado; Web é experimental."),
            self._section("WhatsApp / Meta", [*([ft.ResponsiveRow([self.cfg_token, self.cfg_api_version], spacing=12), ft.ResponsiveRow([self.cfg_phone_id, self.cfg_business_id], spacing=12), ft.ResponsiveRow([self.cfg_webhook, self.cfg_template], spacing=12)] if self.is_technical else [ft.Text("Credenciais protegidas e gerenciadas pela equipe.")]), ft.ResponsiveRow([self.cfg_language])], "O token protegido nunca é exibido; vazio mantém o atual."),
        ]
        if self.is_technical:
            sending.extend([
                self._section("Smart-send completo", [ft.ResponsiveRow([self.smart_min_interval, self.smart_max_interval, self.smart_pause_every, self.smart_pause_min, self.smart_pause_max, self.smart_daily_limit, self.smart_max_session], spacing=12, run_spacing=12)], "Intervalos, pausas, limite e sessão máxima."),
                self._section("Aquecimento nativo", [ft.ResponsiveRow([self.rampup_min_interval, self.rampup_max_interval, self.rampup_daily_floor], spacing=12, run_spacing=12)], "Parâmetros do warmup interno; sem serviço externo."),
            ])
        sending.append(ft.FilledButton("Salvar configurações de envio", icon=ft.Icons.SAVE, on_click=self.save_whatsapp_config))
        sending_page = ft.ListView(sending, spacing=12, padding=2, expand=True)

        system: list[ft.Control] = [
            self._section("Inicialização", [self.startup_switch, self.startup_minimized, ft.Text("A opção minimizada inicia o worker em segundo plano.")], "Disponível neste Windows." if self._startup_supported() else "Disponível apenas no Windows."),
            self._section("Banco de dados e backup", [ft.Text(f"Banco ativo: {getattr(database, 'DB_PATH', '')}", selectable=True), ft.Row([ft.FilledButton("Criar backup SQLite consistente", icon=ft.Icons.BACKUP, on_click=self.make_backup), ft.OutlinedButton("Salvar cópia em…", icon=ft.Icons.SAVE_ALT, on_click=self.save_backup_copy)], wrap=True), self.backup_status], "Usa a API online do SQLite, inclusive em WAL."),
            self._section("Internet e links oficiais", [self.internet_status, ft.Row([ft.OutlinedButton("Testar internet", icon=ft.Icons.WIFI, on_click=self.test_internet), ft.OutlinedButton("Política do WhatsApp", icon=ft.Icons.POLICY, on_click=lambda _: self.open_external_link(WHATSAPP_POLICY_URL)), ft.OutlinedButton("Documentação Cloud API", icon=ft.Icons.DESCRIPTION, on_click=lambda _: self.open_external_link(META_CLOUD_API_URL))], wrap=True)]),
            self._section("Atualizações", [self.update_status, *([ft.ResponsiveRow([self.update_manifest_url, self.update_channel], spacing=12), ft.ResponsiveRow([self.update_download_url])] if self.is_technical else [ft.Text("Canal e fonte de atualização são gerenciados pela equipe.")]), ft.Row([ft.FilledButton("Verificar atualizações", icon=ft.Icons.SYSTEM_UPDATE, on_click=self.check_updates), ft.OutlinedButton("Abrir releases", icon=ft.Icons.OPEN_IN_NEW, on_click=lambda _: self.open_external_link(self.update_download_url.value or APP_UPDATES_URL))], wrap=True)], "Usa versão, manifesto, canal e download configurados."),
        ]
        if self.is_technical:
            system.append(self._section("Licença", [ft.ResponsiveRow([self.license_key, self.license_plan, self.license_until], spacing=12)], "Campos preservados para compatibilidade com a v1."))
        system.append(ft.FilledButton("Salvar configurações do sistema", icon=ft.Icons.SAVE, on_click=self.save_system_settings))
        system_page = ft.ListView(system, spacing=12, padding=2, expand=True)

        self.users_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text(v))
                for v in ("ID", "Usuário", "Perfil", "Ativo", "Troca obrigatória", "Último login", "Ações")
            ],
            rows=[],
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            key="settings-users-table",
        )
        users_page = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Gerenciamento de acessos", size=18, weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "Novo usuário",
                                    icon=ft.Icons.PERSON_ADD,
                                    key="settings-new-user",
                                    on_click=self.open_new_user_modal,
                                ),
                                ft.OutlinedButton(
                                    "Atualizar",
                                    icon=ft.Icons.REFRESH,
                                    key="settings-refresh-users",
                                    on_click=self.load_users,
                                ),
                            ],
                            wrap=True,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True,
                ),
                ft.Container(
                    content=ft.ListView([self.users_table], expand=True),
                    expand=True,
                    padding=4,
                ),
            ],
            expand=True,
            spacing=10,
        )
        pages: list[tuple[str, object, ft.Control]] = [("Conta e aparência", ft.Icons.ACCOUNT_CIRCLE, account), ("WhatsApp e envios", ft.Icons.SEND, sending_page), ("Sistema", ft.Icons.COMPUTER, system_page)]
        if self.can_manage_users:
            pages.append(("Usuários", ft.Icons.MANAGE_ACCOUNTS, users_page))
        self.tab_pages = [page for _label, _icon, page in pages]
        self.tab_buttons = [ft.Button(label, icon=icon, on_click=lambda _, index=index: self._switch_tab(index)) for index, (label, icon, _page) in enumerate(pages)]
        self.tab_container = ft.Container(expand=True)

    def _sidebar(self) -> ft.Container:
        if screen_common is not None:
            return screen_common.build_sidebar(self.app_page, "/settings")
        items: list[ft.Control] = [ft.Row([ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, color=ft.Colors.BLUE_ACCENT), ft.Text("Mezzold", size=20, weight=ft.FontWeight.BOLD)]), ft.Text(f"{self.user}\nPerfil: {self._role_label(self.role)}", color=ft.Colors.PRIMARY), ft.Divider(), self._menu("Início", ft.Icons.HOME, "/dashboard"), self._menu("Clientes", ft.Icons.PEOPLE, "/contacts"), self._menu("Nova Campanha", ft.Icons.SEND, "/campaigns"), self._menu("Agenda de Envios", ft.Icons.SCHEDULE, "/schedule"), self._menu("Conferir Risco", ft.Icons.WARNING_AMBER, "/risk"), self._menu("Histórico", ft.Icons.HISTORY, "/history")]
        if self.is_technical:
            items.append(self._menu("Saúde do Número", ft.Icons.HEALTH_AND_SAFETY, "/health"))
        items.extend([self._menu("Configurações", ft.Icons.SETTINGS, "/settings", True), ft.Container(expand=True), ft.OutlinedButton("Sair", icon=ft.Icons.LOGOUT, on_click=self.logout, width=210)])
        return ft.Container(width=250, bgcolor=ft.Colors.SURFACE_CONTAINER, padding=20, content=ft.Column(items, expand=True))

    def _menu(self, label: str, icon: object, route: str, selected: bool = False) -> ft.ListTile:
        return ft.ListTile(leading=ft.Icon(icon), title=ft.Text(label, weight=ft.FontWeight.BOLD if selected else None), selected=selected, on_click=lambda _: self.app_page.go(route))

    @staticmethod
    def _role_label(role: str) -> str:
        return {getattr(auth, "ROLE_CLIENTE", "cliente"): "Cliente", getattr(auth, "ROLE_EQUIPE", "equipe"): "Equipe técnica", getattr(auth, "ROLE_ADMIN", "admin"): "Administrador", getattr(auth, "ROLE_MEZZOLD_MASTER", "mezzold_master"): "Mezzold Master"}.get(str(role).lower(), str(role).title())

    # ---------------------------------------------------------------- UI helpers
    def _switch_tab(self, index: int) -> None:
        if not 0 <= index < len(self.tab_pages):
            return
        self.tab_container.content = self.tab_pages[index]
        for current, button in enumerate(self.tab_buttons):
            button.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE_ACCENT if current == index else ft.Colors.SURFACE_CONTAINER, color=ft.Colors.WHITE if current == index else ft.Colors.ON_SURFACE, shape=ft.RoundedRectangleBorder(radius=8))
        if index == 3 and self.can_manage_users:
            self.load_users(update_page=False)
        self._safe_update()

    def _safe_update(self) -> None:
        if screen_common is not None:
            screen_common.safe_update(self.app_page)
            return
        try:
            self.app_page.update()
        except Exception:
            pass

    def _show_dialog(self, dialog: object) -> None:
        self.app_page.show_dialog(dialog)

    def _close_dialog(self) -> None:
        if screen_common is not None:
            screen_common.close_dialog(self.app_page)
            return
        try:
            self.app_page.pop_dialog()
        except Exception:
            pass

    def show_snackbar(self, message: str, color: object = ft.Colors.GREEN_700) -> None:
        if screen_common is not None:
            screen_common.show_snack(
                self.app_page,
                message,
                error=color in {ft.Colors.RED, ft.Colors.RED_700, ft.Colors.ERROR, ft.Colors.ERROR_CONTAINER},
                bgcolor=color,
            )
            return
        self._show_dialog(ft.SnackBar(ft.Text(message), bgcolor=color, show_close_icon=True))

    def _run_worker(self, callback: Callable[[], None]) -> None:
        if screen_common is not None:
            screen_common.run_in_background(self.app_page, callback)
            return
        runner = getattr(self.app_page, "run_thread", None)
        if callable(runner):
            runner(callback)
        else:
            threading.Thread(target=callback, daemon=True).start()

    def logout(self, _event: object = None) -> None:
        if screen_common is not None:
            screen_common.logout(self.app_page, _event)
            return
        clearer = getattr(auth, "clear_session", None)
        if callable(clearer):
            try:
                clearer()
            except Exception:
                pass
        self.app_page.go("/")

    # ----------------------------------------------------------- account/visual
    def save_appearance(self, _event: object = None) -> None:
        try:
            company = str(self.company_name.value or "").strip()
            if not company:
                raise ValueError("Informe o nome da empresa.")
            font = self._positive_int(str(self.font_size.value or ""), "Tamanho da fonte", 9)
            if font > 14:
                raise ValueError("Tamanho da fonte: use um valor entre 9 e 14.")
            theme = str(self.theme.value or "light")
            density = str(self.density.value or "normal")
            if theme not in {"light", "dark"} or density not in {"compact", "normal", "comfortable"}:
                raise ValueError("Selecione opções válidas de aparência.")
            database.set_settings({"company_name": company, "app_theme": theme, "ui_density": density, "ui_font_size": str(font)})
            self.app_page.theme_mode = ft.ThemeMode.DARK if theme == "dark" else ft.ThemeMode.LIGHT
            densities = {"compact": ft.VisualDensity.COMPACT, "normal": ft.VisualDensity.STANDARD, "comfortable": ft.VisualDensity.COMFORTABLE}
            self.app_page.theme = ft.Theme(
                visual_density=densities[density],
                text_theme=ft.TextTheme(body_medium=ft.TextStyle(size=font)),
                page_transitions=(
                    screen_common.disabled_page_transitions()
                    if screen_common is not None
                    else ft.PageTransitionsTheme(
                        android=ft.PageTransitionTheme.NONE,
                        ios=ft.PageTransitionTheme.NONE,
                        linux=ft.PageTransitionTheme.NONE,
                        macos=ft.PageTransitionTheme.NONE,
                        windows=ft.PageTransitionTheme.NONE,
                    )
                ),
            )
            self._safe_update()
            self.show_snackbar("Empresa e aparência atualizadas.")
        except Exception as exc:
            self.show_snackbar(f"Não foi possível salvar a aparência: {exc}", ft.Colors.RED_700)

    def change_password(self, _event: object = None) -> None:
        old, new, confirmation = (str(field.value or "") for field in (self.old_password, self.new_password, self.confirm_new_password))
        if not old or not new or not confirmation:
            self.show_snackbar("Preencha os três campos de senha.", ft.Colors.RED_700)
            return
        if new != confirmation or len(new) < 8:
            self.show_snackbar("A confirmação deve coincidir e a senha precisa ter ao menos 8 caracteres.", ft.Colors.RED_700)
            return
        if self.user_id is None:
            self.show_snackbar("Entre novamente: ID da conta indisponível.", ft.Colors.RED_700)
            return
        try:
            auth.change_password(self.user_id, old, new)
        except Exception as exc:
            self.show_snackbar(f"Não foi possível alterar a senha: {exc}", ft.Colors.RED_700)
            return
        for field in (self.old_password, self.new_password, self.confirm_new_password):
            field.value = ""
        self._safe_update()
        self.show_snackbar("Senha alterada com sucesso.")

    # -------------------------------------------------------------- Meta/sending
    def _apply_delay_preset(self, _event: object = None, *, initialize: bool = False) -> None:
        preset = str(self.delay_preset.value or CUSTOM_DELAY_PRESET)
        if preset in DELAY_PRESETS:
            minimum, maximum, fallback = DELAY_PRESETS[preset]
            if not initialize:
                self.smart_min_interval.value, self.smart_max_interval.value, self.cfg_send_interval.value = minimum, maximum, fallback
            self.delay_notice.value = f"{preset}: {minimum}–{maximum}s entre mensagens."
        else:
            self.delay_notice.value = "Personalizado: confira os valores avançados."
        if not initialize:
            self._safe_update()

    def _update_delivery_warning(self, _event: object = None) -> None:
        mode = str(self.cfg_delivery_mode.value or "official_api")
        if mode == getattr(whatsapp, "DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL", "whatsapp_web_experimental"):
            self.delivery_warning.value, self.delivery_warning.color = "Experimental e não oficial: exige opt-in, LGPD e pode causar bloqueio/desconexão.", ft.Colors.AMBER_700
        elif mode == getattr(whatsapp, "DELIVERY_MODE_MANUAL_ASSISTED", "manual_assisted"):
            self.delivery_warning.value, self.delivery_warning.color = "Manual assistido: prepara a ação para o operador, sem disparo automático.", ft.Colors.ON_SURFACE_VARIANT
        else:
            self.delivery_warning.value, self.delivery_warning.color = "Recomendado: API oficial Meta com templates aprovados.", ft.Colors.GREEN_700
        self._safe_update()

    def save_whatsapp_config(self, _event: object = None) -> None:
        try:
            payload = self._collect_sending()
        except ValueError as exc:
            self.show_snackbar(str(exc), ft.Colors.RED_700)
            return

        def confirmed() -> None:
            if self.is_technical:
                self._confirm_technical_save(lambda: self._apply_sending(payload))
            else:
                self._apply_sending(payload)

        experimental = getattr(whatsapp, "DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL", "whatsapp_web_experimental")
        if self.is_technical and payload["config"].delivery_mode == experimental:
            self._show_dialog(ft.AlertDialog(modal=True, title=ft.Text("Ativar WhatsApp Web Experimental?"), content=ft.Text("Não é API oficial. Use somente com opt-in, respeitando LGPD e regras do WhatsApp; há risco de bloqueio, limite ou desconexão."), actions=[ft.TextButton("Cancelar", on_click=lambda _: self._close_dialog()), ft.FilledButton("Estou ciente", on_click=lambda _: (self._close_dialog(), confirmed()))]))
        else:
            confirmed()

    def _collect_sending(self) -> dict[str, object]:
        try:
            interval = float(str(self.cfg_send_interval.value or "").replace(",", "."))
        except ValueError as exc:
            raise ValueError("Intervalo global: informe apenas números.") from exc
        if interval <= 0:
            raise ValueError("Intervalo global precisa ser maior que zero.")
        daily = self._positive_int(str(self.cfg_daily_limit.value or ""), "Máximo diário", 1)
        current = self._loaded_config
        values = {
            "api_version": str(getattr(current, "api_version", "v24.0") or "v24.0"),
            "phone_number_id": str(getattr(current, "phone_number_id", "") or ""),
            "business_account_id": str(getattr(current, "business_account_id", "") or ""),
            "webhook_url": str(getattr(current, "webhook_url", "") or ""),
            "default_template": str(getattr(current, "default_template", "") or ""),
            "delivery_mode": str(getattr(current, "delivery_mode", "official_api") or "official_api"),
            "dry_run": bool(getattr(current, "dry_run", True)),
        }
        if self.is_technical:
            values.update(api_version=str(self.cfg_api_version.value or "v24.0").strip(), phone_number_id=str(self.cfg_phone_id.value or "").strip(), business_account_id=str(self.cfg_business_id.value or "").strip(), webhook_url=str(self.cfg_webhook.value or "").strip(), default_template=str(self.cfg_template.value or "").strip(), delivery_mode=str(self.cfg_delivery_mode.value or "official_api"), dry_run=bool(self.cfg_dry_run.value))
        smart = self._validated_smart()
        rampup = self._validated_rampup() if self.is_technical else {}
        config = whatsapp.WhatsAppConfig(**values, default_language=str(self.cfg_language.value or "pt_BR"), send_interval_seconds=interval, daily_send_limit=daily)
        return {"config": config, "smart": smart, "rampup": rampup}

    def _validated_smart(self) -> dict[str, int]:
        pairs = (("smart_min_interval_seconds", self.smart_min_interval, "Espera mínima", 1), ("smart_max_interval_seconds", self.smart_max_interval, "Espera máxima", 1), ("smart_pause_every", self.smart_pause_every, "Pausa a cada X envios", 1), ("smart_pause_min_seconds", self.smart_pause_min, "Pausa mínima", 0), ("smart_pause_max_seconds", self.smart_pause_max, "Pausa máxima", 0), ("smart_daily_limit", self.smart_daily_limit, "Máximo diário inteligente", 1), ("smart_max_session_minutes", self.smart_max_session, "Sessão máxima", 5))
        values = {key: self._positive_int(str(field.value or ""), label, minimum) for key, field, label, minimum in pairs}
        if min(values["smart_min_interval_seconds"], values["smart_max_interval_seconds"]) < 10:
            raise ValueError("Delays muito baixos podem ser bloqueados. Use pelo menos 10 segundos.")
        if values["smart_max_interval_seconds"] < values["smart_min_interval_seconds"]:
            raise ValueError("A espera máxima precisa ser igual ou maior que a mínima.")
        if values["smart_pause_max_seconds"] < values["smart_pause_min_seconds"]:
            raise ValueError("A pausa máxima precisa ser igual ou maior que a mínima.")
        return values

    def _validated_rampup(self) -> dict[str, int]:
        values = {"rampup_min_interval_seconds": self._positive_int(str(self.rampup_min_interval.value or ""), "Espera mínima do aquecimento", 1), "rampup_max_interval_seconds": self._positive_int(str(self.rampup_max_interval.value or ""), "Espera máxima do aquecimento", 1), "rampup_daily_floor": self._positive_int(str(self.rampup_daily_floor.value or ""), "Envios bons para liberar número", 1)}
        if values["rampup_max_interval_seconds"] < values["rampup_min_interval_seconds"]:
            raise ValueError("A espera máxima do aquecimento precisa ser igual ou maior que a mínima.")
        return values

    def _apply_sending(self, payload: dict[str, object]) -> None:
        try:
            config = payload["config"]
            token = (str(self.cfg_token.value or "").strip() or None) if self.is_technical else None
            whatsapp.save_config(config, token_to_save=token)
            smart = dict(payload["smart"])
            settings = {"smart_min_interval_seconds": str(smart["smart_min_interval_seconds"]), "smart_max_interval_seconds": str(smart["smart_max_interval_seconds"])}
            if self.is_technical:
                settings.update({key: str(value) for key, value in smart.items()})
                settings.update({key: str(value) for key, value in dict(payload["rampup"]).items()})
                settings.update({"block_high_risk_campaigns": "1" if self.cfg_block_high_risk.value else "0", "smart_send_enabled": "1" if self.cfg_smart_send.value else "0"})
            database.set_settings(settings)
            self._loaded_config = config
            self.cfg_token.value = ""
            self._safe_update()
            self.show_snackbar("Configurações de envio e aquecimento salvas.")
        except Exception as exc:
            self.show_snackbar(f"Não foi possível salvar o envio: {exc}", ft.Colors.RED_700)

    # ------------------------------------------------------------- startup/data
    def _startup_supported(self) -> bool:
        try:
            return bool(startup.is_supported())
        except Exception:
            return False

    def _startup_enabled(self) -> bool:
        try:
            return bool(startup.is_startup_enabled())
        except Exception:
            return False

    def _startup_minimized(self) -> bool:
        getter = getattr(startup, "is_startup_minimized", None)
        try:
            return bool(getter()) if callable(getter) else False
        except Exception:
            return False

    def save_system_settings(self, _event: object = None) -> None:
        if self.is_technical:
            self._confirm_technical_save(self._apply_system)
        else:
            self._apply_system()

    def _apply_system(self) -> None:
        try:
            enabled, minimized = bool(self.startup_switch.value), bool(self.startup_minimized.value)
            if not self._startup_supported() and enabled:
                raise RuntimeError("Inicialização automática está disponível apenas no Windows.")
            if self._startup_supported():
                setter = getattr(startup, "set_startup_enabled", None)
                if callable(setter):
                    try:
                        setter(enabled, minimized=minimized)
                    except TypeError:
                        setter(enabled)
                elif enabled and hasattr(startup, "enable_startup"):
                    startup.enable_startup(minimized=minimized)
                elif not enabled and hasattr(startup, "disable_startup"):
                    startup.disable_startup()
                else:
                    raise RuntimeError("API de inicialização indisponível.")
            if self.is_technical:
                database.set_settings({"app_update_manifest_url": str(self.update_manifest_url.value or "").strip(), "app_update_download_url": str(self.update_download_url.value or APP_UPDATES_URL).strip() or APP_UPDATES_URL, "app_update_channel": str(self.update_channel.value or getattr(app_update, "DEFAULT_CHANNEL", "stable"))})
                self._save_license(str(self.license_key.value or ""), str(self.license_plan.value or ""), str(self.license_until.value or ""))
            self.show_snackbar("Configurações do sistema salvas.")
        except Exception as exc:
            self.show_snackbar(f"Não foi possível salvar a inicialização: {exc}", ft.Colors.RED_700)

    def make_backup(self, _event: object = None) -> None:
        self.backup_status.value, self.backup_status.color = "Criando backup consistente...", ft.Colors.BLUE_700
        self._safe_update()
        def worker() -> None:
            try:
                creator = getattr(database, "create_backup", None) or getattr(database, "backup_database", None)
                path = creator() if callable(creator) else self._fallback_sqlite_backup()
                self.backup_status.value, self.backup_status.color = f"Backup criado: {path}", ft.Colors.GREEN_700
                self.show_snackbar("Backup SQLite criado e verificado.")
            except Exception as exc:
                self.backup_status.value, self.backup_status.color = f"Erro no backup: {exc}", ft.Colors.RED_700
                self.show_snackbar(f"Não foi possível criar o backup: {exc}", ft.Colors.RED_700)
            self._safe_update()
        self._run_worker(worker)

    async def save_backup_copy(self, _event: object = None) -> None:
        self.backup_status.value, self.backup_status.color = "Preparando cópia consistente...", ft.Colors.BLUE_700
        self._safe_update()
        try:
            creator = getattr(database, "create_backup", None) or getattr(database, "backup_database", None)
            path = Path(creator() if callable(creator) else self._fallback_sqlite_backup())
            destination = await self.file_picker.save_file(
                dialog_title="Salvar backup do Mezzold Connect",
                file_name=path.name,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["sqlite3", "db"],
                src_bytes=path.read_bytes(),
            )
            if destination:
                self.backup_status.value, self.backup_status.color = f"Cópia salva: {destination}", ft.Colors.GREEN_700
                self.show_snackbar("Cópia do backup salva no destino escolhido.")
            else:
                self.backup_status.value, self.backup_status.color = f"Seleção cancelada; backup preservado em {path}", ft.Colors.AMBER_700
        except Exception as exc:
            self.backup_status.value, self.backup_status.color = f"Erro no backup: {exc}", ft.Colors.RED_700
            self.show_snackbar(f"Não foi possível salvar a cópia: {exc}", ft.Colors.RED_700)
        self._safe_update()

    @staticmethod
    def _fallback_sqlite_backup() -> Path:
        source = Path(database.DB_PATH).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Banco não encontrado: {source}")
        target = (Path(getattr(database, "DATA_DIR", source.parent)) / "backups" / f"mezzold-connect-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite3").resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as source_conn:
                with closing(sqlite3.connect(temporary)) as target_conn:
                    source_conn.backup(target_conn)
                    target_conn.commit()
            with closing(sqlite3.connect(f"{temporary.as_uri()}?mode=ro", uri=True)) as check_conn:
                result = str(check_conn.execute("PRAGMA integrity_check").fetchone()[0])
            if result.lower() != "ok":
                raise RuntimeError(f"Integridade do backup falhou: {result}")
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return target

    def check_updates(self, _event: object = None) -> None:
        self.update_status.value, self.update_status.color = "Verificando atualizações...", ft.Colors.BLUE_700
        self._safe_update()
        version = str(getattr(database, "APP_VERSION", ""))
        manifest = str(self.update_manifest_url.value or self._setting("app_update_manifest_url", "")).strip()
        download = str(self.update_download_url.value or self._setting("app_update_download_url", APP_UPDATES_URL)).strip() or APP_UPDATES_URL
        channel = str(self.update_channel.value or self._setting("app_update_channel", getattr(app_update, "DEFAULT_CHANNEL", "stable"))).strip()
        def worker() -> None:
            try:
                self._finish_update(app_update.check_for_updates(version, manifest, download_url=download, channel=channel))
            except Exception as exc:
                self.update_status.value, self.update_status.color = f"Erro ao verificar: {exc}", ft.Colors.RED_700
                self._safe_update()
        self._run_worker(worker)

    def _finish_update(self, result: object) -> None:
        status = str(_record_value(result, "status", "error"))
        url = str(_record_value(result, "download_url", APP_UPDATES_URL) or APP_UPDATES_URL)
        if status == "no_manifest":
            self.update_status.value, self.update_status.color = "Nenhum manifesto remoto configurado.", ft.Colors.AMBER_700
            self._offer_link("Fonte não configurada", "Abrir a página oficial de releases?", url)
        elif status == "error":
            error = str(_record_value(result, "error", "erro desconhecido"))
            self.update_status.value, self.update_status.color = f"Não foi possível verificar: {error}", ft.Colors.RED_700
            self._offer_link("Falha ao verificar", f"{error}\n\nAbrir a página de download?", url)
        elif bool(_record_value(result, "has_update", False)):
            latest, notes = str(_record_value(result, "latest_version", "")), str(_record_value(result, "release_notes", ""))
            self.update_status.value, self.update_status.color = f"Nova versão disponível: {latest}.", ft.Colors.BLUE_700
            detail = f"Versão atual: {getattr(database, 'APP_VERSION', '')}\nNova versão: {latest}" + (f"\n\nNotas:\n{notes[:700]}" if notes else "") + "\n\nAbrir o download?"
            self._offer_link("Atualização disponível", detail, url)
        else:
            self.update_status.value, self.update_status.color = f"Você já está na versão mais recente ({getattr(database, 'APP_VERSION', '')}).", ft.Colors.GREEN_700
            self.show_snackbar(self.update_status.value)
        self._safe_update()

    def _offer_link(self, title: str, message: str, url: str) -> None:
        self._show_dialog(ft.AlertDialog(modal=True, title=ft.Text(title), content=ft.Text(message), actions=[ft.TextButton("Agora não", on_click=lambda _: self._close_dialog()), ft.FilledButton("Abrir", on_click=lambda _: (self._close_dialog(), self.open_external_link(url)))]))

    def test_internet(self, _event: object = None) -> None:
        self.internet_status.value, self.internet_status.color = "Testando internet...", ft.Colors.BLUE_700
        self._safe_update()
        def worker() -> None:
            online = bool(network.has_internet())
            self.internet_status.value, self.internet_status.color = ("Internet: funcionando.", ft.Colors.GREEN_700) if online else ("Internet: sem conexão.", ft.Colors.RED_700)
            self._safe_update()
        self._run_worker(worker)

    def open_external_link(self, url: str) -> None:
        if not network.has_internet():
            self.show_snackbar("É preciso internet para abrir este link.", ft.Colors.RED_700)
            return
        if screen_common is not None:
            screen_common.open_url(self.app_page, url)
            return
        launcher = getattr(self.app_page, "launch_url", None)
        launcher(url) if callable(launcher) else webbrowser.open(url)

    def refresh_web_status(self, _event: object = None, *, update_page: bool = True) -> None:
        try:
            snapshot = whatsapp.get_whatsapp_web_status()
            self.web_status.value = f"WhatsApp Web: {snapshot.get('label', 'desconhecido')}. {snapshot.get('message', '')}".strip()
            self.web_status.color = ft.Colors.GREEN_700 if snapshot.get("status") == "connected" else ft.Colors.ON_SURFACE_VARIANT
        except Exception as exc:
            self.web_status.value, self.web_status.color = f"WhatsApp Web: falha ao consultar. {exc}", ft.Colors.RED_700
        if update_page:
            self._safe_update()

    def open_whatsapp_web(self, _event: object = None) -> None:
        if not network.has_internet():
            self.show_snackbar("Sem internet para abrir o WhatsApp Web.", ft.Colors.RED_700)
            return
        self.web_status.value, self.web_status.color = "WhatsApp Web: abrindo sessão local...", ft.Colors.BLUE_700
        self._safe_update()
        def worker() -> None:
            try:
                snapshot = whatsapp.open_whatsapp_web_session()
                self.web_status.value, self.web_status.color = f"WhatsApp Web: {snapshot.get('label', '')}. {snapshot.get('message', '')}".strip(), ft.Colors.GREEN_700
            except Exception as exc:
                self.web_status.value, self.web_status.color = f"WhatsApp Web: erro. {exc}", ft.Colors.RED_700
                self.show_snackbar(f"Não foi possível abrir o WhatsApp Web: {exc}", ft.Colors.RED_700)
            self._safe_update()
        self._run_worker(worker)

    # ---------------------------------------------------------- secure confirm
    def _confirm_technical_save(self, callback: Callable[[], None]) -> None:
        verifier = getattr(auth, "verify_user_password", None)
        if self.user_id is None or not callable(verifier):
            self.show_snackbar("Entre novamente: confirmação segura indisponível.", ft.Colors.RED_700)
            return
        code = f"{secrets.randbelow(900000) + 100000}"
        password, typed = ft.TextField(label="Sua senha", password=True, can_reveal_password=True), ft.TextField(label="Código de confirmação")
        def confirm(_event: object = None) -> None:
            try:
                valid = bool(verifier(self.user_id, str(password.value or "")))
            except Exception as exc:
                self.show_snackbar(f"Não foi possível validar a senha: {exc}", ft.Colors.RED_700)
                return
            if not valid or str(typed.value or "").strip() != code:
                self.show_snackbar("Senha ou código não confere.", ft.Colors.RED_700)
                return
            self._close_dialog()
            callback()
        self._show_dialog(ft.AlertDialog(modal=True, title=ft.Text("Confirmar salvamento técnico"), content=ft.Column([ft.Text("Informe sua senha e copie o código exibido."), ft.Text(f"Código: {code}", size=18, weight=ft.FontWeight.BOLD, selectable=True), password, typed], tight=True, spacing=12), actions=[ft.TextButton("Cancelar", on_click=lambda _: self._close_dialog()), ft.FilledButton("Salvar agora", on_click=confirm)]))

    # -------------------------------------------------------------- user admin
    def load_users(self, _event: object = None, *, update_page: bool = True) -> None:
        if not self.can_manage_users:
            return
        try:
            rows = []
            for user in auth.list_users():
                uid, username, role = int(_record_value(user, "id", 0)), str(_record_value(user, "username", "")), str(_record_value(user, "role", ""))
                active, change = bool(_record_value(user, "is_active", False)), bool(_record_value(user, "must_change_password", False))
                last = str(_record_value(user, "last_login_at", "") or "Nunca")
                actions = ft.Row([ft.IconButton(icon=ft.Icons.TOGGLE_ON if active else ft.Icons.TOGGLE_OFF, icon_color=ft.Colors.GREEN_700 if active else ft.Colors.GREY_600, disabled=self.user_id == uid, tooltip="Desativar" if active else "Ativar", on_click=lambda _, user_id=uid, state=active: self.toggle_user_active(user_id, state)), ft.IconButton(icon=ft.Icons.BADGE, tooltip="Alterar perfil", on_click=lambda _, user_id=uid, name=username, current=role: self.open_role_modal(user_id, name, current)), ft.IconButton(icon=ft.Icons.LOCK_RESET, tooltip="Redefinir senha", on_click=lambda _, user_id=uid, name=username: self.open_reset_pw_modal(user_id, name))], spacing=0)
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(str(uid))), ft.DataCell(ft.Text(username, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(self._role_label(role))), ft.DataCell(ft.Icon(ft.Icons.CHECK if active else ft.Icons.CLOSE, color=ft.Colors.GREEN_700 if active else ft.Colors.RED_700)), ft.DataCell(ft.Text("Sim" if change else "Não")), ft.DataCell(ft.Text(last[:19])), ft.DataCell(actions)]))
            self.users_table.rows = rows
        except Exception as exc:
            self.show_snackbar(f"Não foi possível listar usuários: {exc}", ft.Colors.RED_700)
        if update_page:
            self._safe_update()

    def toggle_user_active(self, user_id: int, current_active: bool) -> None:
        if not self.can_manage_users:
            return
        try:
            (auth.deactivate_user if current_active else auth.activate_user)(user_id)
            self.show_snackbar("Usuário desativado." if current_active else "Usuário ativado.")
            self.load_users()
        except Exception as exc:
            self.show_snackbar(f"Não foi possível alterar o usuário: {exc}", ft.Colors.RED_700)

    def open_reset_pw_modal(self, user_id: int, username: str) -> None:
        if not self.can_manage_users:
            return
        field = ft.TextField(label="Nova senha provisória", password=True, can_reveal_password=True)
        def reset(_event: object = None) -> None:
            value = str(field.value or "")
            if len(value) < 8:
                self.show_snackbar("A senha precisa ter pelo menos 8 caracteres.", ft.Colors.RED_700)
                return
            try:
                auth.reset_user_password(user_id, value, must_change_password=True)
            except Exception as exc:
                self.show_snackbar(f"Não foi possível redefinir: {exc}", ft.Colors.RED_700)
                return
            self._close_dialog(); self.show_snackbar(f"Senha de '{username}' redefinida."); self.load_users()
        self._show_dialog(ft.AlertDialog(modal=True, title=ft.Text(f"Redefinir senha de {username}"), content=field, actions=[ft.TextButton("Cancelar", on_click=lambda _: self._close_dialog()), ft.FilledButton("Redefinir", on_click=reset)]))

    def open_role_modal(self, user_id: int, username: str, current_role: str) -> None:
        if not self.can_manage_users:
            return
        field = ft.Dropdown(label="Perfil", value=current_role, options=[ft.dropdown.Option(role, self._role_label(role)) for role in self._assignable_roles()])
        def save(_event: object = None) -> None:
            try:
                auth.update_user_role(user_id, str(field.value or getattr(auth, "ROLE_CLIENTE", "cliente")))
            except Exception as exc:
                self.show_snackbar(f"Não foi possível alterar o perfil: {exc}", ft.Colors.RED_700); return
            self._close_dialog(); self.show_snackbar(f"Perfil de '{username}' atualizado."); self.load_users()
        self._show_dialog(ft.AlertDialog(modal=True, title=ft.Text(f"Alterar perfil de {username}"), content=field, actions=[ft.TextButton("Cancelar", on_click=lambda _: self._close_dialog()), ft.FilledButton("Salvar", on_click=save)]))

    def open_new_user_modal(self, _event: object = None) -> None:
        if not self.can_manage_users:
            return
        username, password = ft.TextField(label="Nome de usuário"), ft.TextField(label="Senha inicial", password=True, can_reveal_password=True)
        role = ft.Dropdown(label="Perfil", value=getattr(auth, "ROLE_CLIENTE", "cliente"), options=[ft.dropdown.Option(value, self._role_label(value)) for value in self._assignable_roles()])
        def create(_event: object = None) -> None:
            name, secret = str(username.value or "").strip(), str(password.value or "")
            if not name or len(secret) < 8:
                self.show_snackbar("Informe o usuário e uma senha de ao menos 8 caracteres.", ft.Colors.RED_700); return
            try:
                auth.create_user(name, secret, role=str(role.value), must_change_password=True)
            except Exception as exc:
                self.show_snackbar(f"Não foi possível criar o usuário: {exc}", ft.Colors.RED_700); return
            self._close_dialog(); self.show_snackbar(f"Usuário '{name}' criado."); self.load_users()
        self._show_dialog(ft.AlertDialog(modal=True, title=ft.Text("Cadastrar novo usuário"), content=ft.Column([username, password, role], tight=True, spacing=12), actions=[ft.TextButton("Cancelar", on_click=lambda _: self._close_dialog()), ft.FilledButton("Cadastrar", on_click=create)]))

    @staticmethod
    def _assignable_roles() -> list[str]:
        return list(dict.fromkeys([getattr(auth, "ROLE_CLIENTE", "cliente"), getattr(auth, "ROLE_EQUIPE", "equipe"), getattr(auth, "ROLE_ADMIN", "admin")]))

    # --------------------------------------------------------------- persistence
    def _load_license(self) -> dict[str, object]:
        try:
            with database.connect() as conn:
                row = conn.execute("SELECT * FROM license WHERE id = 1").fetchone()
            converter = getattr(database, "row_to_dict", None)
            return (converter(row) if callable(converter) else dict(row)) or {}
        except Exception:
            return {}

    @staticmethod
    def _save_license(key: str, plan: str, valid_until: str) -> None:
        now = getattr(database, "now_text", lambda: datetime.now().isoformat(timespec="seconds"))()
        with database.connect() as conn:
            conn.execute("UPDATE license SET license_key = ?, plan_name = ?, valid_until = ?, status = ?, updated_at = ? WHERE id = 1", (key.strip(), plan.strip(), valid_until.strip(), "ativa" if key.strip() else "pendente", now))

    @staticmethod
    def _positive_int(value: str, label: str, minimum: int) -> int:
        try:
            parsed = int(float(value.replace(",", ".")))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}: informe apenas números.") from exc
        if parsed < minimum:
            raise ValueError(f"{label}: use um valor igual ou maior que {minimum}.")
        return parsed

    def did_mount(self) -> None:
        if self.can_manage_users:
            self.load_users()
