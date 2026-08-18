# -*- coding: utf-8 -*-
import shutil
from datetime import datetime
import flet as ft
import auth
import whatsapp
import database
import startup
import app_update

ROLE_LABELS = {
    auth.ROLE_CLIENTE: 'Cliente',
    auth.ROLE_EQUIPE: 'Equipe',
    auth.ROLE_ADMIN: 'Administrador'
}

class SettingsScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/settings", padding=0)
        self.app_page = page
        self.user = auth.get_current_user() or "Usuário"
        self.role = auth.get_current_role() or "Cliente"
        self.is_admin = self.role == auth.ROLE_ADMIN or self.role == auth.ROLE_EQUIPE

        # Sidebar
        menu_items = [
            ft.Row([ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, color=ft.Colors.BLUE_ACCENT), ft.Text("Mezzold", size=20, weight=ft.FontWeight.BOLD)]),
            ft.Text(f"{self.user}\nPerfil: {self.role}", size=13, color=ft.Colors.PRIMARY),
            ft.Divider(height=20),
            self._menu_button("Início", ft.Icons.HOME, route="/dashboard"),
            self._menu_button("Clientes", ft.Icons.PEOPLE, route="/contacts"),
            self._menu_button("Nova Campanha", ft.Icons.SEND, route="/campaigns"),
            self._menu_button("Agenda de Envios", ft.Icons.SCHEDULE, route="/schedule"),
            self._menu_button("Conferir Risco", ft.Icons.WARNING_AMBER, route="/risk"),
            self._menu_button("Histórico", ft.Icons.HISTORY, route="/history"),
        ]

        if self.is_admin:
            menu_items.append(self._menu_button("Saúde do Número", ft.Icons.HEALTH_AND_SAFETY, route="/health"))

        menu_items.extend([
            self._menu_button("Configurações", ft.Icons.SETTINGS, selected=True, route="/settings"),
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

        # TAB 1: Minha Conta & Empresa
        self.company_name = ft.TextField(label="Nome da Empresa / Negócio", value=database.get_setting("company_name", "Mezzold"), width=400)
        self.old_password = ft.TextField(label="Senha Atual", password=True, can_reveal_password=True, width=400)
        self.new_password = ft.TextField(label="Nova Senha", password=True, can_reveal_password=True, width=400)
        self.confirm_new_password = ft.TextField(label="Confirmar Nova Senha", password=True, can_reveal_password=True, width=400)

        tab_account = ft.Container(
            padding=20,
            content=ft.ListView(
                controls=[
                    ft.Text("Dados da Empresa", size=18, weight=ft.FontWeight.BOLD),
                    self.company_name,
                    ft.ElevatedButton("Salvar Nome da Empresa", icon=ft.Icons.BUSINESS, on_click=self.save_company_name, width=240),
                    ft.Divider(height=30),
                    ft.Text("Alterar Senha de Acesso", size=18, weight=ft.FontWeight.BOLD),
                    self.old_password,
                    self.new_password,
                    self.confirm_new_password,
                    ft.ElevatedButton("Atualizar Senha", icon=ft.Icons.KEY, bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=self.change_password, width=200),
                ],
                spacing=12,
                expand=True
            )
        )

        # TAB 2: WhatsApp API
        self.cfg_token = ft.TextField(label="Token Permanente de Acesso (Meta Cloud API)", value=cfg.token or "", password=True, can_reveal_password=True, expand=True)
        self.cfg_phone_id = ft.TextField(label="ID do Número de Telefone (Phone Number ID)", value=cfg.phone_number_id or "", expand=True)
        self.cfg_business_id = ft.TextField(label="ID da Conta Comercial (Business Account ID)", value=cfg.business_account_id or "", expand=True)
        self.cfg_webhook = ft.TextField(label="URL de Callback / Webhook", value=cfg.webhook_url or "", expand=True)
        self.cfg_template = ft.TextField(label="Modelo Padrão Aprovado (Meta)", value=cfg.default_template or "", expand=True)
        self.cfg_language = ft.TextField(label="Idioma Padrão do Modelo", value=cfg.default_language or "pt_BR", width=180)
        self.cfg_delivery_mode = ft.Dropdown(
            label="Modo de Envio Padrão",
            value=cfg.delivery_mode or "whatsapp_web_experimental",
            options=[
                ft.dropdown.Option("official_api", "API Oficial Meta"),
                ft.dropdown.Option("whatsapp_web_experimental", "WhatsApp Web Experimental"),
                ft.dropdown.Option("manual_assisted", "Manual Assistido"),
            ],
            expand=True
        )
        self.cfg_daily_limit = ft.TextField(label="Limite Máximo Diário de Envios", value=str(cfg.daily_send_limit or 500), width=200)
        self.cfg_send_interval = ft.TextField(label="Intervalo Global entre Envios (segundos)", value=str(cfg.send_interval_seconds or 60.0), width=200)
        self.cfg_dry_run = ft.Switch(label="Modo Simulação / Teste (Dry-run): Não envia mensagens reais para clientes", value=bool(cfg.dry_run))
        self.cfg_block_high_risk = ft.Switch(label="Impedir envio automático de campanhas com alto risco de bloqueio", value=database.get_setting("block_high_risk_campaigns", "1") == "1")
        self.cfg_smart_send = ft.Switch(label="Usar pausas inteligentes automáticas entre disparos", value=database.get_setting("smart_send_enabled", "0") == "1")

        tab_api = ft.Container(
            padding=20,
            content=ft.ListView(
                controls=[
                    ft.Text("Credenciais WhatsApp Cloud API", size=18, weight=ft.FontWeight.BOLD),
                    self.cfg_token,
                    ft.Row([self.cfg_phone_id, self.cfg_business_id]),
                    self.cfg_webhook,
                    ft.Divider(height=20),
                    ft.Text("Modelos & Modos de Envio", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row([self.cfg_template, self.cfg_language, self.cfg_delivery_mode]),
                    ft.Row([self.cfg_daily_limit, self.cfg_send_interval]),
                    ft.Divider(height=20),
                    ft.Text("Segurança & Proteção Antiban", size=18, weight=ft.FontWeight.BOLD),
                    self.cfg_dry_run,
                    self.cfg_block_high_risk,
                    self.cfg_smart_send,
                    ft.Divider(height=20),
                    ft.ElevatedButton("Salvar Configurações da API", icon=ft.Icons.SAVE, bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=self.save_api_config, width=280),
                ],
                spacing=12,
                expand=True
            )
        )

        # TAB 3: Sistema & Backup
        self.startup_switch = ft.Switch(
            label="Iniciar Mezzold Connect automaticamente com o Windows",
            value=startup.is_startup_enabled() if hasattr(startup, 'is_startup_enabled') else False,
            on_change=self.toggle_startup
        )
        self.backup_status = ft.Text("", size=13)
        self.update_status = ft.Text(f"Versão Atual: {database.APP_VERSION}", size=13)

        tab_system = ft.Container(
            padding=20,
            content=ft.ListView(
                controls=[
                    ft.Text("Inicialização do Sistema", size=18, weight=ft.FontWeight.BOLD),
                    self.startup_switch,
                    ft.Divider(height=20),
                    ft.Text("Banco de Dados & Cópia de Segurança", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Local do banco SQLite: {database.DB_PATH}", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Row([
                        ft.ElevatedButton("Fazer Backup Agora", icon=ft.Icons.BACKUP, on_click=self.make_backup),
                    ]),
                    self.backup_status,
                    ft.Divider(height=20),
                    ft.Text("Atualizações do Aplicativo", size=18, weight=ft.FontWeight.BOLD),
                    self.update_status,
                    ft.ElevatedButton("Verificar Atualizações", icon=ft.Icons.SYSTEM_UPDATE, on_click=self.check_updates),
                ],
                spacing=12,
                expand=True
            )
        )

        # TAB 4: Gerenciar Usuários (Admin)
        self.users_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Usuário")),
                ft.DataColumn(ft.Text("Perfil")),
                ft.DataColumn(ft.Text("Ativo")),
                ft.DataColumn(ft.Text("Trocar Senha")),
                ft.DataColumn(ft.Text("Último Login")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[]
        )

        tab_users = ft.Container(
            padding=20,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Text("Gerenciamento de Acessos", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.ElevatedButton("Novo Usuário", icon=ft.Icons.PERSON_ADD, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=self.open_new_user_modal),
                        ft.ElevatedButton("Atualizar", icon=ft.Icons.REFRESH, on_click=self.load_users),
                    ]),
                    ft.Divider(height=10),
                    ft.Container(content=ft.ListView(controls=[self.users_table], expand=True), expand=True)
                ],
                spacing=10,
                expand=True
            )
        )

        self.s_tab_container = ft.Container(content=tab_account, expand=True)

        def switch_s_tab(index):
            if index == 0:
                self.s_tab_container.content = tab_account
            elif index == 1:
                self.s_tab_container.content = tab_api
            elif index == 2:
                self.s_tab_container.content = tab_system
            elif index == 3:
                self.s_tab_container.content = tab_users
                self.load_users()

            for i, btn in enumerate(self.s_tab_buttons):
                btn.style = ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_ACCENT if i == index else ft.Colors.SURFACE_CONTAINER,
                    color=ft.Colors.WHITE if i == index else ft.Colors.ON_SURFACE,
                    shape=ft.RoundedRectangleBorder(radius=8)
                )
            if hasattr(self, 'app_page') and self.app_page:
                self.app_page.update()

        self.s_tab_buttons = [
            ft.ElevatedButton("Minha Conta", icon=ft.Icons.ACCOUNT_CIRCLE, on_click=lambda _: switch_s_tab(0)),
            ft.ElevatedButton("WhatsApp API", icon=ft.Icons.API, on_click=lambda _: switch_s_tab(1)),
            ft.ElevatedButton("Sistema & Backup", icon=ft.Icons.COMPUTER, on_click=lambda _: switch_s_tab(2)),
        ]
        if self.is_admin:
            self.s_tab_buttons.append(ft.ElevatedButton("Gerenciar Usuários", icon=ft.Icons.MANAGE_ACCOUNTS, on_click=lambda _: switch_s_tab(3)))

        switch_s_tab(0)

        self.tabs = ft.Column([
            ft.Row(controls=self.s_tab_buttons, spacing=8),
            self.s_tab_container
        ], expand=True, spacing=10)

        content = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                controls=[
                    ft.Text("Configurações do Sistema", size=28, weight=ft.FontWeight.BOLD),
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

    def show_snackbar(self, msg, color=ft.Colors.GREEN):
        self.app_page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        self.app_page.snack_bar.open = True
        self.app_page.update()

    def save_company_name(self, e):
        v = (self.company_name.value or "").strip()
        if v:
            database.set_setting("company_name", v)
            self.show_snackbar("Nome da empresa atualizado!")

    def change_password(self, e):
        old_p = (self.old_password.value or "").strip()
        new_p = (self.new_password.value or "").strip()
        conf_p = (self.confirm_new_password.value or "").strip()

        if not old_p or not new_p or not conf_p:
            self.show_snackbar("Preencha todos os campos de senha.", ft.Colors.RED)
            return
        if new_p != conf_p:
            self.show_snackbar("A nova senha e a confirmação não coincidem.", ft.Colors.RED)
            return

        try:
            auth.change_password(self.user, old_p, new_p)
            self.old_password.value = ""
            self.new_password.value = ""
            self.confirm_new_password.value = ""
            self.show_snackbar("Senha alterada com sucesso!")
        except Exception as ex:
            self.show_snackbar(f"Erro ao alterar senha: {str(ex)}", ft.Colors.RED)

    def save_api_config(self, e):
        try:
            current_config = whatsapp.load_config()
            current_config.token = self.cfg_token.value or current_config.token
            current_config.phone_number_id = self.cfg_phone_id.value or current_config.phone_number_id
            current_config.business_account_id = self.cfg_business_id.value or current_config.business_account_id
            current_config.webhook_url = self.cfg_webhook.value or current_config.webhook_url
            current_config.default_template = self.cfg_template.value or current_config.default_template
            current_config.default_language = self.cfg_language.value or current_config.default_language
            current_config.delivery_mode = self.cfg_delivery_mode.value or current_config.delivery_mode

            try:
                current_config.daily_send_limit = int(self.cfg_daily_limit.value or current_config.daily_send_limit)
            except ValueError:
                pass
            try:
                current_config.send_interval_seconds = float(self.cfg_send_interval.value or current_config.send_interval_seconds)
            except ValueError:
                pass

            current_config.dry_run = bool(self.cfg_dry_run.value)

            token_to_save = self.cfg_token.value if self.cfg_token.value else None
            whatsapp.save_config(current_config, token_to_save=token_to_save)

            database.set_setting("block_high_risk_campaigns", "1" if self.cfg_block_high_risk.value else "0")
            database.set_setting("smart_send_enabled", "1" if self.cfg_smart_send.value else "0")

            self.show_snackbar("Configurações salvas com sucesso!")
        except Exception as ex:
            self.show_snackbar(f"Erro ao salvar configurações: {str(ex)}", ft.Colors.RED)

    def toggle_startup(self, e):
        if self.startup_switch.value:
            if hasattr(startup, 'enable_startup'):
                startup.enable_startup()
                self.show_snackbar("Inicialização automática com o Windows ativada.")
        else:
            if hasattr(startup, 'disable_startup'):
                startup.disable_startup()
                self.show_snackbar("Inicialização automática desativada.")

    def make_backup(self, e):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            data_dir = os.path.dirname(database.DB_PATH)
            backup_path = os.path.join(data_dir, f"backup_mezzold_{timestamp}.db")
            shutil.copy2(database.DB_PATH, backup_path)
            self.backup_status.value = f"✓ Backup criado com sucesso em: {backup_path}"
            self.backup_status.color = ft.Colors.GREEN
            self.show_snackbar("Backup realizado com sucesso!")
        except Exception as ex:
            self.backup_status.value = f"Erro no backup: {str(ex)}"
            self.backup_status.color = ft.Colors.RED
        self.app_page.update()

    def check_updates(self, e):
        try:
            res = app_update.check_for_updates() if hasattr(app_update, 'check_for_updates') else None
            if res and res.get('has_update'):
                self.update_status.value = f"Nova versão encontrada: {res.get('version')}! Acesse o portal para baixar."
                self.update_status.color = ft.Colors.BLUE
            else:
                self.update_status.value = "Você está utilizando a versão mais recente do Mezzold Connect."
                self.update_status.color = ft.Colors.GREEN
        except Exception as ex:
            self.update_status.value = f"Erro ao verificar atualizações: {str(ex)}"
            self.update_status.color = ft.Colors.RED
        self.app_page.update()

    def load_users(self, e=None):
        if not self.is_admin:
            return
        try:
            u_list = auth.list_users()
            self.users_table.rows = []
            for u in u_list:
                uid = int(u.get('id'))
                uname = str(u.get('username') or '')
                urole = str(u.get('role') or '')
                is_act = bool(u.get('is_active', True))
                must_ch = bool(u.get('must_change_password', False))
                last_l = str(u.get('last_login_at') or 'Nunca')

                toggle_btn = ft.IconButton(
                    icon=ft.Icons.TOGGLE_ON if is_act else ft.Icons.TOGGLE_OFF,
                    icon_color=ft.Colors.GREEN if is_act else ft.Colors.GREY,
                    tooltip="Desativar" if is_act else "Ativar",
                    on_click=lambda e, i=uid, act=is_act: self.toggle_user_active(i, act)
                )

                reset_btn = ft.IconButton(
                    icon=ft.Icons.LOCK_RESET,
                    tooltip="Redefinir Senha",
                    on_click=lambda e, i=uid, un=uname: self.open_reset_pw_modal(i, un)
                )

                self.users_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(uid))),
                            ft.DataCell(ft.Text(uname, weight=ft.FontWeight.BOLD)),
                            ft.DataCell(ft.Text(ROLE_LABELS.get(urole, urole))),
                            ft.DataCell(ft.Icon(ft.Icons.CHECK, color=ft.Colors.GREEN) if is_act else ft.Icon(ft.Icons.CLOSE, color=ft.Colors.RED)),
                            ft.DataCell(ft.Text("Sim" if must_ch else "Não")),
                            ft.DataCell(ft.Text(last_l[:16])),
                            ft.DataCell(ft.Row([toggle_btn, reset_btn], spacing=0)),
                        ]
                    )
                )
        except Exception as ex:
            self.show_snackbar(f"Erro ao listar usuários: {str(ex)}", ft.Colors.RED)

        if hasattr(self, 'app_page') and self.app_page:
            self.app_page.update()

    def toggle_user_active(self, user_id: int, current_active: bool):
        try:
            if current_active:
                auth.deactivate_user(user_id)
                self.show_snackbar("Usuário desativado.")
            else:
                auth.activate_user(user_id)
                self.show_snackbar("Usuário ativado.")
            self.load_users()
        except Exception as ex:
            self.show_snackbar(f"Erro: {str(ex)}", ft.Colors.RED)

    def open_reset_pw_modal(self, user_id: int, username: str):
        pw_field = ft.TextField(label="Nova Senha Provisória", password=True, can_reveal_password=True)
        dlg = None
        def on_reset(e):
            v = (pw_field.value or "").strip()
            if not v:
                return
            try:
                auth.reset_user_password(user_id, v, must_change_password=True)
                dlg.open = False
                self.app_page.update()
                self.show_snackbar(f"Senha de '{username}' redefinida com sucesso! Troca obrigatória no próximo login.")
                self.load_users()
            except Exception as ex:
                self.show_snackbar(f"Erro: {str(ex)}", ft.Colors.RED)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Redefinir Senha de {username}"),
            content=pw_field,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Redefinir", bgcolor=ft.Colors.BLUE_ACCENT, color=ft.Colors.WHITE, on_click=on_reset),
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def open_new_user_modal(self, e):
        uname_field = ft.TextField(label="Nome de Usuário *")
        upass_field = ft.TextField(label="Senha Inicial *", password=True, can_reveal_password=True)
        urole_field = ft.Dropdown(
            label="Perfil de Acesso",
            value=auth.ROLE_CLIENTE,
            options=[
                ft.dropdown.Option(auth.ROLE_CLIENTE, "Cliente"),
                ft.dropdown.Option(auth.ROLE_EQUIPE, "Equipe"),
                ft.dropdown.Option(auth.ROLE_ADMIN, "Administrador"),
            ]
        )
        dlg = None

        def on_create(e):
            un = (uname_field.value or "").strip()
            up = (upass_field.value or "").strip()
            if not un or not up:
                return
            try:
                auth.create_user(un, up, role=urole_field.value or auth.ROLE_CLIENTE, must_change_password=True)
                dlg.open = False
                self.app_page.update()
                self.show_snackbar(f"Usuário '{un}' criado com sucesso!")
                self.load_users()
            except Exception as ex:
                self.show_snackbar(f"Erro ao criar usuário: {str(ex)}", ft.Colors.RED)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cadastrar Novo Usuário"),
            content=ft.Column([uname_field, upass_field, urole_field], tight=True, spacing=12),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dlg, 'open', False) or self.app_page.update()),
                ft.ElevatedButton("Cadastrar", bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=on_create),
            ]
        )
        self.app_page.overlay.append(dlg)
        dlg.open = True
        self.app_page.update()

    def did_mount(self):
        self.load_users()
