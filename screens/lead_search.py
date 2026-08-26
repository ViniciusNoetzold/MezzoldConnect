from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import flet as ft

import contact_service
from database import DEFAULT_CONTACT_FOLDER
from screens import common


ROUTE = common.ROUTE_LEAD_SEARCH
GOOGLE_MAPS_SEARCH_URL = "https://www.google.com/maps/search/"
LEAD_PHONE_RE = re.compile(r"(?:\+?55[\s().-]*)?(?:\(?\d{2}\)?[\s().-]*)?(?:9?\d{4})[\s().-]?\d{4}")
LEAD_NAME_BLOCKLIST = {
    "aberto",
    "agora",
    "fechado",
    "telefone",
    "whatsapp",
    "site",
    "rotas",
    "compartilhar",
    "salvar",
    "avaliacoes",
    "avaliacao",
    "horarios",
    "horario",
}


@dataclass
class LeadMergeSummary:
    total: int = 0
    round_found: int = 0
    added: int = 0
    duplicates: int = 0


@dataclass
class LeadImportSummary:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def _is_probable_lead_name(value: str) -> bool:
    text = " ".join(str(value or "").split()).strip(" -|")
    if len(text) < 3:
        return False
    lowered = text.casefold()
    if lowered.startswith(("http://", "https://", "www.")):
        return False
    if any(token in lowered for token in LEAD_NAME_BLOCKLIST):
        return False
    if LEAD_PHONE_RE.search(text):
        return False
    letters = sum(char.isalpha() for char in text)
    digits = sum(char.isdigit() for char in text)
    return letters >= 3 and digits <= max(2, letters)


def _guess_lead_name(lines: list[str], index: int) -> str:
    for offset in range(1, 6):
        previous_index = index - offset
        if previous_index < 0:
            break
        candidate = lines[previous_index].strip()
        if _is_probable_lead_name(candidate):
            return candidate
    return ""


def extract_leads_from_text(text: str) -> list[dict[str, str]]:
    """Extract unique Brazilian phones and their closest probable Maps name."""

    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        for raw_phone in LEAD_PHONE_RE.findall(line):
            phone = contact_service.normalize_phone(raw_phone)
            if not contact_service.is_valid_phone(phone) or phone in seen:
                continue
            seen.add(phone)
            found.append(
                {
                    "name": _guess_lead_name(lines, index) or f"Lead {len(found) + 1}",
                    "phone": phone,
                    "source": line,
                }
            )
    return found


def merge_lead_results(
    current: Iterable[dict[str, object]],
    incoming: Iterable[dict[str, object]],
) -> tuple[list[dict[str, str]], LeadMergeSummary]:
    """Merge extraction rounds by normalized phone, preserving the best name."""

    merged: list[dict[str, str]] = []
    by_phone: dict[str, dict[str, str]] = {}
    for lead in current:
        phone = contact_service.normalize_phone(str(lead.get("phone") or ""))
        if not contact_service.is_valid_phone(phone) or phone in by_phone:
            continue
        item = {
            "name": str(lead.get("name") or "").strip(),
            "phone": phone,
            "source": str(lead.get("source") or "").strip(),
        }
        by_phone[phone] = item
        merged.append(item)

    summary = LeadMergeSummary(total=len(merged))
    for index, lead in enumerate(incoming, start=1):
        summary.round_found += 1
        phone = contact_service.normalize_phone(str(lead.get("phone") or ""))
        if not contact_service.is_valid_phone(phone):
            continue
        name = str(lead.get("name") or "").strip() or f"Lead {index}"
        source = str(lead.get("source") or "").strip()
        existing = by_phone.get(phone)
        if existing:
            summary.duplicates += 1
            if name and existing.get("name", "").startswith("Lead "):
                existing["name"] = name
            if source and not existing.get("source"):
                existing["source"] = source
            continue
        item = {"name": name, "phone": phone, "source": source}
        by_phone[phone] = item
        merged.append(item)
        summary.added += 1
    summary.total = len(merged)
    return merged, summary


