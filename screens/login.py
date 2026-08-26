"""Tela de autenticação compatível com as regras de acesso da v1."""
from __future__ import annotations

import flet as ft

import app_log
import auth


class LoginScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(
            route="/",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            padding=20,
            bgcolor=ft.Colors.SURFACE,
        )
        self.app_page = page
        self.master_mode_active = False

        self.username_input = ft.TextField(
            label="Usuário",
            width=340,
            prefix_icon=ft.Icons.PERSON,
            autofocus=True,
            key="login-username",
            on_submit=lambda _event: self.app_page.run_task(self.password_input.focus),
        )
        self.password_input = ft.TextField(
            label="Senha",
            width=340,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            key="login-password",
            on_submit=self.login,
        )
        self.error_text = ft.Text("", color=ft.Colors.ERROR, size=14, key="login-message")
        self.login_button = ft.ElevatedButton(
            "Conectar",
            width=340,
            height=48,
            icon=ft.Icons.LOGIN,
            key="login-submit",
            on_click=self.login,
        )

        initial_note = (
            "Nenhum usuário está configurado. A configuração inicial deve ser feita "
            "por um administrador autorizado."
            if auth.user_count() == 0
            else "Entre para cuidar dos clientes e envios."
        )
        self.subtitle = ft.Text(
            initial_note,
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
            width=340,
        )

        panel = ft.Container(
            width=430,
            padding=42,
            border_radius=18,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            shadow=ft.BoxShadow(blur_radius=24, color=ft.Colors.BLACK26),
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, size=62, color=ft.Colors.BLUE_ACCENT),
                    ft.Text("Mezzold Connect", size=31, weight=ft.FontWeight.BOLD),
                    self.subtitle,
                    ft.Container(height=8),
                    self.username_input,
                    self.password_input,
                    self.error_text,
                    self.login_button,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=14,
            ),
        )
        self.controls = [panel]
        page.on_keyboard_event = self._keyboard_event

    def _keyboard_event(self, event: ft.KeyboardEvent) -> None:
        if (
            str(event.key or "").lower() == "m"
            and bool(event.ctrl)
            and bool(event.alt)
            and bool(event.shift)
        ):
            self.activate_master_mode()

    def activate_master_mode(self) -> None:
        if self.master_mode_active:
            return
        self.master_mode_active = True
        self.username_input.value = ""
        self.password_input.value = ""
        self.username_input.password = True
        self.username_input.can_reveal_password = False
        self.username_input.label = "Acesso autorizado"
        self.subtitle.value = "Modo de administração autorizado"
        self.error_text.value = ""
        app_log.log("MASTER_LOGIN_MODE_ACTIVATED")
        self.app_page.run_task(self.username_input.focus)
        self.app_page.update()

    def _set_busy(self, value: bool) -> None:
        self.login_button.disabled = value
        self.username_input.disabled = value
        self.password_input.disabled = value
        self.app_page.update()

    def _deny(self, message: str) -> None:
        self.error_text.color = ft.Colors.ERROR
        self.error_text.value = message
        self._set_busy(False)

    def login(self, _event: object | None = None) -> None:
        username = (self.username_input.value or "").strip()
        password = self.password_input.value or ""
        if not username:
            self._deny("Informe o usuário.")
            return
        if not password:
            self._deny("Informe a senha.")
            return

        self.error_text.value = ""
        self._set_busy(True)
        try:
            if self.master_mode_active:
                user = auth.ensure_master_admin(username, password)
            else:
                if auth.is_master_bootstrap_attempt(username, password):
                    app_log.log("MASTER_LOGIN_DENIED", "hotkey_not_active")
                    self._deny("Modo autorizado não foi ativado para esse acesso.")
                    return
                if auth.user_count() == 0:
                    self._deny(
                        "Nenhum usuário configurado. A configuração inicial deve ser feita "
                        "por um administrador autorizado."
                    )
                    return
                user = auth.authenticate(username, password)
                if user is None:
                    self._deny("Usuário ou senha não conferem.")
                    return
        except auth.AuthError as exc:
            event = "MASTER_LOGIN_DENIED" if self.master_mode_active else "LOGIN_DENIED"
            app_log.log(event, str(exc))
            self._deny(str(exc))
            return
        except Exception as exc:
            app_log.log("LOGIN_ERROR", repr(exc))
            self._deny("Não foi possível validar o acesso. Tente novamente.")
            return

        if bool(user.must_change_password):
            self._show_mandatory_password_dialog(user, password)
            self._set_busy(False)
            return

        auth.set_current_user(user)
        self.app_page.on_keyboard_event = None
        self.app_page.go("/dashboard")

    def _show_mandatory_password_dialog(self, user: auth.User, current_password: str) -> None:
        new_password = ft.TextField(
            label="Nova senha",
            password=True,
            can_reveal_password=True,
            key="mandatory-password",
        )
        confirmation = ft.TextField(
            label="Confirmar nova senha",
            password=True,
            can_reveal_password=True,
            key="mandatory-password-confirm",
        )
        error = ft.Text("", color=ft.Colors.ERROR)

        def change(_event: object | None = None) -> None:
            first = new_password.value or ""
            second = confirmation.value or ""
            if first != second:
                error.value = "As senhas não coincidem."
                self.app_page.update()
                return
            try:
                auth.change_password(user.id, current_password, first)
                updated = auth.get_user(user.id) or user
                auth.set_current_user(updated)
            except auth.AuthError as exc:
                error.value = str(exc)
                self.app_page.update()
                return
            self.app_page.pop_dialog()
            self.app_page.on_keyboard_event = None
            self.app_page.go("/dashboard")

        def cancel(_event: object | None = None) -> None:
            auth.clear_session()
            self.app_page.pop_dialog()
            self.password_input.value = ""
            self.error_text.value = "A troca de senha é obrigatória para entrar."
            self.app_page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Troca obrigatória de senha"),
            content=ft.Column(
                [
                    ft.Text("Defina uma senha pessoal antes de continuar."),
                    new_password,
                    confirmation,
                    error,
                ],
                tight=True,
                width=390,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cancel),
                ft.ElevatedButton("Alterar e entrar", key="mandatory-password-submit", on_click=change),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.app_page.show_dialog(dialog)


__all__ = ["LoginScreen"]
