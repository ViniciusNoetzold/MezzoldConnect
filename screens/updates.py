from __future__ import annotations

import flet as ft

import app_update
import database
from screens import common


ROUTE = common.ROUTE_UPDATES
SETTING_MANIFEST_URL = "app_update_manifest_url"
SETTING_DOWNLOAD_URL = "app_update_download_url"
SETTING_CHANNEL = "app_update_channel"


class UpdatesScreen(ft.View):
    ROUTE = ROUTE

    def __init__(self, page: ft.Page):
        super().__init__(route=ROUTE, padding=0, key="updates-view")
        self.app_page = page
        self.last_result: app_update.UpdateCheckResult | None = None
        self._busy = False

        manifest_url = database.get_setting(SETTING_MANIFEST_URL, "")
        download_url = database.get_setting(
            SETTING_DOWNLOAD_URL,
            database.APP_DOWNLOAD_URL or app_update.DEFAULT_DOWNLOAD_URL,
        )
        channel = database.get_setting(SETTING_CHANNEL, app_update.DEFAULT_CHANNEL).strip() or app_update.DEFAULT_CHANNEL
        channels = list(dict.fromkeys([channel, "stable", "beta", "preview"]))

        self.manifest_field = ft.TextField(
            label="URL ou caminho do manifesto JSON",
            value=manifest_url,
            hint_text="https://.../update-manifest.json",
            prefix_icon=ft.Icons.DESCRIPTION,
            expand=True,
            key="update-manifest-input",
            tooltip="Aceita http(s), file:// ou caminho local",
        )
        self.channel_dropdown = ft.Dropdown(
            label="Canal",
            value=channel,
            options=[ft.dropdown.Option(value, value) for value in channels],
            width=180,
            key="update-channel-select",
            tooltip="Canal do manifesto a verificar",
        )
        self.download_field = ft.TextField(
            label="Página ou arquivo de download padrão",
            value=download_url,
            prefix_icon=ft.Icons.DOWNLOAD,
            key="update-download-input",
            tooltip="Fallback usado quando o manifesto não informa um download",
        )

        self.status_icon = ft.Icon(ft.Icons.SYSTEM_UPDATE, size=46, color=ft.Colors.BLUE_ACCENT)
        self.status_title = ft.Text(
            f"Versão instalada: {database.APP_VERSION}",
            size=20,
            weight=ft.FontWeight.BOLD,
            key="update-status-title",
        )
        self.status_detail = ft.Text(
            "Clique em 'Verificar agora' para consultar o manifesto configurado.",
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            key="update-status-detail",
        )
        self.metadata_text = ft.Text(
            "",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            key="update-metadata",
        )
        self.release_notes = ft.Text(
            "Nenhuma nota de versão carregada.",
            selectable=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
            key="update-release-notes",
        )
        self.progress = ft.ProgressRing(
            width=24,
            height=24,
            visible=False,
            semantics_label="Verificando atualizações",
            key="update-check-progress",
        )
        self.check_button = ft.FilledButton(
            "Verificar agora",
            icon=ft.Icons.REFRESH,
            key="check-updates-button",
            tooltip="Consultar o manifesto no canal selecionado",
            on_click=self.check_updates,
        )
        self.open_download_button = ft.OutlinedButton(
            "Abrir download",
            icon=ft.Icons.OPEN_IN_NEW,
            key="open-update-download-button",
            tooltip="Abrir a página ou arquivo indicado pelo manifesto",
            on_click=self.open_download,
        )

        settings_card = ft.Container(
            padding=18,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            key="update-settings-card",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Fonte de atualização", size=18, weight=ft.FontWeight.BOLD, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.HELP_OUTLINE,
                                key="update-manifest-help-button",
                                tooltip="Ver formato aceito do manifesto",
                                on_click=self.show_manifest_help,
                            ),
                        ]
                    ),
                    ft.Row([self.manifest_field, self.channel_dropdown]),
                    self.download_field,
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Salvar preferências",
                                icon=ft.Icons.SAVE,
                                key="save-update-settings-button",
                                on_click=self.save_preferences,
                            ),
                            self.check_button,
                            self.progress,
                        ],
                        wrap=True,
                    ),
                ],
                spacing=10,
            ),
        )

        status_card = ft.Container(
            padding=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            key="update-status-card",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.status_icon,
                            ft.Column(
                                [self.status_title, self.status_detail, self.metadata_text],
                                spacing=4,
                                expand=True,
                            ),
                            self.open_download_button,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=14),
                    ft.Text("Notas da versão", size=17, weight=ft.FontWeight.BOLD),
                    self.release_notes,
                    ft.Divider(height=10),
                    ft.Text(
                        "A verificação apenas informa a versão disponível e abre o download. "
                        "A instalação não é executada automaticamente.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        selectable=True,
                    ),
                ],
                spacing=8,
            ),
        )

        body = ft.ListView(
            [settings_card, status_card],
            expand=True,
            spacing=12,
            padding=ft.Padding.only(right=8),
            key="updates-content-list",
            semantic_child_count=2,
        )
        self.controls = [
            common.screen_layout(
                page,
                ROUTE,
                "Atualizações",
                body,
                subtitle="Verificação por manifesto e canal, usando as configurações locais do aplicativo.",
            )
        ]

    def save_preferences(self, _event: object | None = None, *, notify: bool = True) -> None:
        manifest_url = str(self.manifest_field.value or "").strip()
        download_url = str(self.download_field.value or "").strip() or app_update.DEFAULT_DOWNLOAD_URL
        channel = str(self.channel_dropdown.value or app_update.DEFAULT_CHANNEL).strip() or app_update.DEFAULT_CHANNEL
        database.set_settings(
            {
                SETTING_MANIFEST_URL: manifest_url,
                SETTING_DOWNLOAD_URL: download_url,
                SETTING_CHANNEL: channel,
            }
        )
        self.download_field.value = download_url
        if notify:
            common.show_snack(self.app_page, "Preferências de atualização salvas.")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.visible = busy
        self.check_button.disabled = busy
        common.safe_update(self.app_page)

    def check_updates(self, _event: object | None = None) -> None:
        if self._busy:
            return
        try:
            self.save_preferences(notify=False)
        except Exception as exc:
            common.show_snack(self.app_page, f"Não foi possível salvar as preferências: {exc}", error=True)
            return

        manifest_url = str(self.manifest_field.value or "").strip()
        download_url = str(self.download_field.value or "").strip() or app_update.DEFAULT_DOWNLOAD_URL
        channel = str(self.channel_dropdown.value or app_update.DEFAULT_CHANNEL).strip() or app_update.DEFAULT_CHANNEL
        self._set_busy(True)
        self.status_title.value = "Verificando atualizações..."
        self.status_title.color = ft.Colors.BLUE_ACCENT
        self.status_detail.value = f"Canal: {channel}"
        common.safe_update(self.app_page)

        def worker() -> None:
            try:
                result = app_update.check_for_updates(
                    database.APP_VERSION,
                    manifest_url,
                    download_url=download_url,
                    channel=channel,
                )
            except Exception as exc:
                result = app_update.UpdateCheckResult(
                    status="error",
                    current_version=database.APP_VERSION,
                    download_url=download_url,
                    manifest_url=manifest_url,
                    channel=channel,
                    error=str(exc),
                )
            try:
                self.last_result = result
                self._apply_result(result)
            finally:
                self._set_busy(False)

        common.run_in_background(self.app_page, worker)

    def _apply_result(self, result: app_update.UpdateCheckResult) -> None:
        self.release_notes.value = result.release_notes or "Nenhuma nota de versão informada."
        metadata = [f"Canal: {result.channel}"]
        if result.sha256:
            metadata.append(f"SHA-256: {result.sha256}")
        self.metadata_text.value = " | ".join(metadata)

        if result.status == "available":
            self.status_icon.name = ft.Icons.CLOUD_DOWNLOAD
            self.status_icon.color = ft.Colors.GREEN
            self.status_title.value = f"Nova versão disponível: {result.latest_version}"
            self.status_title.color = ft.Colors.GREEN
            self.status_detail.value = f"Instalada: {result.current_version}. O download está pronto para ser aberto."
            common.show_snack(self.app_page, f"A versão {result.latest_version} está disponível.")
        elif result.status == "current":
            self.status_icon.name = ft.Icons.CHECK_CIRCLE
            self.status_icon.color = ft.Colors.GREEN
            self.status_title.value = "Aplicativo atualizado"
            self.status_title.color = ft.Colors.GREEN
            self.status_detail.value = f"A versão {result.current_version} é a mais recente no canal selecionado."
        elif result.status == "no_manifest":
            self.status_icon.name = ft.Icons.INFO_OUTLINE
            self.status_icon.color = ft.Colors.AMBER
            self.status_title.value = "Manifesto não configurado"
            self.status_title.color = ft.Colors.AMBER
            self.status_detail.value = (
                "Informe a URL/caminho de um manifesto para comparar versões. "
                "A página de download padrão continua disponível."
            )
        else:
            self.status_icon.name = ft.Icons.ERROR_OUTLINE
            self.status_icon.color = ft.Colors.ERROR
            self.status_title.value = "Falha ao verificar atualizações"
            self.status_title.color = ft.Colors.ERROR
            self.status_detail.value = result.error or "O manifesto não pôde ser consultado."
        common.safe_update(self.app_page)

    def open_download(self, _event: object | None = None) -> None:
        target = (
            self.last_result.download_url
            if self.last_result and self.last_result.download_url
            else str(self.download_field.value or app_update.DEFAULT_DOWNLOAD_URL).strip()
        )
        common.open_url(self.app_page, target)

    def show_manifest_help(self, _event: object | None = None) -> None:
        sample = (
            "Formato mínimo aceito:\n\n"
            '{\n  "channels": {\n    "stable": {\n'
            '      "latest_version": "1.1.0",\n'
            '      "download_url": "https://exemplo/MezzoldConnect.exe",\n'
            '      "release_notes": "Correções e melhorias",\n'
            '      "sha256": "hash-opcional"\n'
            "    }\n  }\n}\n\n"
            "Também é possível usar latest_version/download_url na raiz do JSON."
        )
        common.show_alert(
            self.app_page,
            "Manifesto de atualização",
            sample,
            key="update-manifest-help-dialog",
        )
