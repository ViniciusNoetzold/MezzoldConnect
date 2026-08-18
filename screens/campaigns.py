# -*- coding: utf-8 -*-
import threading
from datetime import datetime
import flet as ft
import campaigns
import contacts
import auth
import whatsapp

STATUS_LABELS = {
    'rascunho': 'Rascunho', 'agendada': 'Agendada', 'enviando': 'Em andamento',
    'concluída': 'Concluída', 'concluida': 'Concluída', 'pausada': 'Pausada',
    'cancelada': 'Cancelada', 'enviado': 'Enviado', 'erro': 'Erro'
}

def friendly_status(v):
    return STATUS_LABELS.get(str(v or '').strip(), str(v or ''))

def parse_variants(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    blocks = [b.strip() for b in text.split("\n---\n") if b.strip()]
    if len(blocks) > 1:
        return blocks
    return [line.strip() for line in text.splitlines() if line.strip()]


class CampaignsScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/campaigns", padding=0)
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
            self._menu_button("Nova Campanha", ft.Icons.SEND, selected=True, route="/campaigns"),
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

        cfg = whatsapp.load_config()

        # FORM CONTROLS (Left side)
        self.name_input = ft.TextField(label="Nome da Campanha *", expand=True)
        self.category_dropdown = ft.Dropdown(
            label="Tipo / Categoria",
            value="Marketing",
            width=220,
            options=[
                ft.dropdown.Option("Marketing", "Marketing"),
                ft.dropdown.Option("Aviso ou serviço", "Aviso ou serviço"),
                ft.dropdown.Option("Código de acesso", "Código de acesso"),
                ft.dropdown.Option("Atendimento", "Atendimento"),
            ]
        )
        self.template_name = ft.TextField(label="Nome do Modelo Aprovado (Meta Cloud)", value=cfg.default_template, expand=True)
        self.template_language = ft.TextField(label="Idioma", value=cfg.default_language or "pt_BR", width=120)
        self.delivery_mode_dropdown = ft.Dropdown(
            label="Modo de Envio",
            value=cfg.delivery_mode or "whatsapp_web_experimental",
            options=[
                ft.dropdown.Option("official_api", "API Oficial Meta"),
                ft.dropdown.Option("whatsapp_web_experimental", "WhatsApp Web Experimental"),
                ft.dropdown.Option("manual_assisted", "Manual Assistido"),
            ],
            expand=True
        )

        self.message_input = ft.TextField(
            label="Mensagem Principal *", 
            multiline=True, 
            min_lines=5, 
            max_lines=10,
            hint_text="Digite a mensagem principal que será enviada aos clientes..."
        )
        self.message_variants = ft.TextField(
            label="Variações da Mensagem (opcional)",
            multiline=True,
            min_lines=3,
            max_lines=6,
            hint_text="Escreva variações alternativas separadas por linha ou '---'"
        )

        self.media_path_input = ft.TextField(label="Caminho do Arquivo / Imagem / Link", expand=True)

        def _pick_media(e):
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                path = filedialog.askopenfilename(
                    title="Selecione a mídia ou arquivo da campanha",
                    filetypes=[
                        ("Arquivos de Mídia e Documentos", "*.png;*.jpg;*.jpeg;*.pdf;*.mp4;*.docx;*.xlsx;*.txt"),
                        ("Todos os Arquivos (*.*)", "*.*")
                    ]
                )
                root.destroy()
                if path:
                    self.media_path_input.value = path
                    if hasattr(self, 'app_page') and self.app_page:
                        self.app_page.update()
            except Exception as ex:
                print("Erro ao abrir seletor:", ex)

        self.media_variants_input = ft.TextField(
            label="Variações de Mídia (URLs alternativas, uma por linha)",
            multiline=True,
            min_lines=2,
            max_lines=4
        )

        self.send_mode_radio = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="now", label="Enviar agora"),
                ft.Radio(value="schedule", label="Agendar envio"),
            ]),
            value="now",
            on_change=self._on_send_mode_change
        )
        self.start_at_input = ft.TextField(
            label="Data/Hora de Envio",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            width=220,
            visible=False
        )

        self.delay_min_input = ft.TextField(label="Delay Mín (s)", value=str(campaigns.DEFAULT_DELAY_MIN_SECONDS), width=110, on_change=self._on_delay_change)
        self.delay_max_input = ft.TextField(label="Delay Máx (s)", value=str(campaigns.DEFAULT_DELAY_MAX_SECONDS), width=110, on_change=self._on_delay_change)
        self.delay_info_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        # TARGET FOLDER PANEL (Right side)
        folders = contacts.list_folders()
        folder_opts = [ft.dropdown.Option(f['name'], f['name']) for f in folders]
        default_folder = folders[0]['name'] if folders else "Importados"
        self.folder_dropdown = ft.Dropdown(
            label="Pasta de Clientes Alvo *",
            options=folder_opts,
            value=default_folder,
            expand=True,
            on_select=self._on_folder_change
        )
        self.folder_stats_text = ft.Text("Selecione uma pasta para ver o resumo dos contatos.", size=13)

        create_form_column = ft.Column(
            controls=[
                ft.Row([self.name_input, self.category_dropdown]),
                ft.Row([self.template_name, self.template_language, self.delivery_mode_dropdown]),
                self.message_input,
                self.message_variants,
                ft.Row([
                    self.media_path_input,
                    ft.ElevatedButton("Arquivo", icon=ft.Icons.ATTACH_FILE, on_click=_pick_media)
                ]),
                self.media_variants_input,
                ft.Divider(height=10),
                ft.Text("Agendamento e Ritmo de Envio", weight=ft.FontWeight.BOLD),
                ft.Row([self.send_mode_radio, self.start_at_input], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    self.delay_min_input,
                    self.delay_max_input,
                    ft.ElevatedButton("Usar Recomendação", on_click=self.apply_delay_recommendation),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.delay_info_text,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )

        folder_panel_container = ft.Container(
            width=320,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=10,
            content=ft.Column(
                controls=[
                    ft.Text("Público-Alvo", size=16, weight=ft.FontWeight.BOLD),
                    self.folder_dropdown,
                    ft.Row([
                        ft.ElevatedButton("Nova Pasta", icon=ft.Icons.FOLDER_SPECIAL, on_click=lambda _: self.app_page.go("/contacts"), expand=True),
                        ft.ElevatedButton("Importar", icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: self.app_page.go("/import_contacts"), expand=True),
                    ]),
                    ft.Divider(height=10),
                    ft.Container(
                        padding=12,
                        bgcolor=ft.Colors.SURFACE_CONTAINER,
                        border_radius=8,
                        content=self.folder_stats_text
                    ),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Criar e Iniciar Campanha", 
                        icon=ft.Icons.SEND, 
                        bgcolor=ft.Colors.BLUE_ACCENT, 
                        color=ft.Colors.WHITE, 
                        height=50,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                        on_click=self.create_campaign
                    )
                ],
                spacing=12
            )
        )

        tab_create = ft.Container(
            padding=16,
            content=ft.Row([
                ft.Container(content=create_form_column, expand=True, padding=10),
                folder_panel_container
            ], expand=True, spacing=16),
            expand=True
        )

        # TAB 2: Minhas Campanhas
        self.campaigns_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Pasta")),
                ft.DataColumn(ft.Text("Agendamento")),
                ft.DataColumn(ft.Text("Delay")),
                ft.DataColumn(ft.Text("Total"), numeric=True),
                ft.DataColumn(ft.Text("Enviados"), numeric=True),
                ft.DataColumn(ft.Text("Falhas"), numeric=True),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[]
        )
        self.campaigns_list_view = ft.ListView(controls=[self.campaigns_table], expand=True)

        tab_list = ft.Container(
            padding=16,
            content=ft.Column([
                ft.Row([
                    ft.Text("Todas as Campanhas", size=20, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.load_campaigns_list),
                    ft.ElevatedButton("Abrir Central de Envios", icon=ft.Icons.SCHEDULE, on_click=lambda _: self.app_page.go("/schedule")),
                ]),
                ft.Divider(height=10),
                ft.Container(content=self.campaigns_list_view, expand=True)
            ], expand=True)
        )

        self.tab_container = ft.Container(content=tab_create, expand=True)

        def switch_c_tab(index):
            if index == 0:
                self.tab_container.content = tab_create
            else:
                self.tab_container.content = tab_list
                self.load_campaigns_list()
            for i, btn in enumerate(self.c_tab_buttons):
                btn.style = ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_ACCENT if i == index else ft.Colors.SURFACE_CONTAINER,
                    color=ft.Colors.WHITE if i == index else ft.Colors.ON_SURFACE,
                    shape=ft.RoundedRectangleBorder(radius=8)
                )
            if hasattr(self, 'app_page') and self.app_page:
                self.app_page.update()

        self.c_tab_buttons = [
            ft.ElevatedButton("Nova Campanha", icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda _: switch_c_tab(0)),
            ft.ElevatedButton("Minhas Campanhas", icon=ft.Icons.LIST_ALT, on_click=lambda _: switch_c_tab(1)),
        ]
        switch_c_tab(0)

        self.tabs = ft.Column([
            ft.Row(controls=self.c_tab_buttons, spacing=8),
            self.tab_container
        ], expand=True, spacing=10)

        content = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                controls=[
                    ft.Text("Campanhas WhatsApp", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=10),
                    self.tabs
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

    def _on_send_mode_change(self, e):
        self.start_at_input.visible = (self.send_mode_radio.value == "schedule")
        self.app_page.update()

    def _on_delay_change(self, e):
        self.update_delay_info()

    def _on_folder_change(self, e):
        self.refresh_folder_stats()

    def update_delay_info(self):
        try:
            d_min, d_max = campaigns.normalize_campaign_delay(self.delay_min_input.value, self.delay_max_input.value)
            level, msg = campaigns.delay_recommendation_message(d_min, d_max)
            self.delay_info_text.value = f"Ritmo: {msg} (Intervalo: {d_min}s - {d_max}s)"
        except Exception as ex:
            self.delay_info_text.value = str(ex)
        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def apply_delay_recommendation(self, e=None):
        folder = self.folder_dropdown.value
        total = 0
        if folder:
            items = [c for c in contacts.list_contacts(group_name=folder) if c.get('opt_in') and not c.get('blacklisted')]
            total = len(items)
        r_min, r_max = campaigns.recommended_delay_for_contacts(total)
        self.delay_min_input.value = str(r_min)
        self.delay_max_input.value = str(r_max)
        self.update_delay_info()

    def refresh_folder_stats(self):
        folder = self.folder_dropdown.value
        if not folder:
            self.folder_stats_text.value = "Escolha uma pasta."
            return
        
        items = contacts.list_contacts(group_name=folder)
        total = len(items)
        opt_in_count = sum(1 for c in items if c.get('opt_in') and not c.get('blacklisted'))
        blacklist_count = sum(1 for c in items if c.get('blacklisted'))
        used_count = len(contacts.list_used_contacts(folder_name=folder))

        self.folder_stats_text.value = (
            f"Pasta: {folder}\n\n"
            f"• Total de contatos: {total}\n"
            f"• Liberados com Opt-in: {opt_in_count}\n"
            f"• Já enviados/usados: {used_count}\n"
            f"• Bloqueados (Blacklist): {blacklist_count}"
        )
        self.apply_delay_recommendation()

    def load_campaigns_list(self, e=None):
        try:
            items = campaigns.list_campaigns()
            self.campaigns_table.rows.clear()
            for c in items:
                cid = c.get('id')
                d_min = c.get('delay_min_seconds') or campaigns.DEFAULT_DELAY_MIN_SECONDS
                d_max = c.get('delay_max_seconds') or campaigns.DEFAULT_DELAY_MAX_SECONDS
                self.campaigns_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(str(cid))),
                        ft.DataCell(ft.Text(str(c.get('name') or ''))),
                        ft.DataCell(ft.Text(friendly_status(c.get('status')))),
                        ft.DataCell(ft.Text(str(c.get('folder_name') or ''))),
                        ft.DataCell(ft.Text(str(c.get('scheduled_at') or ''))),
                        ft.DataCell(ft.Text(f"{d_min}-{d_max}s")),
                        ft.DataCell(ft.Text(str(c.get('total_contacts') or 0))),
                        ft.DataCell(ft.Text(str(c.get('sent_contacts') or 0))),
                        ft.DataCell(ft.Text(str(c.get('failed_contacts') or 0))),
                        ft.DataCell(ft.TextButton("Gerenciar", on_click=lambda e: self.app_page.go("/schedule"))),
                    ])
                )
        except Exception as ex:
            self.show_snack(f"Erro ao listar campanhas: {str(ex)}", ft.Colors.RED)

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def create_campaign(self, e):
        name = (self.name_input.value or "").strip()
        message = (self.message_input.value or "").strip()
        folder = self.folder_dropdown.value

        if not name:
            self.show_snack("Informe o nome da campanha.", ft.Colors.RED)
            return
        if not message:
            self.show_snack("Digite a mensagem principal da campanha.", ft.Colors.RED)
            return
        if not folder:
            self.show_snack("Selecione a pasta de clientes.", ft.Colors.RED)
            return

        eligible = [c for c in contacts.list_contacts(group_name=folder) if c.get('opt_in') and not c.get('blacklisted')]
        if not eligible:
            self.show_snack("A pasta selecionada não possui contatos com Opt-in liberado.", ft.Colors.RED)
            return

        contact_ids = [int(c['id']) for c in eligible]

        try:
            d_min, d_max = campaigns.normalize_campaign_delay(self.delay_min_input.value, self.delay_max_input.value, len(contact_ids))
        except Exception as ex:
            self.show_snack(str(ex), ft.Colors.RED)
            return

        scheduled_val = None
        if self.send_mode_radio.value == "schedule":
            s_text = (self.start_at_input.value or "").strip()
            if not s_text:
                self.show_snack("Informe a data e hora do agendamento.", ft.Colors.RED)
                return
            scheduled_val = s_text

        category_map = {
            "Marketing": "marketing",
            "Aviso ou serviço": "utility",
            "Código de acesso": "authentication",
            "Atendimento": "service",
        }

        try:
            m_variants = parse_variants(self.message_variants.value)
            med_variants = parse_variants(self.media_variants_input.value)

            campaign_id = campaigns.create_campaign(
                name=name,
                message=message,
                contact_ids=contact_ids,
                media_path=self.media_path_input.value or "",
                template_name=self.template_name.value or "",
                template_language=self.template_language.value or "pt_BR",
                message_category=category_map.get(self.category_dropdown.value, "marketing"),
                message_variants=m_variants,
                media_variants=med_variants,
                folder_name=folder,
                scheduled_at=scheduled_val,
                delay_min_seconds=d_min,
                delay_max_seconds=d_max,
                delivery_mode=self.delivery_mode_dropdown.value or whatsapp.DELIVERY_MODE_OFFICIAL_API,
            )

            if self.send_mode_radio.value == "now":
                def worker():
                    campaigns.send_campaign(campaign_id, runner="ui_create_now")
                threading.Thread(target=worker, daemon=True).start()
                self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Campanha #{campaign_id} criada e disparo iniciado!"), bgcolor=ft.Colors.GREEN)
            else:
                self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Campanha #{campaign_id} agendada com sucesso!"), bgcolor=ft.Colors.GREEN)

            self.app_page.snack_bar.open = True
            self.app_page.go("/schedule")

        except Exception as ex:
            self.show_snack(f"Erro ao criar campanha: {str(ex)}", ft.Colors.RED)

    def did_mount(self):
        self.refresh_folder_stats()
        self.load_campaigns_list()
