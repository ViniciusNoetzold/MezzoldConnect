# -*- coding: utf-8 -*-
import webbrowser
import flet as ft
import campaigns
import contacts
import auth

STATUS_LABELS = {
    'enviado': 'Enviado',
    'falhou': 'Erro',
    'simulado': 'Teste',
    'pendente_manual': 'Aguardando manual',
    'bloqueado': 'Bloqueado',
    'sem_autorizacao': 'Sem autorização'
}

DELIVERY_MODES = {
    'official_api': 'API Oficial Meta',
    'whatsapp_web_experimental': 'WhatsApp Web',
    'manual_assisted': 'Manual'
}

def friendly_status(v):
    return STATUS_LABELS.get(str(v or '').strip(), str(v or ''))

def friendly_mode(v):
    return DELIVERY_MODES.get(str(v or '').strip(), str(v or ''))


class HistoryScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/history", padding=0)
        self.app_page = page

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
            self._menu_button("Histórico", ft.Icons.HISTORY, selected=True, route="/history"),
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

        # Logs Table
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Data/hora", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Campanha", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Contato", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Telefone", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Modo", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Erro", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Ação", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        )

        self.table_scroll_container = ft.ListView(
            controls=[self.data_table],
            expand=True
        )

        self.logs_container = ft.Container(
            expand=True,
            content=ft.ProgressRing()
        )

        content = ft.Container(
            expand=True,
            padding=30,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("Histórico de Disparos", size=28, weight=ft.FontWeight.BOLD),
                            ft.Container(expand=True),
                            ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.load_history),
                            ft.ElevatedButton("Telefones Já Usados", icon=ft.Icons.PHONE_IN_TALK, on_click=self.show_sent_numbers_dialog),
                        ]
                    ),
                    ft.Divider(height=15),
                    self.logs_container
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

    def load_history(self, e=None):
        try:
            logs = campaigns.list_logs()
            if not logs:
                self.logs_container.content = ft.Text("Nenhum envio registrado ainda.", size=16, color=ft.Colors.ON_SURFACE_VARIANT)
            else:
                self.data_table.rows = []
                for item in logs:
                    action_btn = None
                    action_url = item.get("action_url")
                    if action_url:
                        action_btn = ft.TextButton("Abrir WhatsApp", icon=ft.Icons.OPEN_IN_BROWSER, on_click=lambda e, u=action_url: webbrowser.open(u))

                    self.data_table.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(str(item.get("created_at") or "")[:19])),
                                ft.DataCell(ft.Text(str(item.get("campaign_name") or ""))),
                                ft.DataCell(ft.Text(str(item.get("recipient_name") or ""))),
                                ft.DataCell(ft.Text(str(item.get("phone") or ""))),
                                ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                                ft.DataCell(ft.Text(friendly_mode(item.get("delivery_mode")))),
                                ft.DataCell(ft.Text(str(item.get("error_message") or "")[:40])),
                                ft.DataCell(action_btn if action_btn else ft.Text("-")),
                            ]
                        )
                    )
                self.logs_container.content = self.table_scroll_container
        except Exception as ex:
            self.logs_container.content = ft.Text(f"Erro ao carregar histórico: {str(ex)}", color=ft.Colors.ERROR)

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def show_sent_numbers_dialog(self, e):
        try:
            used_list = contacts.list_used_phones()
        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {str(ex)}"), bgcolor=ft.Colors.ERROR)
            self.app_page.snack_bar.open = True
            self.app_page.update()
            return

        rows = []
        for item in used_list:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(item.get("phone") or ""))),
                ft.DataCell(ft.Text(str(item.get("recipient_name") or ""))),
                ft.DataCell(ft.Text(str(item.get("campaign_name") or ""))),
                ft.DataCell(ft.Text(friendly_status(item.get("status")))),
                ft.DataCell(ft.Text(str(item.get("attempts") or 1))),
                ft.DataCell(ft.Text(str(item.get("last_sent_at") or ""))),
            ]))

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Cliente")),
                ft.DataColumn(ft.Text("Campanha")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Tentativas")),
                ft.DataColumn(ft.Text("Última Vez")),
            ],
            rows=rows if rows else [ft.DataRow(cells=[ft.DataCell(ft.Text("Nenhum telefone utilizado ainda."))] + [ft.DataCell(ft.Text(""))]*5)]
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Telefones Já Contactados"),
            content=ft.Container(
                width=800,
                height=450,
                content=ft.ListView(controls=[table], expand=True)
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update())]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def did_mount(self):
        self.load_history()
