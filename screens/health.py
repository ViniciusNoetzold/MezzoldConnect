# -*- coding: utf-8 -*-
import threading
import flet as ft
import warmup
import contacts
import auth

STATUS_LABELS = {
    'testing': 'Em aquecimento',
    'healthy': 'Saudável',
    'paused': 'Pausado',
    'auto_paused': 'Auto-pausado',
    'restricted': 'Restrito',
    'banned': 'Banido'
}

QUALITY_LABELS = {
    'unknown': 'Sem dados',
    'high': 'Alta',
    'medium': 'Média',
    'low': 'Baixa'
}

def friendly_status(v):
    return STATUS_LABELS.get(str(v or '').strip().lower(), str(v or ''))

def friendly_quality(v):
    return QUALITY_LABELS.get(str(v or '').strip().lower(), str(v or ''))


class HealthScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/health", padding=0)
        self.app_page = page
        self.selected_number_id = None
        self.running_warmups = {}

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
            self._menu_button("Agenda de Envios", ft.Icons.SCHEDULE, route="/schedule"),
            self._menu_button("Conferir Risco", ft.Icons.WARNING_AMBER, route="/risk"),
            self._menu_button("Histórico", ft.Icons.HISTORY, route="/history"),
            self._menu_button("Saúde do Número", ft.Icons.HEALTH_AND_SAFETY, selected=True, route="/health"),
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
        ]

        sidebar = ft.Container(
            width=250,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=20,
            content=ft.Column(controls=menu_items)
        )

        # 4 Stats Cards
        self.stat_total = ft.Text("0", size=22, weight=ft.FontWeight.BOLD)
        self.stat_active = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN)
        self.stat_ready = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE)
        self.stat_paused = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER)

        # Numbers Table
        self.numbers_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Score")),
                ft.DataColumn(ft.Text("Qualidade")),
                ft.DataColumn(ft.Text("Meta Hoje")),
                ft.DataColumn(ft.Text("Enviados")),
                ft.DataColumn(ft.Text("Pronto")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[]
        )

        # Recent Events Table
        self.events_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Data/hora")),
                ft.DataColumn(ft.Text("Número")),
                ft.DataColumn(ft.Text("Destinatário")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Erro")),
            ],
            rows=[]
        )

        # Form Controls (Right Side)
        self.f_name = ft.TextField(label="Nome / Identificador *")
        self.f_phone = ft.TextField(label="Telefone (com DDD) *")
        self.f_phone_id = ft.TextField(label="ID do Número na Meta (opcional)")
        self.f_provider = ft.Dropdown(
            label="Tipo de Envio",
            value="oficial",
            options=[ft.dropdown.Option("oficial", "Oficial API"), ft.dropdown.Option("web", "WhatsApp Web")]
        )
        self.f_status = ft.Dropdown(
            label="Status",
            value="testing",
            options=[
                ft.dropdown.Option("testing", "Em aquecimento"),
                ft.dropdown.Option("healthy", "Saudável"),
                ft.dropdown.Option("paused", "Pausado"),
                ft.dropdown.Option("auto_paused", "Auto-pausado"),
                ft.dropdown.Option("restricted", "Restrito"),
                ft.dropdown.Option("banned", "Banido"),
            ]
        )
        self.f_quality = ft.Dropdown(
            label="Qualidade Meta",
            value="unknown",
            options=[
                ft.dropdown.Option("unknown", "Sem dados"),
                ft.dropdown.Option("high", "Alta"),
                ft.dropdown.Option("medium", "Média"),
                ft.dropdown.Option("low", "Baixa"),
            ]
        )
        self.f_limit = ft.TextField(label="Limite da Conta", value="250")
        self.f_daily_target = ft.TextField(label="Envios por Dia (Inicial)", value="20")
        self.f_max_target = ft.TextField(label="Limite Máximo Diário", value="500")
        self.f_rest_start = ft.TextField(label="Início Repouso (HH:MM)", value="00:00")
        self.f_rest_end = ft.TextField(label="Fim Repouso (HH:MM)", value="07:00")
        
        folders = contacts.list_groups()
        folder_opts = [ft.dropdown.Option(f, f) for f in folders]
        self.f_group = ft.Dropdown(label="Grupo/Pasta para Teste", options=folder_opts, value=folders[0] if folders else "")
        self.f_active = ft.Switch(label="Número Ativo", value=True)
        self.f_ready = ft.Switch(label="Pronto para Campanhas", value=False)
        self.f_notes = ft.TextField(label="Notas / Observações", multiline=True)
        self.progress_msg = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        form_card = ft.Container(
            width=360,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=12,
            content=ft.Column(
                controls=[
                    ft.Text("Cadastrar / Editar Número", size=16, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.ListView(
                            controls=[
                                self.f_name, self.f_phone, self.f_phone_id, self.f_provider,
                                self.f_status, self.f_quality, self.f_limit, self.f_daily_target,
                                self.f_max_target, self.f_rest_start, self.f_rest_end,
                                self.f_group, self.f_active, self.f_ready, self.f_notes
                            ],
                            spacing=10
                        ),
                        expand=True
                    ),
                    self.progress_msg,
                    ft.Row([
                        ft.ElevatedButton("Novo", on_click=self.clear_form, expand=True),
                        ft.ElevatedButton("Salvar", bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=self.save_number, expand=True),
                    ], spacing=6),
                    ft.Row([
                        ft.ElevatedButton("Iniciar Aquecimento", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=self.start_warmup, expand=True),
                        ft.ElevatedButton("Pausar", icon=ft.Icons.PAUSE, on_click=self.stop_warmup, expand=True),
                    ], spacing=6),
                    ft.ElevatedButton("Excluir Número", icon=ft.Icons.DELETE, color=ft.Colors.ERROR, on_click=self.delete_number, width=330),
                ],
                spacing=8,
                expand=True
            )
        )

        left_content = ft.Column(
            controls=[
                ft.Row([
                    self._card("Total Números", self.stat_total, ft.Icons.PHONE_ANDROID, ft.Colors.BLUE_GREY),
                    self._card("Ativos", self.stat_active, ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN),
                    self._card("Prontos", self.stat_ready, ft.Icons.VERIFIED, ft.Colors.BLUE),
                    self._card("Pausados", self.stat_paused, ft.Icons.PAUSE_CIRCLE, ft.Colors.AMBER),
                ], spacing=10),
                ft.Divider(height=15),
                ft.Text("Números WhatsApp Conectados", weight=ft.FontWeight.BOLD, size=16),
                ft.Container(
                    height=220,
                    content=ft.ListView(controls=[self.numbers_table], expand=True)
                ),
                ft.Divider(height=15),
                ft.Text("Últimos Testes de Aquecimento", weight=ft.FontWeight.BOLD, size=16),
                ft.Container(
                    expand=True,
                    content=ft.ListView(controls=[self.events_table], expand=True)
                ),
            ],
            spacing=8,
            expand=True
        )

        content = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Text("Aquecimento & Saúde dos Números", size=28, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.load_data),
                    ]),
                    ft.Divider(height=10),
                    ft.Row([left_content, form_card], expand=True, spacing=16)
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

    def _card(self, title, text_c, icon, color):
        return ft.Container(
            expand=True,
            padding=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=8,
            content=ft.Row([
                ft.Icon(icon, color=color, size=28),
                ft.Column([
                    ft.Text(title, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    text_c
                ], spacing=2)
            ], spacing=10)
        )

    def clear_form(self, e=None):
        self.selected_number_id = None
        self.f_name.value = ""
        self.f_phone.value = ""
        self.f_phone_id.value = ""
        self.f_provider.value = "oficial"
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
        self.progress_msg.value = ""
        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def load_data(self, e=None):
        try:
            stats = warmup.dashboard_stats()
            self.stat_total.value = str(stats.get('total', 0))
            self.stat_active.value = str(stats.get('active', 0))
            self.stat_ready.value = str(stats.get('ready', 0))
            self.stat_paused.value = str(stats.get('paused', 0))

            num_list = warmup.list_numbers()
            self.numbers_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(item.get('id')))),
                    ft.DataCell(ft.Text(str(item.get('display_name') or ''))),
                    ft.DataCell(ft.Text(str(item.get('phone') or ''))),
                    ft.DataCell(ft.Text(friendly_status(item.get('status')))),
                    ft.DataCell(ft.Text(str(item.get('health_score') or 85))),
                    ft.DataCell(ft.Text(friendly_quality(item.get('quality_rating')))),
                    ft.DataCell(ft.Text(str(item.get('current_daily_target') or item.get('daily_target') or 20))),
                    ft.DataCell(ft.Text(str(item.get('sent_today') or 0))),
                    ft.DataCell(ft.Icon(ft.Icons.CHECK, color=ft.Colors.GREEN) if item.get('ready_for_campaigns') else ft.Icon(ft.Icons.CLOSE, color=ft.Colors.GREY)),
                    ft.DataCell(ft.TextButton("Editar", on_click=lambda e, nid=item.get('id'): self.on_number_selected(nid))),
                ])
                for item in num_list
            ]

            ev_list = warmup.list_recent_events()
            self.events_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(ev.get('created_at') or '')[:16])),
                    ft.DataCell(ft.Text(str(ev.get('number_name') or ''))),
                    ft.DataCell(ft.Text(str(ev.get('recipient_name') or ''))),
                    ft.DataCell(ft.Text(str(ev.get('phone') or ''))),
                    ft.DataCell(ft.Text(friendly_status(ev.get('status')))),
                    ft.DataCell(ft.Text(str(ev.get('error_message') or ''))),
                ])
                for ev in ev_list
            ]
        except Exception as ex:
            self.show_snack(f"Erro ao carregar dados: {str(ex)}", ft.Colors.RED)

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def on_number_selected(self, number_id):
        self.selected_number_id = number_id
        data = warmup.get_number(number_id)
        if not data:
            return
        self.f_name.value = str(data.get('display_name') or '')
        self.f_phone.value = str(data.get('phone') or '')
        self.f_phone_id.value = str(data.get('phone_number_id') or '')
        self.f_provider.value = str(data.get('provider') or 'oficial')
        self.f_status.value = str(data.get('status') or 'testing')
        self.f_quality.value = str(data.get('quality_rating') or 'unknown')
        self.f_limit.value = str(data.get('messaging_limit') or '250')
        self.f_daily_target.value = str(data.get('daily_target') or '20')
        self.f_max_target.value = str(data.get('max_daily_target') or '500')
        self.f_rest_start.value = str(data.get('rest_start') or '00:00')
        self.f_rest_end.value = str(data.get('rest_end') or '07:00')
        self.f_active.value = bool(data.get('active', True))
        self.f_ready.value = bool(data.get('ready_for_campaigns', False))
        self.f_notes.value = str(data.get('notes') or '')
        self.progress_msg.value = f"Número #{number_id} selecionado para edição."
        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def save_number(self, e):
        name = (self.f_name.value or "").strip()
        phone = (self.f_phone.value or "").strip()
        if not name or not phone:
            self.show_snack("Nome e telefone são obrigatórios.", ft.Colors.RED)
            return
        try:
            if self.selected_number_id:
                warmup.update_number(
                    self.selected_number_id,
                    display_name=name,
                    phone=phone,
                    phone_number_id=self.f_phone_id.value or '',
                    provider=self.f_provider.value or 'oficial',
                    status=self.f_status.value or 'testing',
                    quality_rating=self.f_quality.value or 'unknown',
                    messaging_limit=self.f_limit.value or '250',
                    daily_target=self.f_daily_target.value or '20',
                    max_daily_target=self.f_max_target.value or '500',
                    active=self.f_active.value,
                    ready_for_campaigns=self.f_ready.value,
                    rest_start=self.f_rest_start.value or '00:00',
                    rest_end=self.f_rest_end.value or '07:00',
                    notes=self.f_notes.value or ''
                )
                self.show_snack("Número atualizado com sucesso!")
            else:
                nid = warmup.add_number(
                    name,
                    phone,
                    self.f_phone_id.value or '',
                    self.f_provider.value or 'oficial',
                    self.f_status.value or 'testing',
                    self.f_quality.value or 'unknown',
                    int(self.f_limit.value or 250),
                    int(self.f_daily_target.value or 20),
                    int(self.f_max_target.value or 500),
                    self.f_active.value,
                    self.f_rest_start.value or '00:00',
                    self.f_rest_end.value or '07:00',
                    self.f_notes.value or ''
                )
                self.selected_number_id = nid
                self.show_snack("Número adicionado com sucesso!")
            self.load_data()
        except Exception as ex:
            self.show_snack(f"Erro ao salvar: {str(ex)}", ft.Colors.RED)

    def delete_number(self, e):
        if not self.selected_number_id:
            self.show_snack("Selecione um número primeiro.", ft.Colors.AMBER)
            return
        dlg = None
        def confirm_del(e):
            try:
                warmup.delete_number(self.selected_number_id)
                dlg.open = False
                self.clear_form()
                self.load_data()
                self.show_snack("Número excluído com sucesso.")
            except Exception as ex:
                self.show_snack(f"Erro ao excluir: {str(ex)}", ft.Colors.RED)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Excluir Número"),
            content=ft.Text("Tem certeza que deseja excluir este número e seu histórico de aquecimento?"),
            actions=[
                ft.TextButton("Não", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Sim, Excluir", bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE, on_click=confirm_del),
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def start_warmup(self, e):
        if not self.selected_number_id:
            self.show_snack("Selecione um número na tabela primeiro.", ft.Colors.AMBER)
            return
        nid = self.selected_number_id
        if nid in self.running_warmups:
            self.show_snack("Este número já está em processo de aquecimento.", ft.Colors.AMBER)
            return

        stop_ev = threading.Event()
        self.running_warmups[nid] = stop_ev

        def worker():
            try:
                grp = self.f_group.value or ""
                warmup.run_number_rampup(nid, group_name=grp, stop_event=stop_ev)
                if hasattr(self, 'app_page') and self.app_page:
                    self.show_snack(f"Aquecimento do número #{nid} finalizado!", ft.Colors.GREEN)
                    self.load_data()
            except Exception as ex:
                if hasattr(self, 'app_page') and self.app_page:
                    self.show_snack(f"Erro no aquecimento: {str(ex)}", ft.Colors.RED)
            finally:
                self.running_warmups.pop(nid, None)

        threading.Thread(target=worker, daemon=True).start()
        self.progress_msg.value = f"Aquecimento do número #{nid} iniciado em segundo plano."
        self.show_snack(f"Aquecimento do número #{nid} iniciado!", ft.Colors.GREEN)
        self.app_page.update()

    def stop_warmup(self, e):
        if not self.selected_number_id:
            return
        nid = self.selected_number_id
        ev = self.running_warmups.get(nid)
        if ev:
            ev.set()
            self.progress_msg.value = "Pausa solicitada."
            self.show_snack("Pausa no aquecimento solicitada.", ft.Colors.AMBER)
        else:
            self.show_snack("Este número não está aquecendo no momento.")

    def did_mount(self):
        self.load_data()
