from __future__ import annotations

import asyncio
import base64
import re
from datetime import datetime
from typing import Any, Callable

import flet as ft

import campaigns
import compliance
import contacts
import database
import network
import whatsapp
from runtime import app_runtime
from screens import common


STATUS_LABELS = {
    "rascunho": "Rascunho", "agendada": "Agendada", "enviando": "Em andamento",
    "concluída": "Concluída", "concluida": "Concluída", "pausada": "Pausada",
    "cancelada": "Cancelada", "enviado": "Enviado", "simulado": "Teste",
    "pendente_manual": "Aguardando envio manual", "aguardando_manual": "Aguardando envio manual",
    "erro": "Erro", "falhou": "Erro", "bloqueado": "Bloqueado",
    "sem_autorizacao": "Sem autorização",
}

CATEGORY_OPTIONS = {
    "Marketing": "marketing",
    "Aviso ou serviço": "utility",
    "Código de acesso": "authentication",
    "Atendimento": "service",
}

DELIVERY_MODE_OPTIONS = (
    (whatsapp.DELIVERY_MODE_OFFICIAL_API, "API Oficial Meta"),
    (whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL, "WhatsApp Web Experimental"),
    (whatsapp.DELIVERY_MODE_MANUAL_ASSISTED, "Manual assistido"),
)


def friendly_status(value: object) -> str:
    text = str(value or "").strip()
    return STATUS_LABELS.get(text, text)


def parse_datetime(value: str) -> str:
    text = str(value or "").strip()
    for fmt in (
        "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    raise campaigns.CampaignError(
        "Use data no formato AAAA-MM-DD HH:MM ou DD/MM/AAAA HH:MM."
    )


