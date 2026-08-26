from __future__ import annotations

from datetime import datetime
from typing import Any

import flet as ft

import contacts
import warmup
import whatsapp
from runtime import app_runtime
from screens import common


STATUS_LABELS = {
    "testing": "Em aquecimento",
    "healthy": "Saudável",
    "paused": "Pausado",
    "auto_paused": "Auto-pausado",
    "restricted": "Restrito",
    "banned": "Banido",
    "running": "Em execução",
    "completed": "Concluído",
    "resting": "Em repouso",
    "enviado": "Enviado",
    "simulado": "Simulado",
    "pendente_manual": "Ação manual",
    "falhou": "Falhou",
    "respondido": "Respondido",
    "opt_out": "Opt-out",
}

QUALITY_LABELS = {
    "unknown": "Sem dados",
    "high": "Alta",
    "medium": "Média",
    "low": "Baixa",
}

PROVIDER_LABELS = {
    whatsapp.DELIVERY_MODE_OFFICIAL_API: "API Oficial",
    whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL: "WhatsApp Web",
    whatsapp.DELIVERY_MODE_MANUAL_ASSISTED: "Manual assistido",
}

VALID_STATUSES = frozenset({"testing", "healthy", "paused", "auto_paused", "restricted", "banned"})
VALID_QUALITIES = frozenset(QUALITY_LABELS)


def friendly_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return STATUS_LABELS.get(normalized, normalized.replace("_", " ").capitalize() or "-")