def import_leads(
    leads: Iterable[dict[str, object]],
    folder_name: str = "",
) -> LeadImportSummary:
    """Persist Maps leads through the v2 contact service (no separate service)."""

    summary = LeadImportSummary()
    target_folder = str(folder_name or "").strip() or DEFAULT_CONTACT_FOLDER
    contact_service.create_folder(target_folder)
    seen: set[str] = set()
    for index, lead in enumerate(leads, start=1):
        name = str(lead.get("name") or "").strip() or f"Lead {index}"
        phone = contact_service.normalize_phone(str(lead.get("phone") or ""))
        if not contact_service.is_valid_phone(phone):
            summary.skipped += 1
            summary.errors.append(f"Lead {index}: número inválido.")
            continue
        if phone in seen:
            summary.duplicates += 1
            continue
        seen.add(phone)
        try:
            _, updated = contact_service.upsert_contact(
                name=name,
                phone=phone,
                group_name=target_folder,
                opt_in=1,
                opt_in_source="google_maps",
                opt_in_category="marketing",
                consent_notes="Importado da tela Buscar leads.",
            )
        except contact_service.ContactError as exc:
            summary.skipped += 1
            summary.errors.append(f"Lead {index}: {exc}")
            continue
        if updated:
            summary.updated += 1
        else:
            summary.imported += 1
    return summary


