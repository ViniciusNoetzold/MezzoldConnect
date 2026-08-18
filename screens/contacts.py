# -*- coding: utf-8 -*-
import flet as ft
import contacts
import auth

class ContactsScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/contacts", padding=0)
        self.app_page = page
        self.selected_folder = None
        self.selected_contact_id = None
        self.all_contacts_data = []

        user = auth.get_current_user() or "Usuário"
        role = auth.get_current_role() or "Cliente"

        # Sidebar
        menu_items = [
            ft.Row([ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, color=ft.Colors.BLUE_ACCENT), ft.Text("Mezzold", size=20, weight=ft.FontWeight.BOLD)]),
            ft.Text(f"{user}\nPerfil: {role}", size=13, color=ft.Colors.PRIMARY),
            ft.Divider(height=20),
            self._menu_button("Início", ft.Icons.HOME, route="/dashboard"),
            self._menu_button("Clientes", ft.Icons.PEOPLE, selected=True, route="/contacts"),
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

        # Left folder panel
        self.folders_list = ft.ListView(expand=True, spacing=6)
        folder_panel = ft.Container(
            width=280,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Text("Pastas de Clientes", size=18, weight=ft.FontWeight.BOLD),
                        ft.IconButton(ft.Icons.CREATE_NEW_FOLDER, tooltip="Nova Pasta", on_click=lambda _: self.create_folder_dialog()),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Divider(height=10),
                    self.folders_list,
                    ft.Divider(height=10),
                    ft.Row([
                        ft.ElevatedButton("Renomear", icon=ft.Icons.EDIT, on_click=lambda _: self.rename_folder_dialog(), expand=True),
                        ft.ElevatedButton("Excluir", icon=ft.Icons.DELETE_OUTLINE, color=ft.Colors.ERROR, on_click=lambda _: self.delete_folder_dialog(), expand=True),
                    ], spacing=6)
                ],
                spacing=8
            )
        )

        # Right Main panel
        self.folder_title = ft.Text("Selecione uma pasta", size=24, weight=ft.FontWeight.BOLD)
        self.folder_stats_text = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT)
        self.search_input = ft.TextField(
            label="Buscar por nome, telefone ou email",
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            on_submit=lambda _: self.refresh_contacts()
        )

        # Tab DataTables
        self.contacts_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Email")),
                ft.DataColumn(ft.Text("Opt-in")),
                ft.DataColumn(ft.Text("Blacklist")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[]
        )
        self.used_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Campanha")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Tentativas")),
                ft.DataColumn(ft.Text("Último Uso")),
            ],
            rows=[]
        )
        self.optin_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Origem Opt-in")),
                ft.DataColumn(ft.Text("Categoria")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[]
        )
        self.blacklist_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Telefone")),
                ft.DataColumn(ft.Text("Motivo")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[]
        )

        self.current_tab_index = 0
        self.tab_content_container = ft.Container(
            content=ft.ListView(controls=[self.contacts_table], expand=True),
            expand=True,
            padding=10
        )

        def switch_tab(index):
            self.current_tab_index = index
            if index == 0:
                self.tab_content_container.content = ft.ListView(controls=[self.contacts_table], expand=True)
            elif index == 1:
                self.tab_content_container.content = ft.ListView(controls=[self.optin_table], expand=True)
            elif index == 2:
                self.tab_content_container.content = ft.ListView(controls=[self.blacklist_table], expand=True)
            elif index == 3:
                self.tab_content_container.content = ft.ListView(controls=[self.used_table], expand=True)
            
            for i, btn in enumerate(self.tab_buttons):
                btn.style = ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_ACCENT if i == index else ft.Colors.SURFACE_CONTAINER,
                    color=ft.Colors.WHITE if i == index else ft.Colors.ON_SURFACE,
                    shape=ft.RoundedRectangleBorder(radius=8)
                )
            if hasattr(self, 'app_page') and self.app_page:
                self.app_page.update()

        self.tab_buttons = [
            ft.ElevatedButton("Contatos da Pasta", icon=ft.Icons.CONTACT_PAGE, on_click=lambda _: switch_tab(0)),
            ft.ElevatedButton("Com Opt-in", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, on_click=lambda _: switch_tab(1)),
            ft.ElevatedButton("Blacklist", icon=ft.Icons.BLOCK, on_click=lambda _: switch_tab(2)),
            ft.ElevatedButton("Já Usados / Histórico", icon=ft.Icons.HISTORY, on_click=lambda _: switch_tab(3)),
        ]
        switch_tab(0)

        self.tabs = ft.Column([
            ft.Row(controls=self.tab_buttons, spacing=8),
            self.tab_content_container
        ], expand=True, spacing=10)

        main_content = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Column([self.folder_title, self.folder_stats_text], spacing=2),
                        ft.Container(expand=True),
                        ft.ElevatedButton("Importar Contatos", icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: self.app_page.go("/import_contacts")),
                        ft.ElevatedButton("Novo Contato", icon=ft.Icons.PERSON_ADD, bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=lambda _: self.open_contact_dialog()),
                    ]),
                    ft.Divider(height=15),
                    ft.Row([
                        self.search_input,
                        ft.ElevatedButton("Filtrar", icon=ft.Icons.FILTER_LIST, on_click=lambda _: self.refresh_contacts()),
                        ft.ElevatedButton("Limpar", on_click=self.clear_search),
                    ]),
                    ft.Divider(height=10),
                    self.tabs
                ],
                spacing=10,
                expand=True
            )
        )

        self.controls = [
            ft.Row(
                controls=[sidebar, folder_panel, main_content],
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

    def clear_search(self, e):
        self.search_input.value = ""
        self.refresh_contacts()

    def load_folders(self):
        self.folders_list.controls.clear()
        try:
            folder_items = contacts.list_folders()
            if not folder_items:
                self.folders_list.controls.append(ft.Text("Nenhuma pasta.", italic=True))
            for f_item in folder_items:
                is_selected = self.selected_folder and self.selected_folder.get('id') == f_item.get('id')
                tile = ft.ListTile(
                    leading=ft.Icon(ft.Icons.FOLDER, color=ft.Colors.AMBER if is_selected else ft.Colors.BLUE_GREY),
                    title=ft.Text(str(f_item.get('name') or ''), weight=ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL),
                    subtitle=ft.Text(f"{f_item.get('total_contacts', 0)} contatos", size=11),
                    selected=bool(is_selected),
                    on_click=lambda e, f=f_item: self.on_folder_selected(f)
                )
                self.folders_list.controls.append(tile)
            
            if not self.selected_folder and folder_items:
                self.on_folder_selected(folder_items[0])
        except Exception as ex:
            self.folders_list.controls.append(ft.Text(f"Erro: {str(ex)}", color=ft.Colors.ERROR))

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def on_folder_selected(self, folder):
        self.selected_folder = folder
        self.folder_title.value = f"Pasta: {folder.get('name')}"
        self.load_folders()
        self.refresh_contacts()

    def refresh_contacts(self):
        if not self.selected_folder:
            return
        
        folder_name = self.selected_folder.get('name')
        search_text = (self.search_input.value or "").strip()

        try:
            items = contacts.list_contacts(search=search_text, group_name=folder_name)
            self.all_contacts_data = items
            
            total = len(items)
            opt_in_count = sum(1 for x in items if x.get('opt_in') and not x.get('blacklisted'))
            blacklist_count = sum(1 for x in items if x.get('blacklisted'))
            
            used_items = contacts.list_used_contacts(folder_name=folder_name, search=search_text)
            used_count = len(used_items)

            self.folder_stats_text.value = (
                f"Total: {total} | Com Opt-in: {opt_in_count} | Já Usados/Enviados: {used_count} | Blacklist: {blacklist_count}"
            )

            # Tab 1: Todos
            self.contacts_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(c.get('id')))),
                    ft.DataCell(ft.Text(str(c.get('name') or ''))),
                    ft.DataCell(ft.Text(str(c.get('phone') or ''))),
                    ft.DataCell(ft.Text(str(c.get('email') or ''))),
                    ft.DataCell(ft.Icon(ft.Icons.CHECK, color=ft.Colors.GREEN) if c.get('opt_in') else ft.Icon(ft.Icons.CLOSE, color=ft.Colors.RED)),
                    ft.DataCell(ft.Icon(ft.Icons.BLOCK, color=ft.Colors.RED) if c.get('blacklisted') else ft.Text("-")),
                    ft.DataCell(ft.Row([
                        ft.IconButton(ft.Icons.EDIT, tooltip="Editar", on_click=lambda e, cid=c.get('id'): self.open_contact_dialog(cid)),
                        ft.IconButton(ft.Icons.DELETE, tooltip="Excluir", icon_color=ft.Colors.ERROR, on_click=lambda e, cid=c.get('id'): self.delete_single_contact(cid)),
                    ], spacing=0))
                ])
                for c in items
            ]

            # Tab 2: Opt-in
            self.optin_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(c.get('id')))),
                    ft.DataCell(ft.Text(str(c.get('name') or ''))),
                    ft.DataCell(ft.Text(str(c.get('phone') or ''))),
                    ft.DataCell(ft.Text(str(c.get('opt_in_source') or ''))),
                    ft.DataCell(ft.Text(str(c.get('opt_in_category') or ''))),
                    ft.DataCell(ft.IconButton(ft.Icons.EDIT, tooltip="Editar", on_click=lambda e, cid=c.get('id'): self.open_contact_dialog(cid)))
                ])
                for c in items if c.get('opt_in') and not c.get('blacklisted')
            ]

            # Tab 3: Blacklist
            self.blacklist_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(c.get('id')))),
                    ft.DataCell(ft.Text(str(c.get('name') or ''))),
                    ft.DataCell(ft.Text(str(c.get('phone') or ''))),
                    ft.DataCell(ft.Text(str(c.get('consent_notes') or c.get('notes') or 'Bloqueado'))),
                    ft.DataCell(ft.IconButton(ft.Icons.EDIT, tooltip="Editar", on_click=lambda e, cid=c.get('id'): self.open_contact_dialog(cid)))
                ])
                for c in items if c.get('blacklisted')
            ]

            # Tab 4: Já Usados
            self.used_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(u.get('phone') or ''))),
                    ft.DataCell(ft.Text(str(u.get('recipient_name') or ''))),
                    ft.DataCell(ft.Text(str(u.get('campaign_name') or ''))),
                    ft.DataCell(ft.Text(str(u.get('status') or ''))),
                    ft.DataCell(ft.Text(str(u.get('attempts') or 1))),
                    ft.DataCell(ft.Text(str(u.get('last_sent_at') or ''))),
                ])
                for u in used_items
            ]

        except Exception as ex:
            self.show_snack(f"Erro ao listar contatos: {str(ex)}", ft.Colors.RED)

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def open_contact_dialog(self, contact_id=None):
        c_data = {}
        if contact_id:
            c_data = contacts.get_contact(contact_id) or {}

        folders = contacts.list_folders()
        folder_options = [ft.dropdown.Option(f['name'], f['name']) for f in folders]

        name_field = ft.TextField(label="Nome *", value=c_data.get('name', ''))
        phone_field = ft.TextField(label="Telefone (com DDD) *", value=c_data.get('phone', ''))
        email_field = ft.TextField(label="E-mail", value=c_data.get('email', ''))
        folder_dropdown = ft.Dropdown(
            label="Pasta", 
            options=folder_options,
            value=c_data.get('group_name', self.selected_folder['name'] if self.selected_folder else None)
        )
        opt_in_source = ft.TextField(label="Origem do opt-in", value=c_data.get('opt_in_source', 'manual'))
        opt_in_category = ft.TextField(label="Categoria do opt-in", value=c_data.get('opt_in_category', 'marketing'))
        opt_in_at = ft.TextField(label="Data do opt-in", value=str(c_data.get('opt_in_at', '')) if c_data.get('opt_in_at') else '')
        consent_notes = ft.TextField(label="Comprovante / Termo", value=c_data.get('consent_notes', ''))
        notes = ft.TextField(label="Observações internas", value=c_data.get('notes', ''), multiline=True)
        opt_in_switch = ft.Switch(label="Contato tem opt-in ativo", value=bool(c_data.get('opt_in', 1)))
        blacklist_switch = ft.Switch(label="Contato está em blacklist", value=bool(c_data.get('blacklisted', 0)))

        dlg = None

        def on_save(e):
            name_val = (name_field.value or "").strip()
            phone_val = (phone_field.value or "").strip()
            if not name_val or not phone_val:
                self.show_snack("Nome e telefone são obrigatórios.", ft.Colors.RED)
                return
            try:
                if contact_id:
                    contacts.update_contact(
                        contact_id,
                        name=name_val,
                        phone=phone_val,
                        email=email_field.value or '',
                        group_name=folder_dropdown.value or '',
                        opt_in=1 if opt_in_switch.value else 0,
                        opt_in_source=opt_in_source.value or '',
                        opt_in_category=opt_in_category.value or '',
                        opt_in_at=opt_in_at.value or '',
                        consent_notes=consent_notes.value or '',
                        notes=notes.value or '',
                        blacklisted=blacklist_switch.value
                    )
                    self.show_snack("Contato atualizado!")
                else:
                    contacts.add_contact(
                        name=name_val,
                        phone=phone_val,
                        email=email_field.value or '',
                        group_name=folder_dropdown.value or (self.selected_folder['name'] if self.selected_folder else ''),
                        opt_in=1 if opt_in_switch.value else 0,
                        opt_in_source=opt_in_source.value or 'manual',
                        opt_in_category=opt_in_category.value or 'marketing',
                        opt_in_at=opt_in_at.value or '',
                        consent_notes=consent_notes.value or '',
                        notes=notes.value or ''
                    )
                    self.show_snack("Contato cadastrado com sucesso!")
                dlg.open = False
                self.app_page.update()
                self.refresh_contacts()
                self.load_folders()
            except Exception as ex:
                self.show_snack(f"Erro ao salvar: {str(ex)}", ft.Colors.RED)

        actions = [
            ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
            ft.ElevatedButton("Salvar", bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=on_save),
        ]

        if contact_id:
            def on_opt_out(e):
                try:
                    contacts.mark_opt_out(contact_id, reason="Opt-out solicitado pelo cliente via interface.")
                    dlg.open = False
                    self.app_page.update()
                    self.refresh_contacts()
                    self.show_snack("Contato marcado como Opt-out / Blacklist.")
                except Exception as ex:
                    self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)

            actions.insert(0, ft.TextButton("Marcar Opt-out", icon=ft.Icons.BLOCK, icon_color=ft.Colors.AMBER, on_click=on_opt_out))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Editar Contato" if contact_id else "Novo Contato"),
            content=ft.Container(
                width=500,
                height=450,
                content=ft.ListView([
                    name_field, phone_field, email_field, folder_dropdown,
                    opt_in_source, opt_in_category, opt_in_at, consent_notes, notes,
                    opt_in_switch, blacklist_switch
                ])
            ),
            actions=actions
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def delete_single_contact(self, contact_id):
        dlg = None
        def confirm_del(e):
            try:
                contacts.delete_contact(contact_id)
                dlg.open = False
                self.app_page.update()
                self.refresh_contacts()
                self.load_folders()
                self.show_snack("Contato excluído.")
            except Exception as ex:
                self.show_snack(f"Erro: {str(ex)}", ft.Colors.RED)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Excluir Contato"),
            content=ft.Text("Tem certeza que deseja excluir este contato?"),
            actions=[
                ft.TextButton("Não", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Sim, Excluir", bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE, on_click=confirm_del),
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def create_folder_dialog(self):
        name_field = ft.TextField(label="Nome da Nova Pasta")
        dlg = None
        def on_create(e):
            v = (name_field.value or "").strip()
            if not v:
                return
            try:
                contacts.create_folder(v)
                dlg.open = False
                self.app_page.update()
                self.load_folders()
                self.show_snack(f"Pasta '{v}' criada com sucesso!")
            except Exception as ex:
                self.show_snack(f"Erro ao criar pasta: {str(ex)}", ft.Colors.RED)
                
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nova Pasta de Contatos"),
            content=name_field,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Criar", bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=on_create)
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def rename_folder_dialog(self):
        if not self.selected_folder:
            self.show_snack("Selecione uma pasta primeiro.", ft.Colors.AMBER)
            return
            
        name_field = ft.TextField(label="Novo nome da pasta", value=self.selected_folder['name'])
        dlg = None
        def on_rename(e):
            v = (name_field.value or "").strip()
            if not v:
                return
            try:
                contacts.rename_folder(self.selected_folder['id'], v)
                dlg.open = False
                self.selected_folder['name'] = v
                self.app_page.update()
                self.load_folders()
                self.on_folder_selected(self.selected_folder)
                self.show_snack("Pasta renomeada!")
            except Exception as ex:
                self.show_snack(f"Erro ao renomear: {str(ex)}", ft.Colors.RED)
                
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Renomear Pasta"),
            content=name_field,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Salvar", bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=on_rename)
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def delete_folder_dialog(self):
        if not self.selected_folder:
            self.show_snack("Selecione uma pasta para excluir.", ft.Colors.AMBER)
            return
            
        dlg = None
        def on_delete(e):
            try:
                moved_count = contacts.delete_folder(self.selected_folder['id'])
                dlg.open = False
                self.selected_folder = None
                self.app_page.update()
                self.load_folders()
                self.show_snack(f"Pasta excluída. {moved_count} contatos foram movidos para 'Importados'.")
            except Exception as ex:
                self.show_snack(f"Erro ao excluir pasta: {str(ex)}", ft.Colors.RED)
                
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Excluir Pasta"),
            content=ft.Text(f"Deseja excluir a pasta '{self.selected_folder['name']}'?\nOs contatos serão preservados e movidos para 'Importados'."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Excluir", bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE, on_click=on_delete)
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def did_mount(self):
        self.load_folders()
