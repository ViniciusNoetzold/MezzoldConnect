# -*- coding: utf-8 -*-
import flet as ft
import auth

class LoginScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(
            route="/",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            padding=0
        )
        self.app_page = page
        
        self.username_input = ft.TextField(
            label="Usuário", 
            width=320, 
            prefix_icon=ft.Icons.PERSON
        )
        self.password_input = ft.TextField(
            label="Senha", 
            width=320, 
            password=True, 
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            on_submit=self.login
        )
        self.error_text = ft.Text(color=ft.Colors.ERROR, size=14)
        
        self.login_container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, size=60, color=ft.Colors.BLUE_ACCENT),
                    ft.Text("Mezzold Connect", size=32, weight=ft.FontWeight.BOLD),
                    ft.Text("Faça login para continuar", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                    self.username_input,
                    self.password_input,
                    self.error_text,
                    ft.ElevatedButton(
                        "Entrar", 
                        width=320, 
                        height=48,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.BLUE_ACCENT,
                            color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(radius=8)
                        ),
                        on_click=self.login
                    ),
                    ft.TextButton(
                        "Não tem conta? Cadastre-se", 
                        on_click=self.register_view
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=14
            ),
            padding=40,
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=ft.Colors.BLACK38)
        )
        
        self.controls = [self.login_container]

    def login(self, e):
        username = (self.username_input.value or "").strip()
        password = (self.password_input.value or "").strip()
        
        if not username or not password:
            self.error_text.value = "Preencha todos os campos."
            if self.app_page:
                self.app_page.update()
            return
            
        success, role, is_active = auth.verify_login(username, password)
        if success and is_active:
            auth.set_current_user(username, role)
            if self.app_page:
                self.app_page.go("/dashboard")
        elif success and not is_active:
            self.error_text.value = "Usuário desativado. Contate o administrador."
            if self.app_page:
                self.app_page.update()
        else:
            self.error_text.value = "Usuário ou senha incorretos."
            if self.app_page:
                self.app_page.update()
            
    def register_view(self, e):
        self.error_text.value = ""
        self.reg_username = ft.TextField(label="Novo Usuário", width=320, prefix_icon=ft.Icons.PERSON)
        self.reg_password = ft.TextField(label="Nova Senha (mín. 8 caracteres)", width=320, password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK)
        self.reg_confirm = ft.TextField(label="Confirmar Senha", width=320, password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK)
        
        self.login_container.content.controls = [
            ft.Icon(ft.Icons.PERSON_ADD, size=60, color=ft.Colors.BLUE_ACCENT),
            ft.Text("Cadastrar Usuário", size=32, weight=ft.FontWeight.BOLD),
            ft.Text("Crie uma nova conta de acesso", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            self.reg_username,
            self.reg_password,
            self.reg_confirm,
            self.error_text,
            ft.ElevatedButton(
                "Cadastrar", 
                width=320, 
                height=48,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_700,
                    color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=8)
                ),
                on_click=self.do_register
            ),
            ft.TextButton(
                "Voltar para o Login", 
                on_click=self.back_to_login
            )
        ]
        if self.app_page:
            self.app_page.update()
        
    def back_to_login(self, e):
        self.error_text.value = ""
        self.login_container.content.controls = [
            ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, size=60, color=ft.Colors.BLUE_ACCENT),
            ft.Text("Mezzold Connect", size=32, weight=ft.FontWeight.BOLD),
            ft.Text("Faça login para continuar", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            self.username_input,
            self.password_input,
            self.error_text,
            ft.ElevatedButton(
                "Entrar", 
                width=320, 
                height=48,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_ACCENT,
                    color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=8)
                ),
                on_click=self.login
            ),
            ft.TextButton(
                "Não tem conta? Cadastre-se", 
                on_click=self.register_view
            )
        ]
        if self.app_page:
            self.app_page.update()

    def do_register(self, e):
        username = (self.reg_username.value or "").strip()
        password = (self.reg_password.value or "").strip()
        confirm = (self.reg_confirm.value or "").strip()
        
        if not username or not password or not confirm:
            self.error_text.value = "Preencha todos os campos."
            if self.app_page:
                self.app_page.update()
            return
            
        if password != confirm:
            self.error_text.value = "As senhas não coincidem."
            if self.app_page:
                self.app_page.update()
            return
            
        try:
            user_count = auth.user_count() if hasattr(auth, 'user_count') else 0
            role = auth.ROLE_ADMIN if user_count == 0 else auth.ROLE_CLIENTE
            auth.create_user(username, password, role=role)
            self.error_text.color = ft.Colors.GREEN
            self.error_text.value = "Conta criada com sucesso! Faça login."
            if self.app_page:
                self.app_page.update()
            import time
            time.sleep(1.2)
            self.error_text.color = ft.Colors.ERROR
            self.back_to_login(e)
        except Exception as ex:
            if "UNIQUE" in str(ex):
                self.error_text.value = "Este usuário já existe."
            else:
                self.error_text.value = f"Erro: {str(ex)}"
            if self.app_page:
                self.app_page.update()
