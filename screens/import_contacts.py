"""Importação de contatos CSV, TXT e XLSX."""
from __future__ import annotations

import tempfile
from pathlib import Path

import flet as ft

import contacts
import database
from screens import common


class ImportContactsScreen(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/import_contacts", padding=0)
        self.app_page = page
        self.selected_file: str | None = None
        self._temporary_file: Path | None = None
        self.file_picker = ft.FilePicker()
        if hasattr(page, "services"):
            page.services.append(self.file_picker)

        self.file_label = ft.Text("Nenhum arquivo selecionado.", italic=True, key="import-file-name")
        folders = contacts.list_folders()
        folder_options = [ft.dropdown.Option(item["name"], item["name"]) for item in folders]
        default_value = folders[0]["name"] if folders else database.DEFAULT_CONTACT_FOLDER
        self.folder_dropdown = ft.Dropdown(
            label="Pasta de destino",
            options=folder_options,
            value=default_value,
            width=320,
            key="import-folder",
        )
        self.new_folder_input = ft.TextField(
            label="Ou crie uma nova pasta",
            width=320,
            hint_text="Deixe em branco para usar a pasta selecionada",
            key="import-new-folder",
        )
        self.opt_in_switch = ft.Switch(
            label="Definir contatos importados com opt-in ativo",
            value=True,
            key="import-opt-in",
        )
        self.opt_in_source = ft.TextField(
            label="Origem do opt-in",
            value="importacao_planilha",
            width=320,
        )
        self.opt_in_category = ft.TextField(
            label="Categoria do opt-in",
            value="marketing",
            width=320,
        )
        self.consent_notes = ft.TextField(
            label="Termo / comprovante",
            value="Importação de planilha/arquivo",
            width=320,
        )
        self.import_results = ft.Text("", size=14, selectable=True, key="import-result")
        self.error_list_view = ft.ListView(height=170, spacing=4)
        self.import_button = ft.ElevatedButton(
            "Iniciar importação",
            icon=ft.Icons.UPLOAD,
            height=46,
            width=220,
            key="import-submit",
            on_click=self.start_import,
        )

        body = ft.Card(
            content=ft.Container(
                padding=24,
                content=ft.ListView(
                    [
                        ft.Text("1. Selecione o arquivo", weight=ft.FontWeight.BOLD, size=16),
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "Escolher arquivo",
                                    icon=ft.Icons.FOLDER_OPEN,
                                    key="import-pick-file",
                                    on_click=self.pick_file,
                                ),
                                self.file_label,
                            ],
                            wrap=True,
                        ),
                        ft.Text(
                            "Aceitos: Excel .xlsx, CSV e TXT. A primeira linha pode conter Nome, Telefone e Email.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Divider(height=20),
                        ft.Text("2. Destino e organização", weight=ft.FontWeight.BOLD, size=16),
                        ft.Row([self.folder_dropdown, self.new_folder_input], wrap=True, spacing=16),
                        ft.Divider(height=20),
                        ft.Text("3. Consentimento e LGPD", weight=ft.FontWeight.BOLD, size=16),
                        self.opt_in_switch,
                        ft.Row(
                            [self.opt_in_source, self.opt_in_category, self.consent_notes],
                            wrap=True,
                            spacing=16,
                        ),
                        ft.Divider(height=22),
                        self.import_button,
                        self.import_results,
                        self.error_list_view,
                    ],
                    expand=True,
                    spacing=10,
                ),
            )
        )
        self.controls = [
            common.screen_layout(
                page,
                "/import_contacts",
                "Importar contatos",
                body,
                subtitle="Importe planilhas mantendo pastas, opt-in e deduplicação por telefone.",
                actions=[
                    ft.OutlinedButton(
                        "Voltar aos contatos",
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _event: page.go("/contacts"),
                    )
                ],
            )
        ]

    async def pick_file(self, _event: object | None = None) -> None:
        try:
            selected = await self.file_picker.pick_files(
                dialog_title="Selecione a planilha ou arquivo de contatos",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx", "csv", "txt"],
                allow_multiple=False,
                with_data=bool(getattr(self.app_page, "web", False)),
            )
            if not selected:
                return
            item = selected[0]
            suffix = Path(item.name).suffix.lower()
            if suffix not in {".xlsx", ".csv", ".txt"}:
                raise ValueError("Formato não suportado. Use XLSX, CSV ou TXT.")
            self._cleanup_temporary_file()
            if item.path:
                self.selected_file = item.path
            elif item.bytes is not None:
                imports_dir = database.DATA_DIR / "imports"
                imports_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    prefix="ui-import-",
                    suffix=suffix,
                    dir=imports_dir,
                    delete=False,
                ) as handle:
                    handle.write(item.bytes)
                    self._temporary_file = Path(handle.name)
                self.selected_file = str(self._temporary_file)
            else:
                raise RuntimeError("O seletor não forneceu o caminho ou os dados do arquivo.")
            self.file_label.value = f"Arquivo selecionado: {item.name}"
            self.file_label.color = ft.Colors.GREEN
            common.safe_update(self.app_page)
        except Exception as exc:
            common.show_snack(self.app_page, f"Erro ao escolher arquivo: {exc}", error=True)

    def start_import(self, _event: object | None = None) -> None:
        if not self.selected_file:
            common.show_snack(self.app_page, "Selecione um arquivo primeiro.", error=True)
            return
        target_folder = (
            (self.new_folder_input.value or "").strip()
            or self.folder_dropdown.value
            or database.DEFAULT_CONTACT_FOLDER
        )
        self.import_button.disabled = True
        self.import_results.value = "Importando contatos…"
        self.import_results.color = ft.Colors.BLUE
        self.error_list_view.controls.clear()
        common.safe_update(self.app_page)
        try:
            summary = contacts.import_contacts(
                self.selected_file,
                target_folder,
                default_opt_in=1 if self.opt_in_switch.value else 0,
                opt_in_source=(self.opt_in_source.value or "").strip() or "importacao_planilha",
                opt_in_category=(self.opt_in_category.value or "").strip() or "marketing",
                consent_notes=(self.consent_notes.value or "").strip() or "Importação de arquivo",
            )
            errors = list(summary.errors or [])
            self.import_results.value = (
                "Importação concluída.\n"
                f"Pasta: {target_folder}\n"
                f"Novos: {summary.imported} | Atualizados: {summary.updated} | "
                f"Duplicados: {summary.duplicates} | Erros: {len(errors)}"
            )
            self.import_results.color = ft.Colors.GREEN
            if errors:
                self.error_list_view.controls.append(
                    ft.Text("Linhas que não puderam ser importadas:", weight=ft.FontWeight.BOLD, color=ft.Colors.ERROR)
                )
                self.error_list_view.controls.extend(
                    ft.Text(f"• {error}", size=12, color=ft.Colors.RED) for error in errors[:50]
                )
            common.show_snack(
                self.app_page,
                f"Importação finalizada: {summary.imported} novo(s), {summary.updated} atualizado(s).",
            )
            self._cleanup_temporary_file()
        except Exception as exc:
            self.import_results.value = f"Falha na importação: {exc}"
            self.import_results.color = ft.Colors.ERROR
        finally:
            self.import_button.disabled = False
            common.safe_update(self.app_page)

    def _cleanup_temporary_file(self) -> None:
        if self._temporary_file is not None:
            try:
                self._temporary_file.unlink(missing_ok=True)
            except OSError:
                pass
        self._temporary_file = None


__all__ = ["ImportContactsScreen"]
