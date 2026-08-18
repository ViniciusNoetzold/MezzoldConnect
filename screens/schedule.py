# -*- coding: utf-8 -*-
import flet as ft
import campaigns
import compliance
import auth
import whatsapp
import threading
from datetime import datetime

STATUS_LABELS = {
    "rascunho": "Rascunho", "agendada": "Agendada", "enviando": "Em andamento",
    "concluída": "Concluída", "concluida": "Concluída", "pausada": "Pausada",
    "cancelada": "Cancelada", "enviado": "Enviado", "simulado": "Teste",
    "pendente_manual": "Aguardando manual", "aguardando_manual": "Aguardando manual",
    "erro": "Erro", "falhou": "Erro", "bloqueado": "Bloqueado", "sem_autorizacao": "Sem autorização",
}

DELIVERY_MODE_LABELS = {
    "official_api": "API Oficial Meta",
    "whatsapp_web_experimental": "WhatsApp Web",
    "manual_assisted": "Manual",
}

def friendly_status(v):
    return STATUS_LABELS.get(str(v or "").strip(), str(v or ""))


class ScheduleScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/schedule", padding=0)
        self.app_page = page
        self.selected_campaign_id = None
        self.running_events: dict = {}
        self.campaign_by_id: dict = {}

        user = auth.get_current_user() or "Usuário"
        role = auth.get_current_role() or "Cliente"

        # Sidebar
        menu_items = [
            ft.Row([ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, color=ft.Colors.BLUE_ACCENT), ft.Text("Mezzold", size=20, weight=ft.FontWeight.BOLD)]),
            ft.Text(f"{user}\nPerfil: {role}", size=13, color=ft.Colors.PRIMARY),
            ft.Divider(height=20),
            self._menu_button("Início", ft.Icons.HOME, route="/dashboard"),
            self._menu_button("Clientes", ft.Icons.PEOPLE, route="/contacts"),
            self._menu_button("Nova Campanha", ft.Icons.SEND, route="/campaigns"),
            self._menu_button("Agenda de Envios", ft.Icons.SCHEDULE, selected=True, route="/schedule"),
            self._menu_button("Conferir Risco", ft.Icons.WARNING_AMBER, route="/risk"),
            self._menu_button("Histórico", ft.Icons.HISTORY, route="/history"),
        ]

        if str(role).lower() in ("equipe", "admin"):
            menu_items.append(self._menu_button("Saúde do Número", ft.Icons.HEALTH_AND_SAFETY, route="/health"))

        menu_items.extend([
            self._menu_button("Configurações", ft.Icons.SETTINGS, route="/settings"),
            ft.Container(expand=True),
            ft.ElevatedButton(
                "Sair", 
                icon=ft.Icons.LOGOUT, 
                width=210, 
                color=ft.Colors.ERROR,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                on_click=self.logout
            )
        ])

        sidebar = ft.Container(
            width=250,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=20,
            content=ft.Column(controls=menu_items)
        )

        # Action buttons top bar
        self.action_buttons = ft.Row(
            controls=[
                ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.load_campaigns),
                ft.ElevatedButton("Iniciar Agora", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=self.start_campaign),
                ft.ElevatedButton("Agendar", icon=ft.Icons.SCHEDULE, on_click=self.schedule_selected),
                ft.ElevatedButton("Pausar", icon=ft.Icons.PAUSE, on_click=self.pause_selected),
                ft.ElevatedButton("Continuar", icon=ft.Icons.PLAY_CIRCLE, on_click=self.continue_campaign),
                ft.ElevatedButton("Cancelar", icon=ft.Icons.CANCEL, color=ft.Colors.ERROR, on_click=self.cancel_selected),
                ft.ElevatedButton("Histórico", icon=ft.Icons.LIST_ALT, on_click=self.show_campaign_history),
                ft.ElevatedButton("Ver Contatos", icon=ft.Icons.OPEN_IN_NEW, on_click=self.show_campaign_detail),
            ],
            wrap=True,
            spacing=8
        )

        # Campaigns DataTable
        self.campaigns_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome da Campanha")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Modo")),
                ft.DataColumn(ft.Text("Agendamento")),
                ft.DataColumn(ft.Text("Pasta")),
                ft.DataColumn(ft.Text("Delay")),
                ft.DataColumn(ft.Text("Total"), numeric=True),
                ft.DataColumn(ft.Text("Enviados"), numeric=True),
                ft.DataColumn(ft.Text("Falhas"), numeric=True),
                ft.DataColumn(ft.Text("Progresso")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[],
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        )

        # Edit panel
        self.edit_name = ft.TextField(label="Nome da Campanha", expand=True)
        self.edit_scheduled_at = ft.TextField(label="Agendamento (AAAA-MM-DD HH:MM)", width=240)
        self.edit_delay_min = ft.TextField(label="Delay Mín (s)", width=110)
        self.edit_delay_max = ft.TextField(label="Delay Máx (s)", width=110)
        self.edit_delivery_mode = ft.Dropdown(
            label="Modo de Envio",
            width=220,
            options=[
                ft.dropdown.Option("official_api", "API Oficial Meta"),
                ft.dropdown.Option("whatsapp_web_experimental", "WhatsApp Web"),
                ft.dropdown.Option("manual_assisted", "Manual Assistido"),
            ]
        )
        self.edit_details = ft.Text("Nenhuma campanha selecionada.", color=ft.Colors.ON_SURFACE_VARIANT)
        self.progress_text = ft.Text("", color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD)
        self.empty_text = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT, italic=True)

        edit_panel = ft.Container(
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            content=ft.Column([
                self.edit_details,
                ft.Row([
                    self.edit_name,
                    self.edit_scheduled_at,
                    self.edit_delay_min,
                    self.edit_delay_max,
                    self.edit_delivery_mode,
                    ft.ElevatedButton("Salvar Alterações", icon=ft.Icons.SAVE, on_click=self.save_changes, bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE),
                ], wrap=True, spacing=8),
                self.progress_text,
            ], spacing=10)
        )

        content = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                controls=[
                    ft.Text("Central de Envios & Agendamentos", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=10),
                    self.action_buttons,
                    self.empty_text,
                    ft.Container(
                        expand=True,
                        content=ft.ListView(
                            expand=True,
                            controls=[self.campaigns_table]
                        )
                    ),
                    edit_panel,
                ],
                spacing=10,
                expand=True
            )
        )

        self.controls = [
            ft.Row(
                controls=[sidebar, content],
                expand=True,
                spacing=0
            )
        ]

    def _menu_button(self, text, icon, selected=False, route=None):
        return ft.ListTile(
            leading=ft.Icon(icon),
            title=ft.Text(text, weight=ft.FontWeight.BOLD if selected else ft.FontWeight.NORMAL),
            selected=selected,
            on_click=lambda e: self.navigate(route) if route else None
        )

    def navigate(self, route):
        self.app_page.go(route)

    def logout(self, e):
        self.app_page.go("/")

    def show_snack(self, msg, color=ft.Colors.GREEN):
        self.app_page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        self.app_page.snack_bar.open = True
        self.app_page.update()

    def load_campaigns(self, e=None):
        self.campaigns_table.rows.clear()
        self.campaign_by_id.clear()
        try:
            items = campaigns.list_campaigns()
            self.empty_text.value = "" if items else "Nenhuma campanha criada ainda. Vá em 'Nova Campanha' para criar."
            for item in items:
                cid = int(item["id"])
                try:
                    risk = compliance.refresh_campaign_risk(cid)
                    item["risk_score"] = risk.get("score", 0)
                except Exception:
                    item["risk_score"] = item.get("risk_score", 0)
                self.campaign_by_id[cid] = item
                total = int(item.get("total_contacts") or 0)
                processed = int(item.get("processed_contacts") or 0)
                sent = int(item.get("sent_contacts") or 0)
                failed = int(item.get("failed_contacts") or 0)
                percent = int(item.get("progress_percent") or (sent/total*100 if total else 0))
                d_min = int(item.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS)
                d_max = int(item.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS)
                mode = DELIVERY_MODE_LABELS.get(str(item.get("delivery_mode") or ""), str(item.get("delivery_mode") or ""))

                self.campaigns_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(cid))),
                            ft.DataCell(ft.Text(str(item.get("name") or ""))),
                            ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                            ft.DataCell(ft.Text(mode)),
                            ft.DataCell(ft.Text(str(item.get("scheduled_at") or ""))),
                            ft.DataCell(ft.Text(str(item.get("folder_name") or ""))),
                            ft.DataCell(ft.Text(f"{d_min}-{d_max}s")),
                            ft.DataCell(ft.Text(str(total))),
                            ft.DataCell(ft.Text(str(sent))),
                            ft.DataCell(ft.Text(str(failed))),
                            ft.DataCell(ft.Text(f"{percent}% ({processed}/{total})")),
                            ft.DataCell(ft.TextButton("Selecionar", on_click=lambda e, cid=cid: self.select_campaign(cid))),
                        ],
                    )
                )
        except Exception as ex:
            self.empty_text.value = f"Erro ao carregar campanhas: {str(ex)}"
        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def select_campaign(self, campaign_id: int):
        self.selected_campaign_id = campaign_id
        item = self.campaign_by_id.get(campaign_id)
        if not item:
            return
        self.edit_name.value = str(item.get("name") or "")
        self.edit_scheduled_at.value = str(item.get("scheduled_at") or "")
        self.edit_delay_min.value = str(item.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS)
        self.edit_delay_max.value = str(item.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS)
        self.edit_delivery_mode.value = str(item.get("delivery_mode") or "official_api")
        total = int(item.get("total_contacts") or 0)
        sent = int(item.get("sent_contacts") or 0)
        failed = int(item.get("failed_contacts") or 0)
        mode = DELIVERY_MODE_LABELS.get(str(item.get("delivery_mode") or ""), "")
        self.edit_details.value = (
            f"Campanha #{campaign_id}: {item.get('name')} | Status: {friendly_status(item.get('status'))} | "
            f"Pasta: {item.get('folder_name') or ''} | Modo: {mode} | "
            f"Total: {total} | Enviados: {sent} | Falhas: {failed} | "
            f"Risco: {item.get('risk_score', 0)}%"
        )
        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def _get_selected_id(self) -> int | None:
        if not self.selected_campaign_id:
            self.show_snack("Selecione uma campanha na tabela primeiro.", ft.Colors.AMBER)
            return None
        return self.selected_campaign_id

    def start_campaign(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        if campaign_id in self.running_events:
            self.show_snack("Esta campanha já está sendo enviada.", ft.Colors.AMBER)
            return
        self._launch_campaign_thread(campaign_id)

    def continue_campaign(self, e):
        campaign_id = self._get_selected_id()
        if campaign_id:
            self._launch_campaign_thread(campaign_id, allow_resume=True)

    def _launch_campaign_thread(self, campaign_id: int, allow_resume: bool = False):
        stop_event = threading.Event()
        self.running_events[campaign_id] = stop_event

        def worker():
            try:
                totals = campaigns.send_campaign(
                    campaign_id,
                    stop_event=stop_event,
                    runner="ui_manual",
                    allow_resume=allow_resume,
                )
                msg = f"Campanha #{campaign_id}: finalizada! Enviados: {totals.get('enviado',0)}, Falhas: {totals.get('falhou',0)}."
                if hasattr(self, 'app_page') and self.app_page:
                    self.show_snack(msg, ft.Colors.GREEN)
                    self.load_campaigns()
            except Exception as ex:
                if hasattr(self, 'app_page') and self.app_page:
                    self.show_snack(f"Erro no envio: {str(ex)}", ft.Colors.ERROR)
            finally:
                self.running_events.pop(campaign_id, None)

        threading.Thread(target=worker, daemon=True).start()
        self.progress_text.value = f"Disparo da campanha #{campaign_id} em andamento..."
        self.show_snack(f"Disparo da campanha #{campaign_id} iniciado!", ft.Colors.BLUE)

    def schedule_selected(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        s_val = (self.edit_scheduled_at.value or "").strip()
        if not s_val:
            self.show_snack("Preencha a data e hora do agendamento.", ft.Colors.RED)
            return
        try:
            campaigns.schedule_campaign(campaign_id, s_val)
            self.show_snack("Campanha agendada com sucesso!")
            self.load_campaigns()
        except Exception as ex:
            self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)

    def pause_selected(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        stop_event = self.running_events.get(campaign_id)
        if stop_event:
            stop_event.set()
        try:
            campaigns.pause_campaign(campaign_id)
            self.show_snack("Campanha pausada.", ft.Colors.AMBER)
            self.load_campaigns()
        except Exception as ex:
            self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)

    def cancel_selected(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        dlg = None
        def confirm_cancel(e):
            dlg.open = False
            try:
                campaigns.cancel_campaign(campaign_id)
                self.show_snack("Campanha cancelada.")
                self.load_campaigns()
            except Exception as ex:
                self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cancelar Campanha"),
            content=ft.Text("Tem certeza que deseja cancelar esta campanha? Ela não será enviada."),
            actions=[
                ft.TextButton("Não", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Sim, Cancelar", bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE, on_click=confirm_cancel),
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def save_changes(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        try:
            d_min, d_max = campaigns.normalize_campaign_delay(self.edit_delay_min.value, self.edit_delay_max.value)
            campaigns.update_campaign_details(
                campaign_id,
                self.edit_name.value or "",
                self.edit_scheduled_at.value.strip() or "",
                delay_min_seconds=d_min,
                delay_max_seconds=d_max,
                delivery_mode=self.edit_delivery_mode.value or "official_api",
            )
            self.show_snack("Campanha atualizada com sucesso!")
            self.load_campaigns()
        except Exception as ex:
            self.show_snack(f"Erro ao salvar: {str(ex)}", ft.Colors.RED)

    def show_campaign_history(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        try:
            logs = campaigns.list_campaign_logs(campaign_id)
        except Exception as ex:
            self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)
            return

        rows = []
        for log in logs:
            status = friendly_status(log.get("status"))
            mode = DELIVERY_MODE_LABELS.get(str(log.get("delivery_mode") or ""), str(log.get("delivery_mode") or ""))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(log.get("created_at") or "")[:16])),
                ft.DataCell(ft.Text(str(log.get("recipient_name") or ""))),
                ft.DataCell(ft.Text(str(log.get("phone") or ""))),
                ft.DataCell(ft.Text(status)),
                ft.DataCell(ft.Text(mode)),
                ft.DataCell(ft.Text(str(log.get("error_message") or "")[:60])),
            ]))

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Data/hora")),
                ft.DataColumn(ft.Text("Contato")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Modo")),
                ft.DataColumn(ft.Text("Erro")),
            ],
            rows=rows if rows else [ft.DataRow(cells=[ft.DataCell(ft.Text("Sem histórico de envio.", italic=True))] + [ft.DataCell(ft.Text(""))]*5)]
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Histórico da Campanha #{campaign_id}"),
            content=ft.Container(
                width=800,
                height=400,
                content=ft.ListView(controls=[table], expand=True)
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update())]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def show_campaign_detail(self, e):
        campaign_id = self._get_selected_id()
        if not campaign_id:
            return
        try:
            campaign = campaigns.get_campaign(campaign_id)
            contact_list = campaigns.get_campaign_contacts(campaign_id)
        except Exception as ex:
            self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)
            return

        rows = []
        for c in contact_list:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(c.get("name") or c.get("recipient_name") or ""))),
                ft.DataCell(ft.Text(str(c.get("phone") or ""))),
                ft.DataCell(ft.Text(friendly_status(c.get("campaign_status") or c.get("status")))),
                ft.DataCell(ft.Text(str(c.get("last_error") or "")[:60])),
            ]))

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Último Erro")),
            ],
            rows=rows if rows else [ft.DataRow(cells=[ft.DataCell(ft.Text("Sem contatos associados."))] + [ft.DataCell(ft.Text(""))]*3)]
        )

        summary = ""
        if campaign:
            mode = DELIVERY_MODE_LABELS.get(str(campaign.get("delivery_mode") or ""), "")
            summary = (
                f"Status: {friendly_status(campaign.get('status'))} | "
                f"Pasta: {campaign.get('folder_name') or ''} | "
                f"Modo: {mode} | "
                f"Template: {campaign.get('template_name') or 'Nenhum'}"
            )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Campanha #{campaign_id} - {campaign.get('name') if campaign else ''}"),
            content=ft.Container(
                width=750,
                height=450,
                content=ft.Column([
                    ft.Text(summary, color=ft.Colors.ON_SURFACE_VARIANT, size=12),
                    ft.Divider(),
                    ft.Text("Mensagem:", weight=ft.FontWeight.BOLD),
                    ft.Text(str(campaign.get("message") or "")[:300] if campaign else "", italic=True),
                    ft.Divider(),
                    ft.Text("Destinatários:", weight=ft.FontWeight.BOLD),
                    ft.ListView(controls=[table], expand=True),
                ])
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update())]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def did_mount(self):
        self.load_campaigns()
