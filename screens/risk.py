# -*- coding: utf-8 -*-
import flet as ft
import compliance
import auth

LEVEL_LABELS = {
    'safe': 'Baixo',
    'warning': 'Atenção',
    'high': 'Alto',
    'critical': 'Crítico',
    'baixo': 'Baixo',
    'atencao': 'Atenção',
    'alto': 'Alto',
    'critico': 'Crítico'
}

def friendly_level(v):
    return LEVEL_LABELS.get(str(v or '').strip().lower(), str(v or ''))

def get_risk_color(score: int):
    if score >= 75:
        return ft.Colors.RED
    elif score >= 50:
        return ft.Colors.ORANGE
    elif score >= 25:
        return ft.Colors.AMBER
    return ft.Colors.GREEN


class RiskScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/risk", padding=0)
        self.app_page = page
        self.selected_risk = None
        self.risks_by_id = {}

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
            self._menu_button("Conferir Risco", ft.Icons.WARNING_AMBER, selected=True, route="/risk"),
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

        # Risk table
        self.risk_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Campanha")),
                ft.DataColumn(ft.Text("Risco (%)"), numeric=True),
                ft.DataColumn(ft.Text("Nível")),
                ft.DataColumn(ft.Text("Principal Motivo")),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[]
        )
        self.table_container = ft.Container(content=self.risk_table, expand=True)

        # Detail panel (right)
        self.detail_title = ft.Text("Selecione uma campanha", size=18, weight=ft.FontWeight.BOLD)
        self.progress_bar = ft.ProgressBar(value=0, color=ft.Colors.GREEN, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, height=12)
        self.score_label = ft.Text("0%", size=24, weight=ft.FontWeight.BOLD)
        self.level_label = ft.Text("", size=14)
        self.notes_list = ft.ListView(expand=True, spacing=6)

        detail_panel = ft.Container(
            width=360,
            padding=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=12,
            content=ft.Column(
                controls=[
                    self.detail_title,
                    ft.Divider(height=10),
                    ft.Row([self.score_label, self.level_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.progress_bar,
                    ft.Divider(height=15),
                    ft.Text("Cuidados & Recomendações:", weight=ft.FontWeight.BOLD),
                    self.notes_list
                ],
                spacing=10
            )
        )

        content = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Text("Conferir Risco & Compliance", size=28, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.load_risks),
                    ]),
                    ft.Text("Monitore a conformidade com as regras do WhatsApp e reduza o risco de bloqueios.", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Divider(height=15),
                    ft.Row([
                        ft.Container(content=ft.ListView(controls=[self.risk_table], expand=True), expand=True),
                        detail_panel
                    ], expand=True, spacing=16)
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

    def load_risks(self, e=None):
        self.risk_table.rows.clear()
        self.risks_by_id.clear()
        try:
            risks = compliance.list_campaign_risks()
            if not risks:
                self.detail_title.value = "Nenhuma campanha encontrada."
            else:
                for r in risks:
                    cid = int(r.get('campaign_id') or 0)
                    self.risks_by_id[cid] = r
                    score = int(r.get('score') or 0)
                    notes = r.get('notes') or []
                    first_note = notes[0] if notes else "Nenhum risco relevante detectado."
                    level_str = friendly_level(r.get('level'))
                    color = get_risk_color(score)

                    self.risk_table.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(str(cid))),
                                ft.DataCell(ft.Text(str(r.get('campaign_name') or ''))),
                                ft.DataCell(ft.Text(f"{score}%", weight=ft.FontWeight.BOLD, color=color)),
                                ft.DataCell(ft.Text(level_str, color=color)),
                                ft.DataCell(ft.Text(first_note[:60])),
                                ft.DataCell(ft.TextButton("Ver Análise", on_click=lambda e, c=cid: self.select_risk(c))),
                            ]
                        )
                    )
                if risks:
                    self.select_risk(int(risks[0].get('campaign_id')))
        except Exception as ex:
            self.detail_title.value = f"Erro: {str(ex)}"

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def select_risk(self, campaign_id: int):
        r = self.risks_by_id.get(campaign_id)
        if not r:
            return
        score = int(r.get('score') or 0)
        level_str = friendly_level(r.get('level'))
        color = get_risk_color(score)

        self.detail_title.value = f"Campanha #{campaign_id}: {r.get('campaign_name')}"
        self.score_label.value = f"{score}%"
        self.score_label.color = color
        self.level_label.value = f"Nível: {level_str}"
        self.level_label.color = color
        self.progress_bar.value = score / 100.0
        self.progress_bar.color = color

        self.notes_list.controls.clear()
        notes = r.get('notes') or []
        if not notes:
            self.notes_list.controls.append(ft.Text("✓ Campanha dentro dos parâmetros seguros recomendados.", color=ft.Colors.GREEN))
        else:
            for note in notes:
                self.notes_list.controls.append(ft.Text(f"• {note}", size=13))

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def did_mount(self):
        self.load_risks()