class LeadSearchScreen(ft.View):
    ROUTE = ROUTE

    def __init__(self, page: ft.Page):
        super().__init__(route=ROUTE, padding=0, key="lead-search-view")
        self.app_page = page
        self.current_leads: list[dict[str, str]] = []
        self.selected_phones: set[str] = set()

        self.source_field = ft.TextField(
            label="Conteúdo copiado do Google Maps",
            hint_text="Cole aqui os resultados da busca...",
            multiline=True,
            min_lines=9,
            max_lines=14,
            key="lead-source-input",
            tooltip="Cole o texto copiado da lista de resultados do Google Maps",
        )
        self.folder_dropdown = ft.Dropdown(
            label="Importar para pasta",
            value=DEFAULT_CONTACT_FOLDER,
            options=[],
            expand=True,
            key="lead-folder-select",
            tooltip="Pasta de destino dos leads selecionados",
        )
        self.result_text = ft.Text(
            "Cole uma busca do Google Maps para extrair os telefones.",
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            key="lead-result-status",
        )
        self.selection_text = ft.Text("0 selecionado(s)", key="lead-selection-status")
        self.results_list = ft.ListView(
            controls=[],
            expand=True,
            spacing=6,
            key="lead-results-list",
            semantic_child_count=0,
        )

        instructions = ft.Container(
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            key="lead-instructions",
            content=ft.Column(
                [
                    ft.Text("Busca manual assistida", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "1. Abra o Google Maps e pesquise por nicho e cidade.\n"
                        "2. Copie os resultados visíveis e cole abaixo.\n"
                        "3. Extraia; novas rodadas são mescladas sem duplicar telefones.\n"
                        "4. Revise a seleção e importe para uma pasta.",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        selectable=True,
                    ),
                    ft.OutlinedButton(
                        "Abrir Google Maps",
                        icon=ft.Icons.MAP,
                        key="open-google-maps-button",
                        tooltip="Abrir a busca do Google Maps no navegador",
                        on_click=lambda _e: common.open_url(self.app_page, GOOGLE_MAPS_SEARCH_URL),
                    ),
                ],
                spacing=8,
            ),
        )

        left_panel = ft.Container(
            expand=3,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=10,
            content=ft.Column(
                [
                    instructions,
                    self.source_field,
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Extrair e mesclar",
                                icon=ft.Icons.MERGE,
                                key="extract-leads-button",
                                tooltip="Extrair telefones e mesclar com a lista atual",
                                on_click=self.extract_and_merge,
                            ),
                            ft.OutlinedButton(
                                "Limpar",
                                icon=ft.Icons.DELETE_SWEEP,
                                key="clear-leads-button",
                                on_click=self.clear_results,
                            ),
                        ],
                        wrap=True,
                    ),
                    self.result_text,
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        )

        right_panel = ft.Container(
            expand=2,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Leads encontrados", size=18, weight=ft.FontWeight.BOLD, expand=True),
                            self.selection_text,
                        ]
                    ),
                    ft.Row(
                        [
                            ft.TextButton(
                                "Selecionar todos",
                                icon=ft.Icons.SELECT_ALL,
                                key="select-all-leads-button",
                                on_click=self.select_all,
                            ),
                            ft.TextButton(
                                "Desmarcar",
                                icon=ft.Icons.DESELECT,
                                key="deselect-all-leads-button",
                                on_click=self.deselect_all,
                            ),
                        ],
                        wrap=True,
                    ),
                    ft.Divider(height=4),
                    self.results_list,
                    ft.Divider(height=4),
                    ft.Row(
                        [
                            self.folder_dropdown,
                            ft.IconButton(
                                icon=ft.Icons.CREATE_NEW_FOLDER,
                                key="create-lead-folder-button",
                                tooltip="Criar nova pasta",
                                on_click=self.open_new_folder_dialog,
                            ),
                        ]
                    ),
                    ft.FilledButton(
                        "Importar selecionados",
                        icon=ft.Icons.CONTACT_PHONE,
                        width=280,
                        key="import-selected-leads-button",
                        tooltip="Importar somente os leads marcados",
                        on_click=self.import_selected,
                    ),
                ],
                expand=True,
                spacing=8,
            ),
        )

        body = ft.Row(
            [left_panel, right_panel],
            expand=True,
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            key="lead-workspace",
        )
        self.controls = [
            common.screen_layout(
                page,
                ROUTE,
                "Buscar leads",
                body,
                subtitle="Extração local e assistida; nenhum serviço externo é adicionado ao app.",
            )
        ]
        self.refresh_folders()

    def refresh_folders(self) -> None:
        try:
            groups = contact_service.list_groups()
        except Exception as exc:
            groups = []
            self.result_text.value = f"Não foi possível listar as pastas: {exc}"
            self.result_text.color = ft.Colors.ERROR
        values = [DEFAULT_CONTACT_FOLDER, *groups]
        unique = list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
        self.folder_dropdown.options = [ft.dropdown.Option(value, value) for value in unique]
        if self.folder_dropdown.value not in unique:
            self.folder_dropdown.value = DEFAULT_CONTACT_FOLDER

    def extract_and_merge(self, _event: object | None = None) -> None:
        pasted = str(self.source_field.value or "").strip()
        if not pasted:
            common.show_snack(self.app_page, "Cole o conteúdo do Google Maps antes de extrair.", error=True)
            return
        incoming = extract_leads_from_text(pasted)
        if not incoming:
            self.result_text.value = "Nenhum telefone brasileiro válido foi encontrado nessa colagem."
            self.result_text.color = ft.Colors.AMBER
            common.safe_update(self.app_page)
            return

        previous_phones = {lead["phone"] for lead in self.current_leads}
        merged, summary = merge_lead_results(self.current_leads, incoming)
        self.current_leads = merged
        self.selected_phones.update(lead["phone"] for lead in merged if lead["phone"] not in previous_phones)
        try:
            saved_phones = {
                str(item.get("phone") or "") for item in contact_service.list_contacts()
            }
            already_saved = sum(1 for lead in incoming if lead["phone"] in saved_phones)
        except Exception:
            already_saved = 0
        self.result_text.value = (
            f"Rodada: {summary.round_found} identificado(s), {summary.added} novo(s), "
            f"{summary.duplicates} duplicado(s) na lista e {already_saved} já existente(s) no banco. "
            f"Total atual: {summary.total}."
        )
        self.result_text.color = ft.Colors.ON_SURFACE_VARIANT
        self.refresh_results()

    def refresh_results(self) -> None:
        controls: list[ft.Control] = []
        for lead in self.current_leads:
            phone = lead["phone"]
            source = lead.get("source", "")
            if len(source) > 95:
                source = source[:92] + "..."
            checkbox = ft.Checkbox(
                value=phone in self.selected_phones,
                key=f"lead-select-{phone}",
                tooltip=f"Selecionar {lead.get('name') or 'lead'}",
                on_change=lambda e, selected_phone=phone: self.toggle_selection(
                    selected_phone, bool(e.control.value)
                ),
            )
            controls.append(
                ft.Container(
                    padding=10,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=8,
                    key=f"lead-row-{phone}",
                    content=ft.Row(
                        [
                            checkbox,
                            ft.Column(
                                [
                                    ft.Text(lead.get("name") or "Lead", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"+{phone}", selectable=True),
                                    ft.Text(
                                        source,
                                        size=11,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        tooltip=lead.get("source") or "",
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ]
                    ),
                )
            )
        if not controls:
            controls.append(
                ft.Container(
                    padding=20,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        "Nenhum lead extraído.",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        italic=True,
                    ),
                    key="lead-results-empty",
                )
            )
        self.results_list.controls = controls
        self.results_list.semantic_child_count = len(self.current_leads)
        self.selection_text.value = f"{len(self.selected_phones)} selecionado(s)"
        common.safe_update(self.app_page)

    def toggle_selection(self, phone: str, selected: bool) -> None:
        if selected:
            self.selected_phones.add(phone)
        else:
            self.selected_phones.discard(phone)
        self.selection_text.value = f"{len(self.selected_phones)} selecionado(s)"
        common.safe_update(self.app_page)

    def select_all(self, _event: object | None = None) -> None:
        self.selected_phones = {lead["phone"] for lead in self.current_leads}
        self.refresh_results()

    def deselect_all(self, _event: object | None = None) -> None:
        self.selected_phones.clear()
        self.refresh_results()

    def clear_results(self, _event: object | None = None) -> None:
        self.source_field.value = ""
        self.current_leads.clear()
        self.selected_phones.clear()
        self.result_text.value = "Cole uma busca do Google Maps para extrair os telefones."
        self.result_text.color = ft.Colors.ON_SURFACE_VARIANT
        self.refresh_results()

    def import_selected(self, _event: object | None = None) -> None:
        payload = [lead for lead in self.current_leads if lead["phone"] in self.selected_phones]
        if not payload:
            common.show_snack(self.app_page, "Selecione pelo menos um lead para importar.", error=True)
            return
        folder = str(self.folder_dropdown.value or DEFAULT_CONTACT_FOLDER).strip()
        try:
            summary = import_leads(payload, folder)
        except Exception as exc:
            common.show_alert(
                self.app_page,
                "Falha ao importar leads",
                str(exc),
                key="lead-import-error-dialog",
            )
            return

        message = (
            f"Pasta: {folder}. Importados: {summary.imported}; atualizados: {summary.updated}; "
            f"duplicados: {summary.duplicates}; ignorados: {summary.skipped}."
        )
        self.result_text.value = message
        self.result_text.color = ft.Colors.GREEN
        if summary.errors:
            common.show_alert(
                self.app_page,
                "Importação concluída com avisos",
                message + "\n\n" + "\n".join(summary.errors[:8]),
                key="lead-import-summary-dialog",
            )
        else:
            common.show_snack(self.app_page, message)
        self.refresh_folders()
        common.safe_update(self.app_page)

    def open_new_folder_dialog(self, _event: object | None = None) -> None:
        field = ft.TextField(
            label="Nome da nova pasta",
            autofocus=True,
            key="new-lead-folder-input",
        )

        def create_folder(_event: object | None = None) -> None:
            name = str(field.value or "").strip()
            if not name:
                common.show_snack(self.app_page, "Informe o nome da pasta.", error=True)
                return
            try:
                contact_service.create_folder(name)
            except Exception as exc:
                common.show_snack(self.app_page, f"Não foi possível criar a pasta: {exc}", error=True)
                return
            common.close_dialog(self.app_page)
            self.refresh_folders()
            self.folder_dropdown.value = name
            common.safe_update(self.app_page)
            common.show_snack(self.app_page, f"Pasta '{name}' criada.")

        actions = [
            ft.TextButton(
                "Cancelar",
                key="cancel-lead-folder-button",
                on_click=lambda e: common.close_dialog(self.app_page, e),
            ),
            ft.FilledButton(
                "Criar pasta",
                key="confirm-lead-folder-button",
                on_click=create_folder,
            ),
        ]
        common.show_alert(
            self.app_page,
            "Nova pasta de leads",
            field,
            actions=actions,
            key="new-lead-folder-dialog",
        )

    def did_mount(self) -> None:
        self.refresh_results()
