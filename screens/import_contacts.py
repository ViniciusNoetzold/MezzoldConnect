# -*- coding: utf-8 -*-
import flet as ft
import contacts
import auth

class ImportContactsScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/import_contacts", padding=0)
        self.app_page = page
        self.selected_file = None
        
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

        self.file_label = ft.Text("Nenhum arquivo selecionado.", italic=True)
        
        # Folder options
        folders = contacts.list_folders()
        folder_options = [ft.dropdown.Option(f['name'], f['name']) for f in folders]
        default_val = folders[0]['name'] if folders else "Importados"
        self.folder_dropdown = ft.Dropdown(
            label="Pasta de Destino",
            options=folder_options,
            value=default_val,
            width=320
        )
        self.new_folder_input = ft.TextField(
            label="Ou digite o nome de uma nova pasta",
            width=320,
            hint_text="Deixe em branco para usar a selecionada acima"
        )

        # Opt-in settings
        self.opt_in_switch = ft.Switch(label="Definir contatos importados com Opt-in ativo", value=True)
        self.opt_in_source = ft.TextField(label="Origem do Opt-in", value="importacao_planilha", width=320)
        self.opt_in_category = ft.TextField(label="Categoria do Opt-in", value="marketing", width=320)
        self.consent_notes = ft.TextField(label="Termo / Comprovante", value="Importação de planilha/arquivo", width=320)

        self.import_results = ft.Text("", size=14)
        self.error_list_view = ft.ListView(height=150, spacing=4)

        def _on_pick_files(e):
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                path = filedialog.askopenfilename(
                    title="Selecione a planilha ou arquivo de contatos",
                    filetypes=[
                        ("Arquivos de Contatos", "*.xlsx;*.csv;*.txt"),
                        ("Planilhas Excel (*.xlsx)", "*.xlsx"),
                        ("Arquivos CSV (*.csv)", "*.csv"),
                        ("Arquivos de Texto (*.txt)", "*.txt"),
                        ("Todos os Arquivos (*.*)", "*.*")
                    ]
                )
                root.destroy()
                if path:
                    self.selected_file = path
                    self.file_label.value = f"Arquivo selecionado: {os.path.basename(path)}"
                    self.file_label.color = ft.Colors.GREEN
                else:
                    self.selected_file = None
                    self.file_label.value = "Nenhum arquivo selecionado."
                    self.file_label.color = None
                if hasattr(self, 'app_page') and self.app_page:
                    self.app_page.update()
            except Exception as ex:
                print("Erro ao abrir seletor:", ex)

        content = ft.Container(
            expand=True,
            padding=30,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: self.navigate("/contacts")),
                            ft.Text("Importar Contatos", size=28, weight=ft.FontWeight.BOLD),
                        ],
                        alignment=ft.MainAxisAlignment.START
                    ),
                    ft.Divider(height=15),
                    ft.Card(
                        elevation=1,
                        content=ft.Container(
                            padding=24,
                            content=ft.ListView(
                                expand=True,
                                controls=[
                                    ft.Text("1. Selecione o arquivo (Excel .xlsx, CSV ou TXT)", weight=ft.FontWeight.BOLD, size=16),
                                    ft.Row([
                                        ft.ElevatedButton("Escolher Arquivo", icon=ft.Icons.FOLDER_OPEN, on_click=_on_pick_files),
                                        self.file_label
                                    ], alignment=ft.MainAxisAlignment.START),
                                    ft.Text("Formatos aceitos: colunas Nome, Telefone, Email na primeira linha.", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ft.Divider(height=20),
                                    
                                    ft.Text("2. Destino e Organização", weight=ft.FontWeight.BOLD, size=16),
                                    ft.Row([self.folder_dropdown, self.new_folder_input], wrap=True, spacing=16),
                                    ft.Divider(height=20),
                                    
                                    ft.Text("3. Consentimento e LGPD", weight=ft.FontWeight.BOLD, size=16),
                                    self.opt_in_switch,
                                    ft.Row([self.opt_in_source, self.opt_in_category, self.consent_notes], wrap=True, spacing=16),
                                    ft.Divider(height=25),
                                    
                                    ft.ElevatedButton(
                                        "Iniciar Importação", 
                                        icon=ft.Icons.UPLOAD, 
                                        bgcolor=ft.Colors.BLUE_ACCENT, 
                                        color=ft.Colors.WHITE, 
                                        height=46,
                                        width=220,
                                        on_click=self.start_import
                                    ),
                                    ft.Divider(height=15),
                                    self.import_results,
                                    self.error_list_view
                                ]
                            )
                        )
                    )
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

    def start_import(self, e):
        if not self.selected_file:
            self.app_page.snack_bar = ft.SnackBar(ft.Text("Selecione um arquivo primeiro!"), bgcolor=ft.Colors.ERROR)
            self.app_page.snack_bar.open = True
            self.app_page.update()
            return
            
        target_folder = (self.new_folder_input.value or "").strip() or self.folder_dropdown.value or "Importados"
            
        try:
            self.import_results.value = "Importando contatos... Por favor aguarde."
            self.import_results.color = ft.Colors.BLUE
            self.error_list_view.controls.clear()
            self.app_page.update()
            
            default_opt_in = 1 if self.opt_in_switch.value else 0
            source = (self.opt_in_source.value or "").strip() or "importacao_planilha"
            cat = (self.opt_in_category.value or "").strip() or "marketing"
            notes = (self.consent_notes.value or "").strip() or "Importação de arquivo"
            
            summary = contacts.import_contacts(
                self.selected_file, 
                target_folder,
                default_opt_in=default_opt_in,
                opt_in_source=source,
                opt_in_category=cat,
                consent_notes=notes
            )
            
            err_count = len(summary.errors) if summary.errors else 0
            self.import_results.value = (
                f"Importação Concluída com Sucesso!\n"
                f"Pasta: '{target_folder}'\n"
                f"Novos Importados: {summary.imported} | Atualizados: {summary.updated} | Duplicados: {summary.duplicates} | Erros: {err_count}"
            )
            self.import_results.color = ft.Colors.GREEN

            if summary.errors:
                self.error_list_view.controls.append(ft.Text("Erros encontrados nas linhas:", weight=ft.FontWeight.BOLD, color=ft.Colors.ERROR))
                for err in summary.errors[:50]:
                    self.error_list_view.controls.append(ft.Text(f"- {err}", size=12, color=ft.Colors.RED))

            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Importação finalizada! {summary.imported} novos contatos adicionados."), bgcolor=ft.Colors.GREEN)
            self.app_page.snack_bar.open = True
            self.app_page.update()
            
        except Exception as ex:
            self.import_results.value = f"Falha na importação: {str(ex)}"
            self.import_results.color = ft.Colors.ERROR
            self.app_page.update()
