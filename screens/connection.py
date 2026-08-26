from __future__ import annotations

from typing import Mapping

import flet as ft

import network
import whatsapp
from screens import common


ROUTE = common.ROUTE_CONNECTION
WHATSAPP_WEB_URL = "https://web.whatsapp.com/"


STATUS_PRESENTATION = {
    whatsapp.WEB_STATUS_NOT_CONNECTED: ("Não conectado", ft.Icons.LINK_OFF, ft.Colors.ON_SURFACE_VARIANT),
    whatsapp.WEB_STATUS_WAITING_QR: ("Aguardando QR Code", ft.Icons.QR_CODE_2, ft.Colors.AMBER),
    whatsapp.WEB_STATUS_CONNECTED: ("Conectado", ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN),
    whatsapp.WEB_STATUS_ERROR: ("Erro", ft.Icons.ERROR_OUTLINE, ft.Colors.ERROR),
    whatsapp.WEB_STATUS_DISCONNECTED: ("Desconectado", ft.Icons.LINK_OFF, ft.Colors.ERROR),
}


class ConnectionScreen(ft.View):
    ROUTE = ROUTE

    def __init__(self, page: ft.Page):
        super().__init__(route=ROUTE, padding=0, key="connection-view")
        self.app_page = page
        self._busy = False

        self.internet_icon = ft.Icon(ft.Icons.WIFI, color=ft.Colors.ON_SURFACE_VARIANT, size=34)
        self.internet_title = ft.Text("Internet ainda não verificada", size=17, weight=ft.FontWeight.BOLD)
        self.internet_detail = ft.Text(
            "Use o teste antes de iniciar uma campanha.",
            color=ft.Colors.ON_SURFACE_VARIANT,
            key="internet-status-detail",
        )
        self.internet_progress = ft.ProgressRing(
            width=20,
            height=20,
            visible=False,
            semantics_label="Verificando internet",
            key="internet-test-progress",
        )
        self.test_button = ft.OutlinedButton(
            "Verificar internet",
            icon=ft.Icons.WIFI,
            key="test-internet-button",
            tooltip="Testar acesso ao WhatsApp e à Meta",
            on_click=self.test_internet,
        )

        self.web_icon = ft.Icon(ft.Icons.LINK_OFF, color=ft.Colors.ON_SURFACE_VARIANT, size=42)
        self.web_title = ft.Text("Não conectado", size=20, weight=ft.FontWeight.BOLD, key="web-status-title")
        self.web_detail = ft.Text(
            "Sessão local ainda não aberta.",
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            key="web-status-detail",
        )
        self.profile_detail = ft.Text(
            "",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            key="web-profile-path",
        )
        self.web_progress = ft.ProgressRing(
            width=22,
            height=22,
            visible=False,
            semantics_label="Abrindo sessão do WhatsApp Web",
            key="web-connect-progress",
        )
        self.connect_button = ft.FilledButton(
            "Iniciar ou reconectar sessão local",
            icon=ft.Icons.QR_CODE_2,
            key="connect-whatsapp-button",
            tooltip="Abrir o perfil local persistente do WhatsApp Web",
            on_click=self.connect_whatsapp,
        )
        self.refresh_button = ft.OutlinedButton(
            "Atualizar estado",
            icon=ft.Icons.REFRESH,
            key="refresh-whatsapp-status-button",
            on_click=self.refresh_web_status,
        )

        internet_card = ft.Container(
            padding=18,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            key="internet-status-card",
            content=ft.Row(
                [
                    self.internet_icon,
                    ft.Column([self.internet_title, self.internet_detail], spacing=3, expand=True),
                    self.internet_progress,
                    self.test_button,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        connection_card = ft.Container(
            padding=22,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            key="whatsapp-status-card",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.web_icon,
                            ft.Column(
                                [self.web_title, self.web_detail, self.profile_detail],
                                spacing=4,
                                expand=True,
                            ),
                            self.web_progress,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=10),
                    ft.Row(
                        [
                            self.connect_button,
                            self.refresh_button,
                            ft.OutlinedButton(
                                "Abrir WhatsApp Web no navegador",
                                icon=ft.Icons.OPEN_IN_NEW,
                                key="open-whatsapp-web-button",
                                tooltip="Abrir web.whatsapp.com sem usar o perfil automatizado",
                                on_click=self.open_whatsapp_web,
                            ),
                        ],
                        wrap=True,
                    ),
                ],
                spacing=10,
            ),
        )

        steps_card = ft.Container(
            padding=18,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=10,
            key="connection-instructions",
            content=ft.Column(
                [
                    ft.Text("Como conectar", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("1. Verifique a internet."),
                    ft.Text("2. Clique em 'Iniciar ou reconectar sessão local'."),
                    ft.Text("3. Escaneie o QR Code com o celular, se ele aparecer."),
                    ft.Text("4. Aguarde o estado 'Conectado' e mantenha a janela aberta durante os envios."),
                    ft.Divider(height=8),
                    ft.Text(
                        "O modo WhatsApp Web é experimental e não oficial. Para operação em "
                        "produção, prefira a API Oficial Meta e mantenha o modo simulação nos testes.",
                        color=ft.Colors.AMBER,
                        selectable=True,
                    ),
                ],
                spacing=7,
            ),
        )

        body = ft.ListView(
            controls=[internet_card, connection_card, steps_card],
            expand=True,
            spacing=12,
            padding=ft.Padding.only(right=8),
            key="connection-content-list",
            semantic_child_count=3,
        )
        self.controls = [
            common.screen_layout(
                page,
                ROUTE,
                "Conexão WhatsApp",
                body,
                subtitle="Teste a rede e acompanhe a sessão local persistente do WhatsApp Web.",
            )
        ]
        self._apply_snapshot(
            {
                "status": whatsapp.WEB_STATUS_NOT_CONNECTED,
                "label": "não conectado",
                "message": "O estado da sessão será verificado ao abrir a tela.",
            },
            update=False,
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.web_progress.visible = busy
        self.connect_button.disabled = busy
        self.refresh_button.disabled = busy
        common.safe_update(self.app_page)

    def _apply_snapshot(self, snapshot: Mapping[str, object], *, update: bool = True) -> None:
        status = str(snapshot.get("status") or whatsapp.WEB_STATUS_NOT_CONNECTED)
        default_title, icon, color = STATUS_PRESENTATION.get(
            status,
            (str(snapshot.get("label") or status), ft.Icons.INFO_OUTLINE, ft.Colors.ON_SURFACE_VARIANT),
        )
        self.web_icon.name = icon
        self.web_icon.color = color
        self.web_title.value = str(snapshot.get("label") or default_title).capitalize()
        self.web_title.color = color
        self.web_detail.value = str(snapshot.get("message") or "Estado sem detalhes.")
        profile = str(snapshot.get("profile_dir") or "").strip()
        self.profile_detail.value = f"Perfil local: {profile}" if profile else ""
        if update:
            common.safe_update(self.app_page)

    def test_internet(self, _event: object | None = None) -> None:
        self.internet_progress.visible = True
        self.test_button.disabled = True
        self.internet_title.value = "Verificando internet..."
        self.internet_title.color = ft.Colors.ON_SURFACE
        common.safe_update(self.app_page)

        def worker() -> None:
            try:
                connected = network.has_internet()
                self.internet_icon.name = ft.Icons.WIFI if connected else ft.Icons.WIFI_OFF
                self.internet_icon.color = ft.Colors.GREEN if connected else ft.Colors.ERROR
                self.internet_title.value = "Internet conectada" if connected else "Sem conexão com a internet"
                self.internet_title.color = ft.Colors.GREEN if connected else ft.Colors.ERROR
                self.internet_detail.value = (
                    "Acesso ao WhatsApp/Meta confirmado."
                    if connected
                    else "Verifique o Wi-Fi, cabo de rede, proxy ou firewall."
                )
            except Exception as exc:
                self.internet_icon.name = ft.Icons.WIFI_OFF
                self.internet_icon.color = ft.Colors.ERROR
                self.internet_title.value = "Falha ao testar a internet"
                self.internet_title.color = ft.Colors.ERROR
                self.internet_detail.value = str(exc)
            finally:
                self.internet_progress.visible = False
                self.test_button.disabled = False
                common.safe_update(self.app_page)

        common.run_in_background(self.app_page, worker)

    def open_whatsapp_web(self, _event: object | None = None) -> None:
        if common.open_url(self.app_page, WHATSAPP_WEB_URL):
            common.show_snack(
                self.app_page,
                "WhatsApp Web aberto. Escaneie o QR Code se necessário.",
            )

    def connect_whatsapp(self, _event: object | None = None) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.web_title.value = "Abrindo sessão..."
        self.web_title.color = ft.Colors.BLUE_ACCENT
        self.web_detail.value = "O navegador local pode solicitar a leitura do QR Code."
        common.safe_update(self.app_page)

        def worker() -> None:
            try:
                snapshot = whatsapp.open_whatsapp_web_session()
                self._apply_snapshot(snapshot, update=False)
                status = str(snapshot.get("status") or "")
                if status == whatsapp.WEB_STATUS_CONNECTED:
                    common.show_snack(self.app_page, "Sessão do WhatsApp Web conectada.")
                elif status == whatsapp.WEB_STATUS_WAITING_QR:
                    common.show_snack(
                        self.app_page,
                        "Leia o QR Code no navegador para concluir a conexão.",
                        bgcolor=ft.Colors.AMBER_800,
                    )
            except Exception as exc:
                self._apply_snapshot(
                    {
                        "status": whatsapp.WEB_STATUS_ERROR,
                        "label": "erro",
                        "message": str(exc),
                    },
                    update=False,
                )
                common.show_alert(
                    self.app_page,
                    "Não foi possível conectar",
                    str(exc),
                    key="whatsapp-connect-error-dialog",
                )
            finally:
                self._set_busy(False)

        common.run_in_background(self.app_page, worker)

    def refresh_web_status(self, _event: object | None = None) -> None:
        if self._busy:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                self._apply_snapshot(whatsapp.get_whatsapp_web_status(), update=False)
            except Exception as exc:
                self._apply_snapshot(
                    {
                        "status": whatsapp.WEB_STATUS_ERROR,
                        "label": "erro",
                        "message": str(exc),
                    },
                    update=False,
                )
            finally:
                self._set_busy(False)

        common.run_in_background(self.app_page, worker)

    def did_mount(self) -> None:
        self.test_internet()
        self.refresh_web_status()
