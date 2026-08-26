from __future__ import annotations

from datetime import datetime
from typing import Any

import flet as ft

import campaigns
import compliance
import whatsapp
from runtime import app_runtime
from screens import common
from screens.campaigns import (
    DELIVERY_MODE_OPTIONS,
    _totals_message,
    campaign_primary_action,
    friendly_status,
    parse_datetime,
    request_campaign_start,
)


TERMINAL_STATUSES = {
    campaigns.CAMPAIGN_STATUS_DONE,
    campaigns.CAMPAIGN_STATUS_DONE_LEGACY,
    campaigns.CAMPAIGN_STATUS_CANCELLED,
    campaigns.CAMPAIGN_STATUS_ERROR,
    campaigns.CAMPAIGN_STATUS_FAILED,
    campaigns.CAMPAIGN_STATUS_MANUAL_PENDING,
}


class ScheduleScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route=common.ROUTE_SCHEDULE, padding=0)
        self.app_page = page
        self.selected_campaign_id: int | None = None
        self.campaign_by_id: dict[int, dict[str, Any]] = {}

        self.agent_status = ft.Text(
            "Agente: carregando…", key="schedule-agent-status",
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self.web_status = ft.Text(
            "WhatsApp Web: carregando…", key="schedule-web-status",
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self.active_status = ft.Text(
            "", key="schedule-active-status", color=ft.Colors.ON_SURFACE_VARIANT,
        )
        status_bar = ft.Container(
            padding=12, border_radius=8, bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Row(
                [self.agent_status, ft.VerticalDivider(), self.web_status,
                 ft.VerticalDivider(), self.active_status],
                wrap=True,
            ),
            key="schedule-status-bar",
        )

        self.refresh_button = ft.Button(
            "Atualizar", icon=ft.Icons.REFRESH, key="schedule-refresh",
            on_click=self.load_campaigns,
        )
        self.primary_button = ft.Button(
            "Iniciar", icon=ft.Icons.PLAY_ARROW, key="schedule-primary-action",
            bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, disabled=True,
            on_click=self.run_primary_action,
        )
        self.schedule_button = ft.Button(
            "Agendar", icon=ft.Icons.SCHEDULE, key="schedule-set-time",
            disabled=True, on_click=self.schedule_selected,
        )
        self.pause_button = ft.Button(
            "Pausar", icon=ft.Icons.PAUSE, key="schedule-pause",
            disabled=True, on_click=self.pause_selected,
        )
        self.cancel_button = ft.Button(
            "Cancelar", icon=ft.Icons.CANCEL, key="schedule-cancel",
            color=ft.Colors.ERROR, disabled=True, on_click=self.cancel_selected,
        )
        self.resend_button = ft.Button(
            "Clonar / Reenviar", icon=ft.Icons.CONTENT_COPY, key="schedule-resend",
            disabled=True, on_click=self.resend_campaign,
        )
        self.history_button = ft.Button(
            "Histórico", icon=ft.Icons.LIST_ALT, key="schedule-history",
            disabled=True, on_click=self.show_campaign_history,
        )
        self.detail_button = ft.Button(
            "Ver campanha", icon=ft.Icons.VISIBILITY, key="schedule-detail",
            disabled=True, on_click=self.show_campaign_detail,
        )
        action_bar = ft.Row(
            [self.refresh_button, self.primary_button, self.schedule_button,
             self.pause_button, self.cancel_button, self.resend_button,
             self.history_button, self.detail_button],
            wrap=True, spacing=8, key="schedule-actions",
        )

        self.campaigns_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")), ft.DataColumn(ft.Text("Campanha")),
                ft.DataColumn(ft.Text("Status")), ft.DataColumn(ft.Text("Risco")),
                ft.DataColumn(ft.Text("Modo")), ft.DataColumn(ft.Text("Agendamento")),
                ft.DataColumn(ft.Text("Pasta")), ft.DataColumn(ft.Text("Delay")),
                ft.DataColumn(ft.Text("Progresso")), ft.DataColumn(ft.Text("Atualizada")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[], border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, key="schedule-table",
        )
        self.empty_text = ft.Text(
            "", key="schedule-empty", italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

        self.edit_name = ft.TextField(
            label="Nome da campanha", key="schedule-edit-name", expand=True
        )
        self.edit_scheduled_at = ft.TextField(
            label="Agendamento (AAAA-MM-DD HH:MM)", key="schedule-edit-time",
            width=260,
        )
        self.edit_delay_min = ft.TextField(
            label="Delay mín. (s)", key="schedule-edit-delay-min", width=125,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.edit_delay_max = ft.TextField(
            label="Delay máx. (s)", key="schedule-edit-delay-max", width=125,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.edit_delivery_mode = ft.Dropdown(
            label="Modo de envio", key="schedule-edit-mode", width=250,
            options=[ft.dropdown.Option(value, label) for value, label in DELIVERY_MODE_OPTIONS],
        )
        self.save_button = ft.Button(
            "Salvar alterações", icon=ft.Icons.SAVE, key="schedule-save",
            bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE,
            disabled=True, on_click=self.save_changes,
        )
        self.edit_details = ft.Text(
            "Nenhuma campanha selecionada.", key="schedule-selection-details",
            color=ft.Colors.ON_SURFACE_VARIANT, selectable=True,
        )
        self.progress_text = ft.Text(
            "Escolha uma campanha.", key="schedule-progress",
            color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD,
        )
        edit_panel = ft.Container(
            padding=16, bgcolor=ft.Colors.SURFACE_CONTAINER, border_radius=10,
            key="schedule-edit-panel",
            content=ft.Column(
                [self.edit_details,
                 ft.Row(
                     [self.edit_name, self.edit_scheduled_at, self.edit_delay_min,
                      self.edit_delay_max, self.edit_delivery_mode, self.save_button],
                     wrap=True, spacing=8,
                 ),
                 self.progress_text],
                spacing=10,
            ),
        )

        body = ft.Column(
            [status_bar, action_bar, self.empty_text,
             ft.ListView([self.campaigns_table], expand=True), edit_panel],
            spacing=10, expand=True, key="schedule-body",
        )
        self.controls = [common.screen_layout(
            page, common.ROUTE_SCHEDULE, "Central de envios e agendamentos", body,
            subtitle="Inicie, acompanhe, pause, cancele, edite ou clone campanhas.",
            actions=[ft.Button(
                "Nova campanha", icon=ft.Icons.ADD,
                key="schedule-new-campaign",
                on_click=lambda _e: page.go(common.ROUTE_CAMPAIGNS),
            )],
        )]
        self.load_campaigns(update_page=False)

    @staticmethod
    def _progress_label(item: dict[str, Any]) -> str:
        total = int(item.get("total_contacts") or 0)
        processed = int(item.get("processed_contacts") or 0)
        percent = int(item.get("progress_percent") or 0)
        return f"{percent}% ({processed}/{total})" if total else "0% (0/0)"

    @staticmethod
    def _delay_label(item: dict[str, Any]) -> str:
        minimum = int(item.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS)
        maximum = int(item.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS)
        return f"{minimum}-{maximum}s"

    def _get_selected_id(self) -> int | None:
        if self.selected_campaign_id is None:
            common.show_snack(
                self.app_page, "Selecione uma campanha na tabela primeiro.", error=True
            )
            return None
        return int(self.selected_campaign_id)

    def refresh_agent_status(self) -> None:
        items = list(self.campaign_by_id.values())
        running = [
            int(item["id"]) for item in items
            if app_runtime.campaign_is_running(int(item["id"]))
        ]
        if running:
            self.agent_status.value = f"Agente: enviando campanhas {running}"
        else:
            try:
                due = len(campaigns.get_due_campaigns())
            except Exception:
                due = 0
            self.agent_status.value = (
                f"Agente: {due} campanha(s) aguardando" if due
                else "Agente: ativo, sem envio no momento"
            )
        try:
            snapshot = whatsapp.get_whatsapp_web_status()
            self.web_status.value = f"WhatsApp Web: {snapshot.get('label') or snapshot.get('status') or 'desconhecido'}"
        except Exception as exc:
            self.web_status.value = f"WhatsApp Web: indisponível ({exc})"
        sending = [
            item for item in items
            if str(item.get("status") or "") == campaigns.CAMPAIGN_STATUS_SENDING
        ]
        if sending:
            item = sending[0]
            self.active_status.value = (
                f"{item.get('name') or ''}: {int(item.get('sent_contacts') or 0)}/"
                f"{int(item.get('total_contacts') or 0)} enviados, "
                f"{int(item.get('failed_contacts') or 0)} falhas"
            )
        else:
            self.active_status.value = ""

    def load_campaigns(
        self,
        _event: object | None = None,
        *,
        select_id: int | None = None,
        update_page: bool = True,
    ) -> None:
        current = select_id or self.selected_campaign_id
        self.campaign_by_id.clear()
        self.campaigns_table.rows.clear()
        try:
            items = campaigns.list_campaigns()
            self.empty_text.value = (
                "" if items
                else "Nenhuma campanha criada. Use Nova campanha para começar."
            )
            for item in items:
                campaign_id = int(item["id"])
                try:
                    item["risk_score"] = int(
                        compliance.refresh_campaign_risk(campaign_id).get("score") or 0
                    )
                except Exception:
                    item["risk_score"] = int(item.get("risk_score") or 0)
                self.campaign_by_id[campaign_id] = item
                self.campaigns_table.rows.append(ft.DataRow(
                    data=campaign_id, key=f"schedule-row-{campaign_id}",
                    selected=False,
                    on_select_change=lambda _e, cid=campaign_id: self.select_campaign(cid),
                    cells=[
                        ft.DataCell(ft.Text(str(campaign_id))),
                        ft.DataCell(ft.Text(str(item.get("name") or ""))),
                        ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                        ft.DataCell(ft.Text(f"{item['risk_score']}%")),
                        ft.DataCell(ft.Text(whatsapp.delivery_mode_label(item.get("delivery_mode")))),
                        ft.DataCell(ft.Text(str(item.get("scheduled_at") or ""))),
                        ft.DataCell(ft.Text(str(item.get("folder_name") or "Campanha antiga"))),
                        ft.DataCell(ft.Text(self._delay_label(item))),
                        ft.DataCell(ft.Text(self._progress_label(item))),
                        ft.DataCell(ft.Text(str(item.get("updated_at") or "")[:19])),
                        ft.DataCell(ft.TextButton(
                            "Selecionar", key=f"schedule-select-{campaign_id}",
                            on_click=lambda _e, cid=campaign_id: self.select_campaign(cid),
                        )),
                    ],
                ))
        except Exception as exc:
            self.empty_text.value = f"Erro ao carregar campanhas: {exc}"
            items = []

        requested = current or getattr(
            self.app_page, "mezzold_selected_campaign_id", None
        )
        if requested not in self.campaign_by_id and items:
            requested = int(items[0]["id"])
        setattr(self.app_page, "mezzold_selected_campaign_id", None)
        if requested in self.campaign_by_id:
            self.select_campaign(int(requested), update_page=False)
        else:
            self._clear_selection()
        self.refresh_agent_status()
        if update_page:
            common.safe_update(self.app_page)

    def _clear_selection(self) -> None:
        self.selected_campaign_id = None
        self.edit_name.value = ""
        self.edit_scheduled_at.value = ""
        self.edit_delay_min.value = ""
        self.edit_delay_max.value = ""
        self.edit_delivery_mode.value = None
        self.edit_details.value = "Nenhuma campanha selecionada."
        self.progress_text.value = "Escolha uma campanha."
        self._update_action_state(None)

    def select_campaign(self, campaign_id: int, *, update_page: bool = True) -> None:
        item = self.campaign_by_id.get(int(campaign_id))
        if not item:
            common.show_snack(self.app_page, "Campanha não encontrada.", error=True)
            return
        self.selected_campaign_id = int(campaign_id)
        for row in self.campaigns_table.rows:
            row.selected = int(row.data) == int(campaign_id)
        self.edit_name.value = str(item.get("name") or "")
        self.edit_scheduled_at.value = str(item.get("scheduled_at") or "")
        self.edit_delay_min.value = str(
            item.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS
        )
        self.edit_delay_max.value = str(
            item.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS
        )
        self.edit_delivery_mode.value = whatsapp.normalize_delivery_mode(
            item.get("delivery_mode")
        )
        self.edit_details.value = (
            f"Campanha #{campaign_id} | Status: {friendly_status(item.get('status'))} | "
            f"Pasta: {item.get('folder_name') or 'Campanha antiga'} | "
            f"Modo: {whatsapp.delivery_mode_label(item.get('delivery_mode'))} | "
            f"Risco: {int(item.get('risk_score') or 0)}% | "
            f"Total: {int(item.get('total_contacts') or 0)} | "
            f"Enviados: {int(item.get('sent_contacts') or 0)} | "
            f"Falhas: {int(item.get('failed_contacts') or 0)}"
        )
        action = campaign_primary_action(item.get("status"))
        self.progress_text.value = str(action.get("message") or self._progress_label(item))
        self._update_action_state(item)
        if update_page:
            common.safe_update(self.app_page)

    def _update_action_state(self, item: dict[str, Any] | None) -> None:
        selected = item is not None
        status = str(item.get("status") or "") if item else ""
        action = campaign_primary_action(status)
        self.primary_button.content = str(action["label"])
        self.primary_button.disabled = not bool(action["enabled"])
        terminal = status in TERMINAL_STATUSES
        self.schedule_button.disabled = not selected or terminal or status == campaigns.CAMPAIGN_STATUS_SENDING
        self.pause_button.disabled = (
            not selected
            or terminal
            or status in {campaigns.CAMPAIGN_STATUS_DRAFT, campaigns.CAMPAIGN_STATUS_PAUSED}
        )
        self.cancel_button.disabled = not selected or terminal
        self.resend_button.disabled = not selected
        self.history_button.disabled = not selected
        self.detail_button.disabled = not selected
        self.save_button.disabled = not selected or terminal or status == campaigns.CAMPAIGN_STATUS_SENDING

    def run_primary_action(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        item = self.campaign_by_id.get(campaign_id) or {}
        action = campaign_primary_action(item.get("status"))
        if not action["enabled"]:
            common.show_snack(
                self.app_page, str(action.get("message") or "Ação indisponível."),
                error=True,
            )
            return
        self._request_selected_start(bool(action["allow_resume"]))

    def start_campaign(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is not None:
            self._request_selected_start(False)

    def continue_campaign(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is not None:
            self._request_selected_start(True)

    def _request_selected_start(self, allow_resume: bool) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        dry_run = bool(whatsapp.load_config().dry_run)

        def progress(current: int, total: int, message: str) -> None:
            if dry_run:
                return
            self.progress_text.value = f"{current}/{total} - {message}"
            common.safe_update(self.app_page)

        def completed(
            totals: dict[str, int] | None, error: Exception | None
        ) -> None:
            if error is not None:
                self.progress_text.value = f"Erro na campanha #{campaign_id}: {error}"
            else:
                self.progress_text.value = _totals_message(campaign_id, totals)
            self.load_campaigns(select_id=campaign_id, update_page=False)
            common.safe_update(self.app_page)

        def started() -> None:
            if dry_run:
                return
            self.progress_text.value = f"Campanha #{campaign_id} em andamento…"
            self.load_campaigns(select_id=campaign_id, update_page=False)
            common.safe_update(self.app_page)

        request_campaign_start(
            self.app_page, campaign_id, allow_resume=allow_resume,
            runner="ui_continue" if allow_resume else "ui_manual",
            progress_callback=progress, completion_callback=completed,
            on_started=started,
        )

    def schedule_selected(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        try:
            scheduled_at = parse_datetime(str(self.edit_scheduled_at.value or ""))
            campaigns.schedule_campaign(campaign_id, scheduled_at)
        except Exception as exc:
            common.show_snack(self.app_page, f"Não foi possível agendar: {exc}", error=True)
            return
        self.load_campaigns(select_id=campaign_id, update_page=False)
        common.show_snack(self.app_page, f"Campanha #{campaign_id} agendada para {scheduled_at}.")
        self._warn_web_schedule_if_needed(campaign_id)
        common.safe_update(self.app_page)

    def _warn_web_schedule_if_needed(self, campaign_id: int) -> None:
        item = campaigns.get_campaign(campaign_id) or {}
        if (
            whatsapp.normalize_delivery_mode(item.get("delivery_mode"))
            != whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL
            or whatsapp.load_config().dry_run
        ):
            return
        common.show_alert(
            self.app_page, "Confirmação manual necessária",
            "Por segurança, o envio real via WhatsApp Web não recebe confirmação automática. "
            "No horário, selecione a campanha, clique em Iniciar e confirme o aviso.",
            key="schedule-web-warning",
        )

    def pause_selected(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        try:
            app_runtime.pause_campaign(campaign_id)
            self.progress_text.value = f"Campanha #{campaign_id} pausada."
            self.load_campaigns(select_id=campaign_id, update_page=False)
            common.show_snack(self.app_page, "Campanha pausada.")
        except Exception as exc:
            common.show_snack(self.app_page, f"Não foi possível pausar: {exc}", error=True)
        common.safe_update(self.app_page)

    def cancel_selected(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return

        def confirm_cancel(_event: object | None = None) -> None:
            common.close_dialog(self.app_page)
            try:
                app_runtime.cancel_campaign(campaign_id)
                self.progress_text.value = f"Campanha #{campaign_id} cancelada."
                self.load_campaigns(select_id=campaign_id, update_page=False)
                common.show_snack(self.app_page, "Campanha cancelada e envio interrompido.")
            except Exception as exc:
                common.show_snack(
                    self.app_page, f"Não foi possível cancelar: {exc}", error=True
                )
            common.safe_update(self.app_page)

        common.show_alert(
            self.app_page, "Cancelar campanha",
            "Cancelar esta campanha? Os destinatários ainda pendentes não serão enviados.",
            actions=[
                ft.TextButton(
                    "Voltar", key="schedule-cancel-back",
                    on_click=lambda e: common.close_dialog(self.app_page, e),
                ),
                ft.Button(
                    "Cancelar campanha", icon=ft.Icons.CANCEL,
                    key="schedule-cancel-confirm", bgcolor=ft.Colors.ERROR,
                    color=ft.Colors.ON_ERROR, on_click=confirm_cancel,
                ),
            ],
            key="schedule-cancel-dialog",
        )

    def resend_campaign(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        try:
            new_campaign_id = campaigns.duplicate_campaign_for_resend(campaign_id)
            duplicate = campaigns.get_campaign(new_campaign_id) or {}
            self.load_campaigns(select_id=new_campaign_id, update_page=False)
            common.show_snack(
                self.app_page,
                f"Campanha clonada para reenvio: {duplicate.get('name') or new_campaign_id}.",
            )
        except Exception as exc:
            common.show_snack(self.app_page, f"Não foi possível clonar: {exc}", error=True)
        common.safe_update(self.app_page)

    def _validated_edit(self) -> dict[str, Any] | None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return None
        name = str(self.edit_name.value or "").strip()
        if not name:
            common.show_snack(self.app_page, "Informe o nome da campanha.", error=True)
            return None
        try:
            scheduled_at = (
                parse_datetime(str(self.edit_scheduled_at.value))
                if str(self.edit_scheduled_at.value or "").strip() else ""
            )
            d_min, d_max = campaigns.normalize_campaign_delay(
                self.edit_delay_min.value, self.edit_delay_max.value
            )
            delivery_mode = whatsapp.normalize_delivery_mode(self.edit_delivery_mode.value)
        except Exception as exc:
            common.show_snack(self.app_page, str(exc), error=True)
            return None
        return {
            "campaign_id": campaign_id, "name": name,
            "scheduled_at": scheduled_at, "delay_min_seconds": d_min,
            "delay_max_seconds": d_max, "delivery_mode": delivery_mode,
        }

    def save_changes(self, _event: object | None = None) -> None:
        payload = self._validated_edit()
        if payload is None:
            return
        level, message = campaigns.delay_recommendation_message(
            payload["delay_min_seconds"], payload["delay_max_seconds"]
        )
        if level != "alto":
            self._save_changes_impl(payload)
            return

        def confirm_save(_event: object | None = None) -> None:
            common.close_dialog(self.app_page)
            self._save_changes_impl(payload)

        common.show_alert(
            self.app_page, "Delay com risco alto",
            f"{message}\n\nDeseja salvar esse intervalo mesmo assim?",
            actions=[
                ft.TextButton(
                    "Revisar", key="schedule-delay-risk-back",
                    on_click=lambda e: common.close_dialog(self.app_page, e),
                ),
                ft.Button(
                    "Salvar mesmo assim", key="schedule-delay-risk-confirm",
                    on_click=confirm_save,
                ),
            ],
            key="schedule-delay-risk-dialog",
        )

    def _save_changes_impl(self, payload: dict[str, Any]) -> None:
        campaign_id = int(payload["campaign_id"])
        details = {key: value for key, value in payload.items() if key != "campaign_id"}
        try:
            campaigns.update_campaign_details(campaign_id, **details)
            self.load_campaigns(select_id=campaign_id, update_page=False)
            common.show_snack(self.app_page, "Campanha atualizada.")
            if details.get("scheduled_at"):
                self._warn_web_schedule_if_needed(campaign_id)
        except Exception as exc:
            common.show_snack(
                self.app_page, f"Não foi possível salvar: {exc}", error=True
            )
        common.safe_update(self.app_page)

    def show_campaign_detail(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        try:
            campaign = campaigns.get_campaign(campaign_id)
            contact_list = campaigns.get_campaign_contacts(campaign_id)
            variants = campaigns.get_campaign_variants(campaign_id)
            if not campaign:
                raise campaigns.CampaignError("Campanha não encontrada.")
        except Exception as exc:
            common.show_snack(self.app_page, f"Erro ao abrir campanha: {exc}", error=True)
            return

        contacts_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Contato")), ft.DataColumn(ft.Text("Telefone")),
                     ft.DataColumn(ft.Text("Status")), ft.DataColumn(ft.Text("Último erro"))],
            rows=[ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(item.get("name") or item.get("recipient_name") or ""))),
                ft.DataCell(ft.Text(str(item.get("phone") or ""))),
                ft.DataCell(ft.Text(friendly_status(item.get("campaign_status") or item.get("status")))),
                ft.DataCell(ft.Text(str(item.get("last_error") or "")[:120])),
            ]) for item in contact_list],
        )
        variant_controls: list[ft.Control] = []
        for index, variant in enumerate(variants, start=1):
            variant_controls.append(ft.Container(
                padding=8, border_radius=6, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                content=ft.Text(
                    f"Variação {index}: {variant.get('body') or ''}\n"
                    f"Mídia: {variant.get('media_path') or 'sem mídia'}",
                    selectable=True,
                ),
            ))
        media = str(campaign.get("media_path") or "").strip()
        body_controls: list[ft.Control] = [
            ft.Text(
                f"{campaign.get('name') or ''}\n"
                f"Status: {friendly_status(campaign.get('status'))} | "
                f"Pasta: {campaign.get('folder_name') or 'Campanha antiga'} | "
                f"Modo: {whatsapp.delivery_mode_label(campaign.get('delivery_mode'))}\n"
                f"Agendamento: {campaign.get('scheduled_at') or ''} | "
                f"Template: {campaign.get('template_name') or 'nenhum'} "
                f"({campaign.get('template_language') or 'pt_BR'}) | "
                f"Delay: {self._delay_label(campaign)}",
                selectable=True,
            ),
            ft.Divider(), ft.Text("Mensagem", weight=ft.FontWeight.BOLD),
            ft.Text(str(campaign.get("message") or ""), selectable=True),
        ]
        if media:
            body_controls.append(ft.Button(
                "Abrir mídia principal", icon=ft.Icons.OPEN_IN_NEW,
                key="schedule-open-main-media",
                on_click=lambda _e, value=media: common.open_url(self.app_page, value),
            ))
        if variant_controls:
            body_controls.extend([
                ft.Divider(), ft.Text("Variações", weight=ft.FontWeight.BOLD),
                *variant_controls,
            ])
        body_controls.extend([
            ft.Divider(), ft.Text("Destinatários", weight=ft.FontWeight.BOLD),
            contacts_table if contact_list else ft.Text("Sem contatos associados."),
        ])
        common.show_alert(
            self.app_page, f"Campanha #{campaign_id}",
            ft.Container(width=880, height=520, content=ft.ListView(body_controls, spacing=8)),
            key="schedule-detail-dialog",
        )

    def show_campaign_history(self, _event: object | None = None) -> None:
        campaign_id = self._get_selected_id()
        if campaign_id is None:
            return
        try:
            logs = campaigns.list_campaign_logs(campaign_id)
        except Exception as exc:
            common.show_snack(self.app_page, f"Erro ao abrir histórico: {exc}", error=True)
            return
        rows: list[ft.DataRow] = []
        for index, log in enumerate(logs):
            url = str(log.get("action_url") or "").strip()
            action: ft.Control = ft.Text("")
            if url:
                action = ft.TextButton(
                    "Abrir", icon=ft.Icons.OPEN_IN_NEW,
                    key=f"schedule-manual-link-{index}",
                    on_click=lambda _e, value=url: common.open_url(self.app_page, value),
                )
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(log.get("created_at") or "")[:19])),
                ft.DataCell(ft.Text(str(log.get("recipient_name") or ""))),
                ft.DataCell(ft.Text(str(log.get("phone") or ""))),
                ft.DataCell(ft.Text(friendly_status(log.get("status")))),
                ft.DataCell(ft.Text(whatsapp.delivery_mode_label(log.get("delivery_mode")))),
                ft.DataCell(action),
                ft.DataCell(ft.Text(str(log.get("error_message") or "")[:120])),
            ]))
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Data/hora")), ft.DataColumn(ft.Text("Contato")),
                ft.DataColumn(ft.Text("Telefone")), ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Modo")), ft.DataColumn(ft.Text("Manual")),
                ft.DataColumn(ft.Text("Erro")),
            ],
            rows=rows,
        )
        common.show_alert(
            self.app_page, f"Histórico da campanha #{campaign_id}",
            ft.Container(
                width=950, height=480,
                content=ft.ListView(
                    [table] if rows else [ft.Text("Esta campanha ainda não tem histórico.")]
                ),
            ),
            key="schedule-history-dialog",
        )

    def did_mount(self) -> None:
        self.load_campaigns()