def parse_variants(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    blocks = [block.strip() for block in text.split("\n---\n") if block.strip()]
    if len(blocks) > 1:
        return blocks
    return [line.strip() for line in text.splitlines() if line.strip()]


def campaign_primary_action(status: object) -> dict[str, object]:
    value = str(status or "").strip()
    if value == campaigns.CAMPAIGN_STATUS_PAUSED:
        return {"label": "Continuar", "enabled": True, "allow_resume": True, "message": ""}
    if value in {campaigns.CAMPAIGN_STATUS_DRAFT, campaigns.CAMPAIGN_STATUS_SCHEDULED}:
        return {"label": "Iniciar", "enabled": True, "allow_resume": False, "message": ""}
    if value in {campaigns.CAMPAIGN_STATUS_DONE, campaigns.CAMPAIGN_STATUS_DONE_LEGACY}:
        return {
            "label": "Concluída", "enabled": False, "allow_resume": False,
            "message": "Campanha concluída não pode ser reiniciada. Use Reenviar para criar uma nova campanha.",
        }
    if value == campaigns.CAMPAIGN_STATUS_CANCELLED:
        return {
            "label": "Cancelada", "enabled": False, "allow_resume": False,
            "message": "Campanha cancelada não pode continuar diretamente. Use Reenviar para criar uma nova campanha.",
        }
    if value == campaigns.CAMPAIGN_STATUS_SENDING:
        return {
            "label": "Em andamento", "enabled": False, "allow_resume": False,
            "message": "Campanha já está em andamento.",
        }
    return {
        "label": "Iniciar", "enabled": False, "allow_resume": False,
        "message": f"Campanha com status '{value}' não está liberada para início.",
    }


def _totals_message(campaign_id: int, totals: dict[str, int] | None) -> str:
    values = totals or {}
    return (
        f"Campanha #{campaign_id} finalizada: "
        f"{int(values.get('enviado', 0))} enviados, "
        f"{int(values.get('simulado', 0))} simulados, "
        f"{int(values.get('pendente_manual', 0))} manuais e "
        f"{int(values.get('falhou', 0))} falhas."
    )


def request_campaign_start(
    page: ft.Page,
    campaign_id: int,
    *,
    allow_resume: bool = False,
    runner: str = "ui",
    progress_callback: Callable[[int, int, str], None] | None = None,
    completion_callback: Callable[[dict[str, int] | None, Exception | None], None] | None = None,
    on_started: Callable[[], None] | None = None,
) -> bool:
    """Run V1 preflights, explicit confirmations and then the shared runtime."""

    campaign_id = int(campaign_id)
    try:
        can_start, reason = campaigns.can_start_campaign(campaign_id, allow_resume=allow_resume)
        if not can_start:
            common.show_snack(page, reason, error=True)
            return False
        campaign = campaigns.get_campaign(campaign_id)
        if not campaign:
            raise campaigns.CampaignError("Campanha não encontrada.")
        config = whatsapp.load_config()
        delivery_mode = whatsapp.normalize_delivery_mode(
            campaign.get("delivery_mode") or config.delivery_mode
        )
        if not config.dry_run and not network.has_internet():
            common.show_snack(
                page,
                "Sem internet. O envio não foi iniciado; tente novamente quando a conexão voltar.",
                error=True,
            )
            return False
        risk = compliance.refresh_campaign_risk(campaign_id)
    except Exception as exc:
        common.show_snack(page, f"Não foi possível preparar o envio: {exc}", error=True)
        return False

    def completed(totals: dict[str, int] | None, error: Exception | None) -> None:
        if completion_callback:
            completion_callback(totals, error)
        elif error is not None:
            common.show_snack(page, f"Erro no envio da campanha #{campaign_id}: {error}", error=True)
        else:
            common.show_snack(page, _totals_message(campaign_id, totals))

    def launch(explicit_confirmation: bool) -> None:
        started = app_runtime.start_campaign(
            campaign_id,
            allow_resume=allow_resume,
            explicit_user_confirmation=explicit_confirmation,
            runner=runner,
            progress_callback=progress_callback,
            completion_callback=completed,
        )
        if not started:
            common.show_snack(page, "Esta campanha já está sendo enviada.", error=True)
            return
        if on_started:
            on_started()
        else:
            common.show_snack(page, f"Envio da campanha #{campaign_id} iniciado.")

    def request_web_confirmation() -> None:
        if (
            delivery_mode != whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL
            or config.dry_run
        ):
            launch(False)
            return

        total = len(campaigns.get_campaign_contacts(campaign_id))
        delay_min = int(campaign.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS)
        delay_max = int(campaign.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS)

        def confirm_web(_event: object | None = None) -> None:
            common.close_dialog(page)
            common.run_after_dialog(page, launch, True)

        common.show_alert(
            page,
            "Confirmar WhatsApp Web Experimental",
            (
                f"Campanha: {campaign.get('name') or campaign_id}\n"
                f"Pasta: {campaign.get('folder_name') or 'Campanha antiga'}\n"
                f"Contatos: {total}\nDelay: {delay_min}-{delay_max}s\n\n"
                "O WhatsApp Web não é uma API oficial. Há risco de bloqueio, "
                "limitação ou desconexão. Confirme o opt-in e o respeito à LGPD "
                "e às regras do WhatsApp."
            ),
            actions=[
                ft.TextButton(
                    "Voltar", key="web-send-cancel",
                    on_click=lambda e: common.close_dialog(page, e),
                ),
                ft.Button(
                    "Confirmar e iniciar", icon=ft.Icons.WARNING_AMBER,
                    key="web-send-confirm", bgcolor=ft.Colors.ERROR,
                    color=ft.Colors.ON_ERROR, on_click=confirm_web,
                ),
            ],
            key="web-send-confirmation",
        )

    score = int(risk.get("score") or 0)
    if score >= 75 and database.get_setting("block_high_risk_campaigns", "1") == "1":
        notes = "\n".join(f"• {note}" for note in list(risk.get("notes") or [])[:5])
        common.show_alert(
            page,
            "Envio bloqueado por risco crítico",
            (
                f"A campanha atingiu {score}% de risco e a proteção contra risco alto está ativa.\n\n"
                f"{notes or 'Revise público, mensagem, mídia e ritmo antes de tentar novamente.'}\n\n"
                "Ajuste a campanha ou, com autorização técnica, altere a política em Configurações."
            ),
            key="risk-send-blocked",
        )
        return False
    if score >= 50:
        notes = "\n".join(f"• {note}" for note in list(risk.get("notes") or [])[:4])
        def confirm_risk(_event: object | None = None) -> None:
            common.close_dialog(page)
            common.run_after_dialog(page, request_web_confirmation)

        common.show_alert(
            page,
            "Campanha com risco elevado",
            (
                f"A análise apontou {score}% de risco ({risk.get('level') or 'atenção'}).\n\n"
                f"{notes or 'Revise público, mensagem e ritmo antes de continuar.'}\n\n"
                "Deseja prosseguir mesmo assim?"
            ),
            actions=[
                ft.TextButton(
                    "Revisar campanha", key="risk-send-cancel",
                    on_click=lambda e: common.close_dialog(page, e),
                ),
                ft.Button(
                    "Prosseguir", icon=ft.Icons.WARNING,
                    key="risk-send-confirm", on_click=confirm_risk,
                ),
            ],
            key="risk-send-confirmation",
        )
        return True

    request_web_confirmation()
    return True


class CampaignsScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route=common.ROUTE_CAMPAIGNS, padding=0)
        self.app_page = page
        self._delay_customized = False
        self._tab_index = 0

        config = whatsapp.load_config()
        self.media_picker = ft.FilePicker(key="campaign-media-picker")
        self.services.append(self.media_picker)

        self.name_input = ft.TextField(
            label="Nome da campanha *", key="campaign-name", autofocus=True
        )
        self.category_dropdown = ft.Dropdown(
            label="Tipo de mensagem", value="Marketing", key="campaign-category",
            options=[ft.dropdown.Option(label, label) for label in CATEGORY_OPTIONS],
        )
        self.delivery_mode_dropdown = ft.Dropdown(
            label="Modo de envio", value=whatsapp.normalize_delivery_mode(config.delivery_mode),
            key="campaign-delivery-mode",
            options=[ft.dropdown.Option(value, label) for value, label in DELIVERY_MODE_OPTIONS],
        )
        self.template_name = ft.TextField(
            label="Modelo aprovado na Meta", value=config.default_template,
            key="campaign-template-name",
        )
        self.template_language = ft.TextField(
            label="Idioma", value=config.default_language or "pt_BR",
            key="campaign-template-language", width=145,
        )
        self.message_input = ft.TextField(
            label="Mensagem principal",
            hint_text="Use {nome} para personalizar quando o provedor permitir.",
            multiline=True, min_lines=5, max_lines=9, key="campaign-message",
        )
        self.message_variants = ft.TextField(
            label="Outras versões da mensagem",
            hint_text="Uma por linha ou blocos separados por uma linha com ---",
            multiline=True, min_lines=3, max_lines=6,
            key="campaign-message-variants",
        )
        self.media_path_input = ft.TextField(
            label="Imagem, arquivo ou link", key="campaign-media-path", expand=True
        )
        self.media_variants_input = ft.TextField(
            label="Outras imagens, arquivos ou links",
            hint_text="Um caminho ou URL por linha", multiline=True,
            min_lines=2, max_lines=4, key="campaign-media-variants",
        )

        self.send_mode_radio = ft.RadioGroup(
            value="now", key="campaign-send-mode", on_change=self._on_send_mode_change,
            content=ft.Row(
                [ft.Radio(value="now", label="Iniciar agora"),
                 ft.Radio(value="schedule", label="Agendar")],
                wrap=True,
            ),
        )
        self.start_at_input = ft.TextField(
            label="Data/hora (AAAA-MM-DD HH:MM)",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"), visible=False,
            key="campaign-scheduled-at", width=260,
        )
        self.delay_min_input = ft.TextField(
            label="Delay mín. (s)", value=str(campaigns.DEFAULT_DELAY_MIN_SECONDS),
            key="campaign-delay-min", width=130, keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_delay_change,
        )
        self.delay_max_input = ft.TextField(
            label="Delay máx. (s)", value=str(campaigns.DEFAULT_DELAY_MAX_SECONDS),
            key="campaign-delay-max", width=130, keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_delay_change,
        )
        self.delay_info_text = ft.Text(
            "", key="campaign-delay-info", color=ft.Colors.ON_SURFACE_VARIANT
        )
        self.folder_dropdown = ft.Dropdown(
            label="Pasta de contatos *", key="campaign-folder", enable_search=True,
            on_select=self._on_folder_change,
        )
        self.folder_stats_text = ft.Text(
            "Escolha uma pasta para ver os contatos.", key="campaign-folder-stats",
            selectable=True,
        )

        create_form = ft.ListView(
            controls=[
                ft.ResponsiveRow(
                    [ft.Container(self.name_input, col={"sm": 12, "lg": 7}),
                     ft.Container(self.category_dropdown, col={"sm": 12, "lg": 5})],
                    spacing=10,
                ),
                ft.ResponsiveRow(
                    [ft.Container(self.delivery_mode_dropdown, col={"sm": 12, "lg": 5}),
                     ft.Container(self.template_name, col={"sm": 8, "lg": 5}),
                     ft.Container(self.template_language, col={"sm": 4, "lg": 2})],
                    spacing=10,
                ),
                self.message_input,
                self.message_variants,
                ft.Row(
                    [self.media_path_input,
                     ft.Button(
                         "Escolher arquivo", icon=ft.Icons.ATTACH_FILE,
                         key="campaign-pick-media", on_click=self.pick_media,
                     ),
                     ft.IconButton(
                         icon=ft.Icons.CLEAR, tooltip="Remover mídia selecionada",
                         key="campaign-clear-media", on_click=self.clear_media,
                     )]
                ),
                self.media_variants_input,
                ft.Divider(),
                ft.Text("Quando e em qual ritmo enviar", weight=ft.FontWeight.BOLD),
                ft.Row([self.send_mode_radio, self.start_at_input], wrap=True),
                ft.Row(
                    [self.delay_min_input, self.delay_max_input,
                     ft.Button(
                         "Usar recomendação", icon=ft.Icons.AUTO_AWESOME,
                         key="campaign-recommended-delay",
                         on_click=self.apply_delay_recommendation,
                     )],
                    wrap=True,
                ),
                self.delay_info_text,
            ],
            expand=True, spacing=12, key="campaign-form",
        )

        target_panel = ft.Container(
            width=330, padding=16, border_radius=10,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            content=ft.Column(
                [ft.Text("Público-alvo", size=17, weight=ft.FontWeight.BOLD),
                 self.folder_dropdown,
                 ft.Row(
                     [ft.Button(
                          "Nova pasta", icon=ft.Icons.CREATE_NEW_FOLDER,
                          key="campaign-new-folder", expand=True,
                          on_click=lambda _e: page.go(common.ROUTE_CONTACTS),
                      ),
                      ft.Button(
                          "Importar", icon=ft.Icons.UPLOAD_FILE,
                          key="campaign-import-contacts", expand=True,
                          on_click=lambda _e: page.go(common.ROUTE_IMPORT_CONTACTS),
                      )]
                 ),
                 ft.Container(
                     content=self.folder_stats_text, padding=12, border_radius=8,
                     bgcolor=ft.Colors.SURFACE_CONTAINER,
                 ),
                 ft.Container(expand=True),
                 ft.Button(
                     "Criar campanha", icon=ft.Icons.SEND, key="campaign-create",
                     height=50, bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE,
                     on_click=self.create_campaign,
                 )],
                spacing=12, expand=True,
            ),
        )
        self.create_panel = ft.Container(
            padding=8,
            content=ft.Row(
                [ft.Container(create_form, padding=8, expand=True), target_panel],
                spacing=16, expand=True,
            ),
            expand=True, key="campaign-create-panel",
        )

        self.campaigns_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")), ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Status")), ft.DataColumn(ft.Text("Risco")),
                ft.DataColumn(ft.Text("Modo")), ft.DataColumn(ft.Text("Pasta")),
                ft.DataColumn(ft.Text("Agendamento")), ft.DataColumn(ft.Text("Progresso")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[], border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, key="campaign-list-table",
        )
        self.list_empty_text = ft.Text(
            "", color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
            key="campaign-list-empty",
        )
        self.list_panel = ft.Container(
            padding=8,
            content=ft.Column(
                [ft.Row(
                     [ft.Text("Campanhas cadastradas", size=20, weight=ft.FontWeight.BOLD),
                      ft.Container(expand=True),
                      ft.Button(
                          "Atualizar", icon=ft.Icons.REFRESH,
                          key="campaign-list-refresh", on_click=self.load_campaigns_list,
                      ),
                      ft.Button(
                          "Central de envios", icon=ft.Icons.SCHEDULE,
                          key="campaign-open-schedule",
                          on_click=lambda _e: page.go(common.ROUTE_SCHEDULE),
                      )]
                 ),
                 self.list_empty_text,
                 ft.ListView([self.campaigns_table], expand=True)],
                expand=True, spacing=10,
            ),
            expand=True, key="campaign-list-panel",
        )

        self.tab_content = ft.Container(expand=True)
        self.create_tab_button = ft.Button(
            "Nova campanha", icon=ft.Icons.ADD_CIRCLE_OUTLINE,
            key="campaign-tab-create", on_click=lambda _e: self.switch_tab(0),
        )
        self.list_tab_button = ft.Button(
            "Minhas campanhas", icon=ft.Icons.LIST_ALT,
            key="campaign-tab-list", on_click=lambda _e: self.switch_tab(1),
        )
        body = ft.Column(
            [ft.Row([self.create_tab_button, self.list_tab_button], spacing=8),
             self.tab_content],
            expand=True, spacing=10,
        )
        self.controls = [common.screen_layout(
            page, common.ROUTE_CAMPAIGNS, "Nova campanha", body,
            subtitle="Crie, personalize e envie para uma pasta inteira de contatos com opt-in.",
        )]
        self.switch_tab(0, update_page=False)
        self.refresh_folders(update_page=False)

    def switch_tab(self, index: int, *, update_page: bool = True) -> None:
        self._tab_index = 0 if int(index) == 0 else 1
        self.tab_content.content = self.create_panel if self._tab_index == 0 else self.list_panel
        selected_style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
        normal_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
        self.create_tab_button.style = selected_style if self._tab_index == 0 else normal_style
        self.list_tab_button.style = selected_style if self._tab_index == 1 else normal_style
        if self._tab_index == 1:
            self.load_campaigns_list(update_page=False)
        if update_page:
            common.safe_update(self.app_page)

    async def pick_media(self, _event: object | None = None) -> None:
        try:
            selected = await self.media_picker.pick_files(
                dialog_title="Selecione a mídia da campanha",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[
                    "png", "jpg", "jpeg", "webp", "gif", "pdf", "mp4",
                    "doc", "docx", "xls", "xlsx", "txt", "zip",
                ],
                allow_multiple=False,
                with_data=bool(getattr(self.app_page, "web", False)),
            )
            if not selected:
                return
            picked = selected[0]
            path = str(getattr(picked, "path", "") or "").strip()
            if not path:
                raw = getattr(picked, "bytes", None)
                if raw is None:
                    raise ValueError("O seletor não retornou o caminho nem os dados do arquivo.")
                if isinstance(raw, str):
                    raw = base64.b64decode(raw)
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(picked.name or "midia"))
                destination_dir = database.DATA_DIR / "campaign_media"
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = destination_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{safe_name}"
                destination.write_bytes(bytes(raw))
                path = str(destination)
            self.media_path_input.value = path
            common.safe_update(self.app_page)
        except Exception as exc:
            common.show_snack(
                self.app_page, f"Não foi possível selecionar a mídia: {exc}", error=True
            )

    def clear_media(self, _event: object | None = None) -> None:
        self.media_path_input.value = ""
        common.safe_update(self.app_page)

    def _on_send_mode_change(self, _event: object | None = None) -> None:
        self.start_at_input.visible = self.send_mode_radio.value == "schedule"
        common.safe_update(self.app_page)

    def _on_delay_change(self, _event: object | None = None) -> None:
        self._delay_customized = True
        self.update_delay_info()

    def _on_folder_change(self, _event: object | None = None) -> None:
        self.refresh_folder_stats()

    def _folder_names(self) -> list[str]:
        names = [str(item.get("name") or "").strip() for item in contacts.list_folders()]
        return [name for name in names if name]

    def refresh_folders(
        self, _event: object | None = None, *, update_page: bool = True
    ) -> None:
        try:
            names = self._folder_names()
            self.folder_dropdown.options = [ft.dropdown.Option(name, name) for name in names]
            if self.folder_dropdown.value not in names:
                preferred = database.DEFAULT_CONTACT_FOLDER
                self.folder_dropdown.value = (
                    preferred if preferred in names else (names[0] if names else None)
                )
            self.refresh_folder_stats(update_page=False)
        except Exception as exc:
            self.folder_stats_text.value = f"Erro ao carregar pastas: {exc}"
        if update_page:
            common.safe_update(self.app_page)

    def eligible_contacts(self, folder_name: str | None = None) -> list[dict[str, Any]]:
        folder = str(
            folder_name if folder_name is not None else self.folder_dropdown.value or ""
        ).strip()
        if not folder:
            return []
        return [
            item for item in contacts.list_contacts(group_name=folder)
            if item.get("opt_in") and not item.get("blacklisted")
        ]

    def update_delay_info(self, *, update_page: bool = True) -> None:
        try:
            d_min, d_max = campaigns.normalize_campaign_delay(
                self.delay_min_input.value, self.delay_max_input.value
            )
            _level, message = campaigns.delay_recommendation_message(d_min, d_max)
            self.delay_info_text.value = f"{message} Configurado: {d_min}-{d_max}s."
        except Exception as exc:
            self.delay_info_text.value = str(exc)
        if update_page:
            common.safe_update(self.app_page)

    def apply_delay_recommendation(
        self, _event: object | None = None, *, update_page: bool = True
    ) -> None:
        d_min, d_max = campaigns.recommended_delay_for_contacts(len(self.eligible_contacts()))
        self.delay_min_input.value = str(d_min)
        self.delay_max_input.value = str(d_max)
        self._delay_customized = False
        self.update_delay_info(update_page=update_page)

    def refresh_folder_stats(
        self, _event: object | None = None, *, update_page: bool = True
    ) -> None:
        folder = str(self.folder_dropdown.value or "").strip()
        if not folder:
            self.folder_stats_text.value = "Crie ou escolha uma pasta de contatos."
            self.update_delay_info(update_page=False)
        else:
            items = contacts.list_contacts(group_name=folder)
            eligible = [item for item in items if item.get("opt_in") and not item.get("blacklisted")]
            blocked = sum(1 for item in items if item.get("blacklisted"))
            used = len(contacts.list_used_contacts(folder_name=folder))
            self.folder_stats_text.value = (
                f"Pasta: {folder}\n\n• Total: {len(items)}\n"
                f"• Com opt-in: {len(eligible)}\n• Já usados/enviados: {used}\n"
                f"• Na blacklist: {blocked}"
            )
            if not self._delay_customized:
                self.apply_delay_recommendation(update_page=False)
            else:
                self.update_delay_info(update_page=False)
        if update_page:
            common.safe_update(self.app_page)

    def _validated_payload(self) -> dict[str, Any] | None:
        name = str(self.name_input.value or "").strip()
        message = str(self.message_input.value or "").strip()
        template = str(self.template_name.value or "").strip()
        folder = str(self.folder_dropdown.value or "").strip()
        if not name:
            common.show_snack(self.app_page, "Informe o nome da campanha.", error=True)
            return None
        if not message and not template:
            common.show_snack(
                self.app_page,
                "Escreva uma mensagem ou informe um modelo aprovado na Meta.",
                error=True,
            )
            return None
        if not folder:
            common.show_snack(self.app_page, "Escolha uma pasta de contatos.", error=True)
            return None
        all_contacts = contacts.list_contacts(group_name=folder)
        if not all_contacts:
            common.show_snack(self.app_page, "A pasta selecionada está vazia.", error=True)
            return None
        selected = [int(item["id"]) for item in self.eligible_contacts(folder)]
        if not selected:
            common.show_snack(
                self.app_page,
                "A pasta não possui contatos com opt-in liberado e fora da blacklist.",
                error=True,
            )
            return None
        try:
            d_min, d_max = campaigns.normalize_campaign_delay(
                self.delay_min_input.value, self.delay_max_input.value, len(selected)
            )
            scheduled_at = None
            if self.send_mode_radio.value == "schedule":
                scheduled_at = parse_datetime(str(self.start_at_input.value or ""))
            delivery_mode = whatsapp.normalize_delivery_mode(self.delivery_mode_dropdown.value)
        except Exception as exc:
            common.show_snack(self.app_page, str(exc), error=True)
            return None
        return {
            "name": name, "message": message, "contact_ids": selected,
            "media_path": str(self.media_path_input.value or "").strip(),
            "template_name": template,
            "template_language": str(self.template_language.value or "pt_BR").strip() or "pt_BR",
            "message_category": CATEGORY_OPTIONS.get(
                str(self.category_dropdown.value or "Marketing"), "marketing"
            ),
            "message_variants": parse_variants(str(self.message_variants.value or "")),
            "media_variants": parse_variants(str(self.media_variants_input.value or "")),
            "scheduled_at": scheduled_at, "folder_name": folder,
            "delay_min_seconds": d_min, "delay_max_seconds": d_max,
            "delivery_mode": delivery_mode,
        }

    def create_campaign(self, _event: object | None = None) -> None:
        payload = self._validated_payload()
        if payload is None:
            return
        level, message = campaigns.delay_recommendation_message(
            payload["delay_min_seconds"], payload["delay_max_seconds"]
        )
        if level != "alto":
            self._create_from_payload(payload)
            return

        def confirm_delay(_event: object | None = None) -> None:
            common.close_dialog(self.app_page)
            self._create_from_payload(payload)

        common.show_alert(
            self.app_page, "Ritmo de envio com risco alto",
            f"{message}\n\nDeseja criar a campanha com esse intervalo mesmo assim?",
            actions=[
                ft.TextButton(
                    "Revisar delay", key="campaign-delay-risk-cancel",
                    on_click=lambda e: common.close_dialog(self.app_page, e),
                ),
                ft.Button(
                    "Criar mesmo assim", key="campaign-delay-risk-confirm",
                    on_click=confirm_delay,
                ),
            ],
            key="campaign-delay-risk-dialog",
        )

    def _create_from_payload(self, payload: dict[str, Any]) -> None:
        try:
            campaign_id = campaigns.create_campaign(**payload)
        except Exception as exc:
            common.show_snack(
                self.app_page, f"Não foi possível criar a campanha: {exc}", error=True
            )
            return
        if payload.get("scheduled_at"):
            common.show_snack(
                self.app_page,
                f"Campanha #{campaign_id} agendada para {payload['scheduled_at']}.",
            )
            if (
                payload.get("delivery_mode") == whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL
                and not whatsapp.load_config().dry_run
            ):
                common.show_alert(
                    self.app_page, "Confirmação necessária no horário",
                    "O envio real por WhatsApp Web nunca é confirmado automaticamente. "
                    "No horário agendado, abra a Central de envios e clique em Iniciar para "
                    "revisar o risco e confirmar manualmente.",
                    actions=[ft.Button(
                        "Ir para a Central de envios",
                        icon=ft.Icons.SCHEDULE,
                        key="campaign-web-schedule-continue",
                        on_click=self._close_web_schedule_warning,
                    )],
                    key="campaign-web-schedule-warning",
                )
            else:
                self.app_page.go(common.ROUTE_SCHEDULE)
            return
        common.show_snack(self.app_page, f"Campanha #{campaign_id} criada. Preparando o envio.")
        request_campaign_start(
            self.app_page, campaign_id, runner="ui_create_now",
            on_started=lambda: self.app_page.run_task(self._open_schedule_after_dialog),
        )

    async def _open_schedule_after_dialog(self) -> None:
        # Let Flet finish restoring the dismissed confirmation dialog before
        # freezing/removing its view during route navigation.
        await asyncio.sleep(0.1)
        self.app_page.go(common.ROUTE_SCHEDULE)

    def _close_web_schedule_warning(self, _event: object | None = None) -> None:
        common.close_dialog(self.app_page)
        self.app_page.run_task(self._open_schedule_after_dialog)

    def load_campaigns_list(
        self, _event: object | None = None, *, update_page: bool = True
    ) -> None:
        self.campaigns_table.rows.clear()
        try:
            items = campaigns.list_campaigns()
            self.list_empty_text.value = (
                "" if items else "Nenhuma campanha criada. Use a aba Nova campanha."
            )
            for item in items:
                campaign_id = int(item["id"])
                try:
                    risk_score = int(
                        compliance.refresh_campaign_risk(campaign_id).get("score") or 0
                    )
                except Exception:
                    risk_score = int(item.get("risk_score") or 0)
                total = int(item.get("total_contacts") or 0)
                processed = int(item.get("processed_contacts") or 0)
                percent = int(item.get("progress_percent") or 0)
                self.campaigns_table.rows.append(ft.DataRow(
                    key=f"campaign-row-{campaign_id}",
                    cells=[
                        ft.DataCell(ft.Text(str(campaign_id))),
                        ft.DataCell(ft.Text(str(item.get("name") or ""))),
                        ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                        ft.DataCell(ft.Text(f"{risk_score}%")),
                        ft.DataCell(ft.Text(whatsapp.delivery_mode_label(item.get("delivery_mode")))),
                        ft.DataCell(ft.Text(str(item.get("folder_name") or "Campanha antiga"))),
                        ft.DataCell(ft.Text(str(item.get("scheduled_at") or ""))),
                        ft.DataCell(ft.Text(f"{percent}% ({processed}/{total})")),
                        ft.DataCell(ft.TextButton(
                            "Gerenciar", key=f"campaign-manage-{campaign_id}",
                            on_click=lambda _e, cid=campaign_id: self._open_schedule(cid),
                        )),
                    ],
                ))
        except Exception as exc:
            self.list_empty_text.value = f"Erro ao listar campanhas: {exc}"
        if update_page:
            common.safe_update(self.app_page)

    def _open_schedule(self, campaign_id: int) -> None:
        setattr(self.app_page, "mezzold_selected_campaign_id", int(campaign_id))
        self.app_page.go(common.ROUTE_SCHEDULE)

    def did_mount(self) -> None:
        self.refresh_folders(update_page=False)
        self.load_campaigns_list(update_page=False)
        common.safe_update(self.app_page)
