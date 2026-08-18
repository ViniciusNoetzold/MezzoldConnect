# -*- coding: utf-8 -*-
import threading
import flet as ft
import campaigns
import auth
import compliance

STATUS_LABELS = {
    'rascunho': 'Rascunho', 'agendada': 'Agendada', 'enviando': 'Em andamento',
    'concluída': 'Concluída', 'concluida': 'Concluída', 'pausada': 'Pausada',
    'cancelada': 'Cancelada', 'enviado': 'Enviado', 'erro': 'Erro'
}

def friendly_status(v):
    return STATUS_LABELS.get(str(v or '').strip(), str(v or ''))


class Dashboard(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/dashboard", padding=0)
        self.app_page = page
        
        user = auth.get_current_user() or "Usuário"
        role = auth.get_current_role() or "Cliente"
        
        # Sidebar
        menu_items = [
            ft.Row([ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, color=ft.Colors.BLUE_ACCENT), ft.Text("Mezzold", size=20, weight=ft.FontWeight.BOLD)]),
            ft.Text(f"{user}\nPerfil: {role}", size=13, color=ft.Colors.PRIMARY),
            ft.Divider(height=20),
            self._menu_button("Início", ft.Icons.HOME, selected=True, route="/dashboard"),
            self._menu_button("Clientes", ft.Icons.PEOPLE, route="/contacts"),
            self._menu_button("Nova Campanha", ft.Icons.SEND, route="/campaigns"),
            self._menu_button("Agenda de Envios", ft.Icons.SCHEDULE, route="/schedule"),
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

        # 7 Stat Cards Controls
        self.stat_contacts = ft.Text("0", size=24, weight=ft.FontWeight.BOLD)
        self.stat_opt_in = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN)
        self.stat_blocked = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED)
        self.stat_campaigns = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE)
        self.stat_scheduled = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER)
        self.stat_sent = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN)
        self.stat_failed = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED)

        # Campaigns Table
        self.campaigns_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome da Campanha")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Agendamento")),
                ft.DataColumn(ft.Text("Total"), numeric=True),
                ft.DataColumn(ft.Text("Enviados"), numeric=True),
                ft.DataColumn(ft.Text("Falhas"), numeric=True),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[],
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        )
        self.empty_campaigns_text = ft.Text("Nenhuma campanha criada ainda.", italic=True, color=ft.Colors.ON_SURFACE_VARIANT)
        self.table_container = ft.Container(content=self.empty_campaigns_text)

        content = ft.Container(
            expand=True,
            padding=30,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Text("Dashboard", size=30, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.refresh_stats),
                        ft.ElevatedButton(
                            "Enviar atrasados", 
                            icon=ft.Icons.SEND_TIME_EXTENSION, 
                            bgcolor=ft.Colors.AMBER_800, 
                            color=ft.Colors.WHITE, 
                            on_click=self.send_due
                        )
                    ]),
                    ft.Divider(height=20),
                    
                    # 7 Cards Grid
                    ft.Row(
                        controls=[
                            self._stat_card("Total Contatos", self.stat_contacts, ft.Icons.PEOPLE, ft.Colors.BLUE_GREY),
                            self._stat_card("Com Opt-in", self.stat_opt_in, ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN),
                            self._stat_card("Blacklist", self.stat_blocked, ft.Icons.BLOCK, ft.Colors.RED),
                            self._stat_card("Campanhas", self.stat_campaigns, ft.Icons.CAMPAIGN, ft.Colors.BLUE),
                        ],
                        spacing=12,
                        wrap=True
                    ),
                    ft.Row(
                        controls=[
                            self._stat_card("Agendadas", self.stat_scheduled, ft.Icons.SCHEDULE, ft.Colors.AMBER),
                            self._stat_card("Enviados", self.stat_sent, ft.Icons.DONE_ALL, ft.Colors.GREEN),
                            self._stat_card("Falhas", self.stat_failed, ft.Icons.ERROR_OUTLINE, ft.Colors.RED),
                        ],
                        spacing=12,
                        wrap=True
                    ),
                    ft.Divider(height=25),
                    
                    ft.Text("Últimas Campanhas", size=20, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        expand=True,
                        content=ft.ListView(
                            expand=True,
                            controls=[self.table_container]
                        )
                    )
                ],
                spacing=12,
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

    def _stat_card(self, title, text_control, icon, icon_color):
        return ft.Container(
            width=200,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            content=ft.Row([
                ft.Icon(icon, size=32, color=icon_color),
                ft.Column([
                    ft.Text(title, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    text_control
                ], spacing=2)
            ], alignment=ft.MainAxisAlignment.START, spacing=12)
        )

    def refresh_stats(self, e=None):
        try:
            stats = campaigns.dashboard_stats()
            self.stat_contacts.value = str(stats.get('contacts', 0))
            self.stat_opt_in.value = str(stats.get('opt_in', 0))
            self.stat_blocked.value = str(stats.get('blocked', 0))
            self.stat_campaigns.value = str(stats.get('campaigns', 0))
            self.stat_scheduled.value = str(stats.get('scheduled', 0))
            self.stat_sent.value = str(stats.get('sent', 0))
            self.stat_failed.value = str(stats.get('failed', 0))
        except Exception as ex:
            print("Erro ao atualizar stats:", ex)

        self.load_campaigns_table()
        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def load_campaigns_table(self):
        try:
            items = campaigns.list_campaigns()
            if not items:
                self.table_container.content = self.empty_campaigns_text
            else:
                self.campaigns_table.rows.clear()
                for c in items[:10]: # Top 10 mais recentes
                    cid = c.get('id')
                    self.campaigns_table.rows.append(
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(str(cid))),
                            ft.DataCell(ft.Text(str(c.get('name') or ''))),
                            ft.DataCell(ft.Text(friendly_status(c.get('status')))),
                            ft.DataCell(ft.Text(str(c.get('scheduled_at') or ''))),
                            ft.DataCell(ft.Text(str(c.get('total_contacts') or 0))),
                            ft.DataCell(ft.Text(str(c.get('sent_contacts') or 0))),
                            ft.DataCell(ft.Text(str(c.get('failed_contacts') or 0))),
                            ft.DataCell(ft.TextButton("Ver", on_click=lambda e: self.navigate("/schedule"))),
                        ])
                    )
                self.table_container.content = self.campaigns_table
        except Exception as ex:
            self.table_container.content = ft.Text(f"Erro ao carregar campanhas: {str(ex)}", color=ft.Colors.ERROR)

    def send_due(self, e):
        def worker():
            try:
                due = campaigns.get_due_campaigns()
                if not due:
                    if hasattr(self, 'app_page') and self.app_page:
                        self.app_page.snack_bar = ft.SnackBar(ft.Text("Nenhuma campanha atrasada para enviar."))
                        self.app_page.snack_bar.open = True
                        self.app_page.update()
                    return
                for camp in due:
                    campaigns.send_campaign(int(camp['id']), runner="ui_due_button")
                if hasattr(self, 'app_page') and self.app_page:
                    self.app_page.snack_bar = ft.SnackBar(ft.Text(f"{len(due)} campanha(s) atrasada(s) processada(s)!"), bgcolor=ft.Colors.GREEN)
                    self.app_page.snack_bar.open = True
                    self.refresh_stats()
            except Exception as ex:
                if hasattr(self, 'app_page') and self.app_page:
                    self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Erro ao processar atrasadas: {str(ex)}"), bgcolor=ft.Colors.ERROR)
                    self.app_page.snack_bar.open = True
                    self.app_page.update()

        threading.Thread(target=worker, daemon=True).start()
        self.app_page.snack_bar = ft.SnackBar(ft.Text("Processamento de campanhas atrasadas iniciado em segundo plano."))
        self.app_page.snack_bar.open = True
        self.app_page.update()

    def did_mount(self):
        self.refresh_stats()

# Alias
DashboardScreen = Dashboard