def friendly_quality(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return QUALITY_LABELS.get(normalized, normalized.capitalize() or "-")


def friendly_provider(value: object) -> str:
    try:
        normalized = warmup.normalize_provider(value)
    except (TypeError, ValueError):
        normalized = str(value or "")
    return PROVIDER_LABELS.get(normalized, normalized.replace("_", " ").capitalize() or "-")


def _format_datetime(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        return datetime.fromisoformat(text).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text[:16].replace("T", " ")


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


class HealthScreen(ft.View):
    """Native warmup dashboard/editor backed by the process-wide runtime."""

    def __init__(self, page: ft.Page):
        super().__init__(route=common.ROUTE_HEALTH, padding=0)
        self.app_page = page
        self.selected_number_id: int | None = None

        self.stat_total = self._stat_value("health-stat-total")
        self.stat_active = self._stat_value("health-stat-active", ft.Colors.GREEN)
        self.stat_ready = self._stat_value("health-stat-ready", ft.Colors.BLUE)
        self.stat_paused = self._stat_value("health-stat-paused", ft.Colors.AMBER)

        self.numbers_table = ft.DataTable(
            key="warmup-numbers-table",
            columns=[
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Provedor")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Score"), numeric=True),
                ft.DataColumn(ft.Text("Qualidade")),
                ft.DataColumn(ft.Text("Meta hoje"), numeric=True),
                ft.DataColumn(ft.Text("Enviados"), numeric=True),
                ft.DataColumn(ft.Text("Pronto")),
                ft.DataColumn(ft.Text("Execução")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[],
            column_spacing=18,
        )
        self.runs_table = ft.DataTable(
            key="warmup-runs-table",
            columns=[
                ft.DataColumn(ft.Text("Início")),
                ft.DataColumn(ft.Text("Número")),
                ft.DataColumn(ft.Text("Grupo")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Meta"), numeric=True),
                ft.DataColumn(ft.Text("Enviados"), numeric=True),
                ft.DataColumn(ft.Text("Simulados"), numeric=True),
                ft.DataColumn(ft.Text("Manuais"), numeric=True),
                ft.DataColumn(ft.Text("Falhas"), numeric=True),
                ft.DataColumn(ft.Text("Ignorados"), numeric=True),
                ft.DataColumn(ft.Text("Fim")),
            ],
            rows=[],
            column_spacing=18,
        )
        self.events_table = ft.DataTable(
            key="warmup-events-table",
            columns=[
                ft.DataColumn(ft.Text("Data/hora")),
                ft.DataColumn(ft.Text("Número")),
                ft.DataColumn(ft.Text("Destinatário")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Detalhe")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[],
            column_spacing=18,
        )
        self.numbers_empty = ft.Text("Nenhum número cadastrado.")
        self.runs_empty = ft.Text("Nenhuma execução registrada.")
        self.events_empty = ft.Text("Nenhum evento de aquecimento registrado.")

        self.f_name = ft.TextField(label="Nome / identificador *", key="warmup-name", dense=True)
        self.f_phone = ft.TextField(
            label="Telefone com DDD *",
            hint_text="Ex.: (11) 99999-9999",
            key="warmup-phone",
            dense=True,
        )
        self.f_phone_id = ft.TextField(label="ID do número na Meta", key="warmup-phone-number-id", dense=True)
        self.f_provider = ft.Dropdown(
            label="Tipo de envio",
            value=whatsapp.DELIVERY_MODE_OFFICIAL_API,
            key="warmup-provider",
            dense=True,
            options=[
                ft.DropdownOption(key=whatsapp.DELIVERY_MODE_OFFICIAL_API, text="API Oficial Meta"),
                ft.DropdownOption(
                    key=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                    text="WhatsApp Web Experimental",
                ),
                ft.DropdownOption(key=whatsapp.DELIVERY_MODE_MANUAL_ASSISTED, text="Manual assistido"),
            ],
        )
        self.f_status = ft.Dropdown(
            label="Status",
            value="testing",
            key="warmup-status",
            dense=True,
            options=[
                ft.DropdownOption(key=value, text=label)
                for value, label in (
                    ("testing", "Em aquecimento"),
                    ("healthy", "Saudável"),
                    ("paused", "Pausado"),
                    ("auto_paused", "Auto-pausado"),
                    ("restricted", "Restrito"),
                    ("banned", "Banido"),
                )
            ],
        )
        self.f_quality = ft.Dropdown(
            label="Qualidade Meta",
            value="unknown",
            key="warmup-quality",
            dense=True,
            options=[
                ft.DropdownOption(key="unknown", text="Sem dados"),
                ft.DropdownOption(key="high", text="Alta"),
                ft.DropdownOption(key="medium", text="Média"),
                ft.DropdownOption(key="low", text="Baixa"),
            ],
        )
        self.f_limit = ft.TextField(label="Limite atual da conta", value="250", key="warmup-messaging-limit", dense=True)
        self.f_daily_target = ft.TextField(label="Meta diária inicial", value="20", key="warmup-daily-target", dense=True)
        self.f_max_target = ft.TextField(label="Meta diária máxima", value="500", key="warmup-max-target", dense=True)
        self.f_rest_start = ft.TextField(
            label="Início do repouso (HH:MM)", value="00:00", key="warmup-rest-start", dense=True
        )
        self.f_rest_end = ft.TextField(
            label="Fim do repouso (HH:MM)", value="07:00", key="warmup-rest-end", dense=True
        )
        self.f_group = ft.Dropdown(
            label="Grupo autorizado para aquecimento *",
            key="warmup-group",
            dense=True,
            enable_search=True,
            options=[],
        )
        self.f_active = ft.Switch(label="Número ativo", value=True, key="warmup-active")
        self.f_ready = ft.Switch(label="Pronto para campanhas", value=False, key="warmup-ready-for-campaigns")
        self.f_notes = ft.TextField(
            label="Notas / observações",
            multiline=True,
            min_lines=2,
            max_lines=4,
            key="warmup-notes",
            dense=True,
        )

        self.progress_bar = ft.ProgressBar(
            value=0,
            visible=False,
            key="warmup-progress",
            semantics_label="Progresso do aquecimento",
        )
        self.progress_msg = ft.Text(
            "Selecione um número para editar ou aquecer.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            key="warmup-progress-message",
        )
        self.new_button = ft.OutlinedButton(
            "Novo", icon=ft.Icons.ADD, key="warmup-new-button", on_click=self.clear_form, expand=True
        )
        self.save_button = ft.FilledButton(
            "Salvar", icon=ft.Icons.SAVE, key="warmup-save-button", on_click=self.save_number, expand=True
        )
        self.start_button = ft.FilledButton(
            "Iniciar aquecimento",
            icon=ft.Icons.PLAY_ARROW,
            key="warmup-start-button",
            on_click=self.start_warmup,
            disabled=True,
            expand=True,
        )
        self.pause_button = ft.OutlinedButton(
            "Pausar agora",
            icon=ft.Icons.PAUSE,
            key="warmup-pause-button",
            on_click=self.stop_warmup,
            disabled=True,
            expand=True,
        )
        self.delete_button = ft.TextButton(
            "Excluir número",
            icon=ft.Icons.DELETE,
            key="warmup-delete-button",
            on_click=self.delete_number,
            disabled=True,
            style=ft.ButtonStyle(color=ft.Colors.ERROR),
        )

        form_card = ft.Container(
            width=370,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=12,
            key="warmup-form-card",
            content=ft.Column(
                controls=[
                    ft.Text("Cadastrar / editar número", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=4),
                    ft.ListView(
                        controls=[
                            self.f_name,
                            self.f_phone,
                            self.f_phone_id,
                            self.f_provider,
                            self.f_status,
                            self.f_quality,
                            ft.Row([self.f_limit, self.f_daily_target], spacing=8),
                            self.f_max_target,
                            ft.Row([self.f_rest_start, self.f_rest_end], spacing=8),
                            self.f_group,
                            ft.Row([self.f_active, self.f_ready], wrap=True, spacing=8),
                            self.f_notes,
                        ],
                        spacing=9,
                        expand=True,
                        key="warmup-form-fields",
                    ),
                    self.progress_bar,
                    self.progress_msg,
                    ft.Row([self.new_button, self.save_button], spacing=8),
                    ft.Row([self.start_button, self.pause_button], spacing=8),
                    ft.Row([self.delete_button], alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=8,
                expand=True,
            ),
        )

        tabs = ft.Tabs(
            length=3,
            selected_index=0,
            expand=True,
            key="warmup-tabs",
            content=ft.Column(
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="Números", icon=ft.Icons.PHONE_ANDROID),
                            ft.Tab(label="Execuções", icon=ft.Icons.PLAYLIST_PLAY),
                            ft.Tab(label="Eventos", icon=ft.Icons.RECEIPT_LONG),
                        ],
                        key="warmup-tab-bar",
                    ),
                    ft.TabBarView(
                        controls=[
                            self._table_panel(self.numbers_table, self.numbers_empty),
                            self._table_panel(self.runs_table, self.runs_empty),
                            self._table_panel(self.events_table, self.events_empty),
                        ],
                        expand=True,
                        key="warmup-tab-content",
                    ),
                ],
                expand=True,
                spacing=4,
            ),
        )

        dashboard = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        self._card("Total", self.stat_total, ft.Icons.PHONE_ANDROID, ft.Colors.BLUE_GREY),
                        self._card("Ativos", self.stat_active, ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN),
                        self._card("Prontos", self.stat_ready, ft.Icons.VERIFIED, ft.Colors.BLUE),
                        self._card("Pausados", self.stat_paused, ft.Icons.PAUSE_CIRCLE, ft.Colors.AMBER),
                    ],
                    spacing=10,
                ),
                tabs,
            ],
            spacing=10,
            expand=True,
            key="warmup-dashboard",
        )
        body = ft.Row(
            controls=[dashboard, form_card],
            expand=True,
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            key="warmup-body",
        )

        self.controls = [
            common.screen_layout(
                page,
                common.ROUTE_HEALTH,
                "Aquecimento e saúde dos números",
                body,
                subtitle="Rampa nativa com contatos autorizados, limites graduais e pausa imediata.",
                actions=[
                    ft.OutlinedButton(
                        "Atualizar",
                        icon=ft.Icons.REFRESH,
                        key="warmup-refresh-button",
                        on_click=self.load_data,
                    )
                ],
            )
        ]
        self._refresh_groups()

    @staticmethod
    def _stat_value(key: str, color: Any | None = None) -> ft.Text:
        return ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=color, key=key)

    @staticmethod
    def _card(title: str, value: ft.Text, icon: Any, color: Any) -> ft.Container:
        return ft.Container(
            expand=True,
            padding=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=8,
            content=ft.Row(
                [
                    ft.Icon(icon, color=color, size=28),
                    ft.Column(
                        [ft.Text(title, size=11, color=ft.Colors.ON_SURFACE_VARIANT), value], spacing=2
                    ),
                ],
                spacing=10,
            ),
        )

    @staticmethod
    def _table_panel(table: ft.DataTable, empty_label: ft.Text) -> ft.Container:
        return ft.Container(
            expand=True,
            padding=8,
            content=ft.Column(
                controls=[empty_label, ft.Row([table], scroll=ft.ScrollMode.AUTO, expand=True)],
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def _refresh_groups(self) -> list[str]:
        groups = contacts.list_groups()
        current = str(self.f_group.value or "").strip()
        self.f_group.options = [ft.DropdownOption(key=name, text=name) for name in groups]
        self.f_group.value = current if current in groups else (groups[0] if groups else None)
        return groups

    def clear_form(self, _event: object | None = None) -> None:
        self.selected_number_id = None
        self.f_name.value = ""
        self.f_phone.value = ""
        self.f_phone_id.value = ""
        self.f_provider.value = whatsapp.DELIVERY_MODE_OFFICIAL_API
        self.f_status.value = "testing"
        self.f_quality.value = "unknown"
        self.f_limit.value = "250"
        self.f_daily_target.value = "20"
        self.f_max_target.value = "500"
        self.f_rest_start.value = "00:00"
        self.f_rest_end.value = "07:00"
        self.f_active.value = True
        self.f_ready.value = False
        self.f_notes.value = ""
        self._clear_form_errors()
        self._refresh_groups()
        self.progress_bar.visible = False
        self.progress_bar.value = 0
        self.progress_msg.value = "Novo cadastro. Preencha os campos obrigatórios."
        self._update_runtime_controls()
        common.safe_update(self.app_page)

    def _clear_form_errors(self) -> None:
        for field in (
            self.f_name,
            self.f_phone,
            self.f_limit,
            self.f_daily_target,
            self.f_max_target,
            self.f_rest_start,
            self.f_rest_end,
        ):
            field.error = None
        for field in (self.f_provider, self.f_status, self.f_quality, self.f_group):
            field.error_text = None

    @staticmethod
    def _required_int(field: ft.TextField, label: str, minimum: int = 1) -> int:
        try:
            value = int(str(field.value or "").strip())
        except ValueError as exc:
            field.error = f"{label}: informe um número inteiro."
            raise ValueError(field.error) from exc
        if value < minimum:
            field.error = f"{label}: o mínimo é {minimum}."
            raise ValueError(field.error)
        return value

    @staticmethod
    def _validate_time_field(field: ft.TextField, label: str) -> str:
        value = str(field.value or "").strip()
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            field.error = f"{label}: use HH:MM, por exemplo 07:00."
            raise ValueError(field.error) from exc
        return value

    def _form_payload(self) -> dict[str, Any]:
        self._clear_form_errors()
        name = str(self.f_name.value or "").strip()
        if not name:
            self.f_name.error = "Informe um nome para identificar o número."
            raise ValueError(self.f_name.error)
        phone = str(self.f_phone.value or "").strip()
        if not phone or not contacts.is_valid_phone(phone):
            self.f_phone.error = "Telefone inválido. Informe DDD e número."
            raise ValueError(self.f_phone.error)

        try:
            provider = warmup.normalize_provider(self.f_provider.value)
        except warmup.WarmupError as exc:
            self.f_provider.error_text = str(exc)
            raise ValueError(str(exc)) from exc
        status = str(self.f_status.value or "")
        if status not in VALID_STATUSES:
            self.f_status.error_text = "Selecione um status válido."
            raise ValueError(self.f_status.error_text)
        quality = str(self.f_quality.value or "")
        if quality not in VALID_QUALITIES:
            self.f_quality.error_text = "Selecione uma qualidade válida."
            raise ValueError(self.f_quality.error_text)

        messaging_limit = self._required_int(self.f_limit, "Limite da conta")
        daily_target = self._required_int(
            self.f_daily_target, "Meta diária inicial", warmup.INITIAL_DAILY_TARGET
        )
        max_daily_target = self._required_int(self.f_max_target, "Meta diária máxima")
        if daily_target > messaging_limit:
            self.f_daily_target.error = "A meta inicial não pode superar o limite atual da conta."
            raise ValueError(self.f_daily_target.error)
        if max_daily_target < daily_target:
            self.f_max_target.error = "A meta máxima não pode ser menor que a meta inicial."
            raise ValueError(self.f_max_target.error)

        return {
            "display_name": name,
            "phone": phone,
            "phone_number_id": str(self.f_phone_id.value or "").strip(),
            "provider": provider,
            "status": status,
            "quality_rating": quality,
            "messaging_limit": messaging_limit,
            "daily_target": daily_target,
            "max_daily_target": max_daily_target,
            "active": bool(self.f_active.value),
            "ready_for_campaigns": bool(self.f_ready.value),
            "rest_start": self._validate_time_field(self.f_rest_start, "Início do repouso"),
            "rest_end": self._validate_time_field(self.f_rest_end, "Fim do repouso"),
            "notes": str(self.f_notes.value or "").strip(),
        }

    def save_number(self, _event: object | None = None) -> None:
        if self.selected_number_id and app_runtime.warmup_is_running(self.selected_number_id):
            common.show_snack(self.app_page, "Pause o aquecimento antes de alterar este número.", error=True)
            return
        try:
            payload = self._form_payload()
            if self.selected_number_id is None:
                self.selected_number_id = warmup.add_number(**payload)
                message = "Número cadastrado com sucesso."
            else:
                warmup.update_number(self.selected_number_id, **payload)
                message = "Número atualizado com sucesso."
            self.progress_msg.value = f"Número #{self.selected_number_id} salvo."
            self.load_data()
            common.show_snack(self.app_page, message)
        except (ValueError, TypeError, warmup.WarmupError) as exc:
            common.safe_update(self.app_page)
            common.show_snack(self.app_page, str(exc), error=True)
        except Exception as exc:
            common.show_snack(self.app_page, f"Não foi possível salvar o número: {exc}", error=True)

    def on_number_selected(self, number_id: int) -> None:
        data = warmup.get_number(number_id)
        if not data:
            common.show_snack(self.app_page, "Esse número não existe mais.", error=True)
            self.load_data()
            return
        self.selected_number_id = int(number_id)
        self.f_name.value = str(data.get("display_name") or "")
        self.f_phone.value = str(data.get("phone") or "")
        self.f_phone_id.value = str(data.get("phone_number_id") or "")
        try:
            self.f_provider.value = warmup.normalize_provider(data.get("provider"))
        except warmup.WarmupError:
            self.f_provider.value = whatsapp.DELIVERY_MODE_OFFICIAL_API
        self.f_status.value = str(data.get("status") or "testing")
        self.f_quality.value = str(data.get("quality_rating") or "unknown")
        self.f_limit.value = str(data.get("messaging_limit") or 250)
        self.f_daily_target.value = str(data.get("daily_target") or warmup.INITIAL_DAILY_TARGET)
        self.f_max_target.value = str(data.get("max_daily_target") or warmup.DEFAULT_MAX_DAILY_TARGET)
        self.f_rest_start.value = str(data.get("rest_start") or "00:00")
        self.f_rest_end.value = str(data.get("rest_end") or "07:00")
        self.f_active.value = bool(_int_value(data.get("active"), 1))
        self.f_ready.value = bool(_int_value(data.get("ready_for_campaigns")))
        self.f_notes.value = str(data.get("notes") or "")
        self._clear_form_errors()

        groups = self._refresh_groups()
        recent_runs = warmup.list_recent_runs(limit=1, number_id=number_id)
        previous_group = str(recent_runs[0].get("group_name") or "") if recent_runs else ""
        if previous_group in groups:
            self.f_group.value = previous_group
        if app_runtime.warmup_is_running(number_id):
            self.progress_bar.visible = True
            self.progress_bar.value = None
            self.progress_msg.value = f"Aquecimento do número #{number_id} em execução."
        else:
            self.progress_bar.visible = False
            self.progress_bar.value = 0
            self.progress_msg.value = f"Número #{number_id} selecionado."
        self._update_runtime_controls()
        common.safe_update(self.app_page)

    def delete_number(self, _event: object | None = None) -> None:
        if self.selected_number_id is None:
            common.show_snack(self.app_page, "Selecione um número primeiro.", error=True)
            return
        number_id = self.selected_number_id
        if app_runtime.warmup_is_running(number_id):
            common.show_snack(self.app_page, "Pause o aquecimento antes de excluir o número.", error=True)
            return

        def confirm_delete(_event: object | None = None) -> None:
            try:
                warmup.delete_number(number_id)
                common.close_dialog(self.app_page)
                self.clear_form()
                self.load_data()
                common.show_snack(self.app_page, "Número e histórico de aquecimento excluídos.")
            except Exception as exc:
                common.show_snack(self.app_page, f"Não foi possível excluir: {exc}", error=True)

        common.show_alert(
            self.app_page,
            "Excluir número",
            "Esta ação exclui o número, suas execuções e seus eventos de aquecimento. Deseja continuar?",
            key="warmup-delete-dialog",
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: common.close_dialog(self.app_page, e)),
                ft.FilledButton(
                    "Excluir definitivamente",
                    icon=ft.Icons.DELETE_FOREVER,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
                    key="warmup-confirm-delete",
                    on_click=confirm_delete,
                ),
            ],
        )

    def start_warmup(self, _event: object | None = None) -> None:
        if self.selected_number_id is None:
            common.show_snack(self.app_page, "Selecione um número na aba Números.", error=True)
            return
        number_id = self.selected_number_id
        if app_runtime.warmup_is_running(number_id):
            common.show_snack(self.app_page, "Este número já está aquecendo.", error=True)
            self._update_runtime_controls()
            return

        group_name = str(self.f_group.value or "").strip()
        if not group_name:
            self.f_group.error_text = "Escolha um grupo com contatos autorizados."
            common.safe_update(self.app_page)
            common.show_snack(self.app_page, self.f_group.error_text, error=True)
            return
        if group_name not in contacts.list_groups():
            self.f_group.error_text = "O grupo selecionado não existe mais. Atualize a tela."
            common.safe_update(self.app_page)
            common.show_snack(self.app_page, self.f_group.error_text, error=True)
            return
        self.f_group.error_text = None

        number = warmup.get_number(number_id)
        if not number:
            common.show_snack(self.app_page, "Esse número não existe mais.", error=True)
            self.load_data()
            return
        try:
            provider = warmup.normalize_provider(number.get("provider"))
            config = whatsapp.load_config()
        except (ValueError, whatsapp.WhatsAppAPIError) as exc:
            common.show_snack(self.app_page, f"Configuração de envio inválida: {exc}", error=True)
            return

        is_real_web = provider == whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL and not bool(config.dry_run)
        if not is_real_web:
            self._begin_warmup(number_id, group_name, explicit_user_confirmation=False)
            return

        acknowledgement = ft.Checkbox(
            label=(
                "Confirmo que os contatos deram opt-in e aceito o risco do modo "
                "experimental não oficial."
            ),
            value=False,
            key="warmup-web-acknowledgement",
        )

        def confirm_web(_event: object | None = None) -> None:
            if not acknowledgement.value:
                acknowledgement.error = True
                common.safe_update(self.app_page)
                common.show_snack(self.app_page, "Marque a confirmação para continuar.", error=True)
                return
            common.close_dialog(self.app_page)
            self._begin_warmup(number_id, group_name, explicit_user_confirmation=True)

        common.show_alert(
            self.app_page,
            "Confirmar aquecimento real via WhatsApp Web",
            ft.Column(
                controls=[
                    ft.Text(
                        "O WhatsApp Web Experimental abrirá o navegador local e enviará mensagens reais. "
                        "A sessão precisa estar conectada por QR Code."
                    ),
                    ft.Text(
                        "Esse modo não usa a API oficial e pode sofrer desconexão, limitação ou bloqueio.",
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ERROR,
                    ),
                    acknowledgement,
                ],
                tight=True,
                spacing=12,
            ),
            key="warmup-web-confirm-dialog",
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: common.close_dialog(self.app_page, e)),
                ft.FilledButton(
                    "Confirmar e iniciar",
                    icon=ft.Icons.PLAY_ARROW,
                    key="warmup-web-confirm-button",
                    on_click=confirm_web,
                ),
            ],
        )

    def _begin_warmup(
        self,
        number_id: int,
        group_name: str,
        *,
        explicit_user_confirmation: bool,
    ) -> None:
        self.progress_bar.visible = True
        self.progress_bar.value = None
        self.progress_msg.value = f"Preparando o aquecimento do número #{number_id}..."
        self.start_button.disabled = True
        self.pause_button.disabled = False
        self.save_button.disabled = True
        self.delete_button.disabled = True
        common.safe_update(self.app_page)

        def on_progress(current: int, total: int, message: str) -> None:
            if self.selected_number_id == number_id:
                self.progress_bar.visible = True
                self.progress_bar.value = (current / total) if total else None
                self.progress_msg.value = f"{current}/{total} · {message}"
                common.safe_update(self.app_page)

        def on_complete(totals: dict[str, int] | None, error: Exception | None) -> None:
            if self.selected_number_id == number_id:
                self.progress_bar.visible = False
                self.progress_bar.value = 0
                if error is not None:
                    self.progress_msg.value = f"Aquecimento interrompido: {error}"
                else:
                    result = totals or {}
                    self.progress_msg.value = (
                        f"Finalizado: {_int_value(result.get('sent'))} enviados, "
                        f"{_int_value(result.get('simulated'))} simulados, "
                        f"{_int_value(result.get('manual'))} manuais, "
                        f"{_int_value(result.get('failed'))} falhas e "
                        f"{_int_value(result.get('skipped'))} ignorados."
                    )
            self.load_data()
            if error is not None:
                common.show_snack(self.app_page, f"Erro no aquecimento: {error}", error=True)
            else:
                common.show_snack(self.app_page, "Aquecimento finalizado; saúde recalculada.")

        started = app_runtime.start_warmup(
            number_id,
            group_name,
            progress_callback=on_progress,
            completion_callback=on_complete,
            explicit_user_confirmation=explicit_user_confirmation,
        )
        if not started:
            self.progress_bar.visible = False
            self.progress_bar.value = 0
            self.progress_msg.value = "O aquecimento já estava em execução."
            self._update_runtime_controls()
            common.safe_update(self.app_page)
            common.show_snack(self.app_page, "Este número já está aquecendo.", error=True)
            return
        self.progress_msg.value = (
            f"Aquecimento do número #{number_id} iniciado com o grupo {group_name}. "
            "Você pode navegar para outra tela."
        )
        self._update_runtime_controls()
        common.safe_update(self.app_page)
        common.show_snack(self.app_page, "Aquecimento iniciado em segundo plano.")

    def stop_warmup(self, _event: object | None = None) -> None:
        if self.selected_number_id is None:
            common.show_snack(self.app_page, "Selecione um número primeiro.", error=True)
            return
        if not app_runtime.stop_warmup(self.selected_number_id):
            self._update_runtime_controls()
            common.safe_update(self.app_page)
            common.show_snack(self.app_page, "Este número não está aquecendo.", error=True)
            return
        self.pause_button.disabled = True
        self.progress_bar.visible = True
        self.progress_bar.value = None
        self.progress_msg.value = "Pausa solicitada; qualquer espera entre mensagens foi interrompida."
        common.safe_update(self.app_page)
        common.show_snack(self.app_page, "Pausa imediata solicitada.", bgcolor=ft.Colors.AMBER_800)

    def _update_runtime_controls(self) -> None:
        running = bool(
            self.selected_number_id is not None and app_runtime.warmup_is_running(self.selected_number_id)
        )
        selected = self.selected_number_id is not None
        self.start_button.disabled = not selected or running
        self.pause_button.disabled = not running
        self.save_button.disabled = running
        self.delete_button.disabled = not selected or running

    def load_data(self, _event: object | None = None) -> None:
        try:
            self._refresh_groups()
            stats = warmup.dashboard_stats()
            self.stat_total.value = str(_int_value(stats.get("total")))
            self.stat_active.value = str(_int_value(stats.get("active")))
            self.stat_ready.value = str(_int_value(stats.get("ready")))
            self.stat_paused.value = str(_int_value(stats.get("paused")))

            numbers = warmup.list_numbers()
            existing_ids = {int(item["id"]) for item in numbers}
            if self.selected_number_id is not None and self.selected_number_id not in existing_ids:
                self.clear_form()
            self.numbers_empty.visible = not numbers
            self.numbers_table.rows = [self._number_row(item) for item in numbers]

            runs = warmup.list_recent_runs(limit=100)
            self.runs_empty.visible = not runs
            self.runs_table.rows = [self._run_row(item) for item in runs]

            events = warmup.list_recent_events(limit=200)
            self.events_empty.visible = not events
            self.events_table.rows = [self._event_row(item) for item in events]
            self._update_runtime_controls()
        except Exception as exc:
            common.show_snack(self.app_page, f"Erro ao carregar o aquecimento: {exc}", error=True)
        common.safe_update(self.app_page)

    def _number_row(self, item: dict[str, Any]) -> ft.DataRow:
        number_id = int(item["id"])
        running = app_runtime.warmup_is_running(number_id)
        ready = bool(_int_value(item.get("ready_for_campaigns")))
        return ft.DataRow(
            key=f"warmup-number-row-{number_id}",
            cells=[
                ft.DataCell(ft.Text(str(item.get("display_name") or ""))),
                ft.DataCell(ft.Text(str(item.get("phone") or ""), selectable=True)),
                ft.DataCell(ft.Text(friendly_provider(item.get("provider")))),
                ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                ft.DataCell(ft.Text(str(_int_value(item.get("health_score"), 100)))),
                ft.DataCell(ft.Text(friendly_quality(item.get("quality_rating")))),
                ft.DataCell(
                    ft.Text(
                        str(
                            _int_value(
                                item.get("current_daily_target"),
                                _int_value(item.get("daily_target"), warmup.INITIAL_DAILY_TARGET),
                            )
                        )
                    )
                ),
                ft.DataCell(ft.Text(str(_int_value(item.get("sent_today"))))),
                ft.DataCell(
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if ready else ft.Icons.CANCEL_OUTLINED,
                        color=ft.Colors.GREEN if ready else ft.Colors.GREY,
                        tooltip="Pronto para campanhas" if ready else "Ainda não está pronto",
                    )
                ),
                ft.DataCell(
                    ft.Row(
                        [
                            ft.ProgressRing(width=18, height=18, stroke_width=2, visible=running),
                            ft.Text("Aquecendo" if running else "Parado"),
                        ],
                        spacing=6,
                    )
                ),
                ft.DataCell(
                    ft.TextButton(
                        "Editar",
                        icon=ft.Icons.EDIT,
                        key=f"warmup-edit-{number_id}",
                        on_click=lambda _e, value=number_id: self.on_number_selected(value),
                    )
                ),
            ],
        )

    @staticmethod
    def _run_row(item: dict[str, Any]) -> ft.DataRow:
        return ft.DataRow(
            key=f"warmup-run-row-{item.get('id')}",
            cells=[
                ft.DataCell(ft.Text(_format_datetime(item.get("started_at")))),
                ft.DataCell(ft.Text(str(item.get("number_name") or ""))),
                ft.DataCell(ft.Text(str(item.get("group_name") or "-"))),
                ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                ft.DataCell(ft.Text(str(_int_value(item.get("target_contacts"))))),
                ft.DataCell(ft.Text(str(_int_value(item.get("sent"))))),
                ft.DataCell(ft.Text(str(_int_value(item.get("simulated"))))),
                ft.DataCell(ft.Text(str(_int_value(item.get("manual"))))),
                ft.DataCell(ft.Text(str(_int_value(item.get("failed"))))),
                ft.DataCell(ft.Text(str(_int_value(item.get("skipped"))))),
                ft.DataCell(ft.Text(_format_datetime(item.get("finished_at")))),
            ],
        )

    def _event_row(self, item: dict[str, Any]) -> ft.DataRow:
        action_url = str(item.get("action_url") or "").strip()
        error = str(item.get("error_message") or "").strip()
        provider_id = str(item.get("provider_message_id") or "").strip()
        detail = error or provider_id or "-"
        action: ft.Control = ft.Text("-")
        if action_url:
            action = ft.TextButton(
                "Abrir WhatsApp",
                icon=ft.Icons.OPEN_IN_NEW,
                on_click=lambda _e, url=action_url: common.open_url(self.app_page, url),
            )
        return ft.DataRow(
            key=f"warmup-event-row-{item.get('id')}",
            cells=[
                ft.DataCell(ft.Text(_format_datetime(item.get("created_at")))),
                ft.DataCell(ft.Text(str(item.get("number_name") or ""))),
                ft.DataCell(ft.Text(str(item.get("recipient_name") or ""))),
                ft.DataCell(ft.Text(str(item.get("phone") or ""), selectable=True)),
                ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                ft.DataCell(ft.Text(detail, tooltip=detail)),
                ft.DataCell(action),
            ],
        )

    def did_mount(self) -> None:
        self.load_data()
