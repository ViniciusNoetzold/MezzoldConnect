from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from database import APP_TITLE, DEFAULT_CONTACT_FOLDER


PHONE_PATTERN = re.compile(r"(?:(?:\+|00)?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\d{4}|\d{4})[-\s]?\d{4}")


def extract_phones_from_text(text: str) -> list[str]:
    from contacts import normalize_phone, is_valid_phone
    found: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"[\(\+\d][\d\s\-\(\)\.]{6,20}\d", text):
        raw = match.group(0)
        normalized = normalize_phone(raw)
        if is_valid_phone(normalized) and normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found


class LeadSearchMixin:
    def show_lead_search(self) -> None:
        import webbrowser
        import contact_service as _cs

        frame = self._screen("Buscar leads")

        instr = ttk.Frame(frame, style="Panel.TFrame", padding=14)
        instr.pack(fill="x", pady=(0, 12))
        ttk.Label(
            instr,
            text=(
                "Como buscar leads:\n"
                "1. Clique em 'Abrir Google Maps' abaixo.\n"
                "2. Pesquise por nicho e cidade (ex: 'oficina mecânica Sarandi RS').\n"
                "3. Selecione tudo na página (Ctrl+A), copie (Ctrl+C) e cole na caixa abaixo.\n"
                "4. Clique em 'Extrair telefones' — os números serão identificados automaticamente.\n"
                "5. Selecione os que deseja importar e clique em 'Importar'."
            ),
            style="Panel.TLabel",
            wraplength=860,
            justify="left",
        ).pack(anchor="w")
        ttk.Button(
            instr,
            text="Abrir Google Maps no navegador",
            command=lambda: webbrowser.open("https://www.google.com/maps/search/"),
        ).pack(anchor="w", pady=(10, 0))

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = ttk.Frame(body, style="Panel.TFrame", padding=12)
        right.pack(side="right", fill="y", minsize=280)

        ttk.Label(left, text="Cole o texto com os resultados da busca:", style="Panel.TLabel").pack(anchor="w")
        paste_area = tk.Text(left, height=14, wrap="word", font=("Segoe UI", 9))
        paste_area.pack(fill="both", expand=True, pady=(4, 8))

        result_var = tk.StringVar(value="")
        extract_btn = ttk.Button(left, text="Extrair telefones", style="Accent.TButton")
        extract_btn.pack(anchor="w")
        ttk.Label(left, textvariable=result_var, style="Muted.TLabel", wraplength=560).pack(anchor="w", pady=(8, 0))

        ttk.Label(right, text="Telefones encontrados:", style="Panel.TLabel").pack(anchor="w", pady=(0, 6))
        phones_frame = ttk.Frame(right)
        phones_frame.pack(fill="both", expand=True)
        phones_listbox = tk.Listbox(phones_frame, selectmode="extended", height=14)
        phones_listbox.pack(side="left", fill="both", expand=True)
        lb_scroll = ttk.Scrollbar(phones_frame, orient="vertical", command=phones_listbox.yview)
        lb_scroll.pack(side="right", fill="y")
        phones_listbox.configure(yscrollcommand=lb_scroll.set)

        ttk.Label(right, text="Importar para pasta:", style="Panel.TLabel").pack(anchor="w", pady=(10, 4))
        target_folder = tk.StringVar(value=DEFAULT_CONTACT_FOLDER)
        folder_combo = ttk.Combobox(right, textvariable=target_folder, state="readonly")
        folder_combo.pack(fill="x")

        def refresh_folders() -> None:
            folder_combo.configure(values=_cs.list_groups() or [DEFAULT_CONTACT_FOLDER])

        def new_folder() -> None:
            name = simpledialog.askstring(APP_TITLE, "Nome da nova pasta:", parent=right)
            if name:
                _cs.create_folder(name.strip())
                refresh_folders()
                target_folder.set(name.strip())

        ttk.Button(right, text="Nova pasta", command=new_folder).pack(fill="x", pady=(4, 0))

        found_phones: list[str] = []

        def do_extract() -> None:
            text = paste_area.get("1.0", "end")
            phones = extract_phones_from_text(text)
            found_phones.clear()
            found_phones.extend(phones)
            phones_listbox.delete(0, "end")
            for p in phones:
                phones_listbox.insert("end", p)
            result_var.set(f"{len(phones)} número(s) encontrado(s).")

        def do_import() -> None:
            folder = target_folder.get().strip() or DEFAULT_CONTACT_FOLDER
            sel = phones_listbox.curselection()
            to_import = [found_phones[i] for i in sel] if sel else list(found_phones)
            if not to_import:
                messagebox.showwarning(APP_TITLE, "Nenhum telefone para importar.")
                return
            _cs.create_folder(folder)
            imported = 0
            for phone in to_import:
                try:
                    _cs.add_contact("Lead", phone, group_name=folder, opt_in=1, opt_in_source="busca_manual")
                    imported += 1
                except _cs.ContactError:
                    pass
            result_var.set(f"{imported} contato(s) importado(s) para '{folder}'.")
            refresh_folders()

        extract_btn.configure(command=do_extract)

        import_btn = ttk.Button(right, text="Importar selecionados", style="Accent.TButton")
        import_btn.pack(fill="x", pady=(10, 0))
        import_btn.configure(command=do_import)
        ttk.Button(
            right, text="Importar todos",
            command=lambda: (phones_listbox.select_set(0, "end"), do_import()),
        ).pack(fill="x", pady=(4, 0))

        refresh_folders()
