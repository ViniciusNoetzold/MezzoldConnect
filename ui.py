from __future__ import annotations

import shutil
import secrets
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import auth
import campaigns
import compliance
import contact_service as contacts
import network
import startup
import warmup
import whatsapp
from database import APP_TITLE, APP_VERSION, DB_PATH, DEFAULT_CONTACT_FOLDER, connect, get_setting, row_to_dict, set_setting


WHATSAPP_POLICY_URL = "https://www.whatsapp.com/legal/business-policy/"
META_CLOUD_API_URL = "https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview"

STATUS_LABELS = {
    "rascunho": "Rascunho",
    "agendada": "Agendada",
    "enviando": "Em andamento",
    "concluída": "Concluída",
    "concluida": "Concluída",
    "pausada": "Pausada",
    "cancelada": "Cancelada",
    "enviado": "Enviado",
    "simulado": "Teste",
    "pendente_manual": "Aguardando envio manual",
    "aguardando_manual": "Aguardando envio manual",
    "erro": "Erro",
    "falhou": "Erro",
    "bloqueado": "Bloqueado",
    "sem_autorizacao": "Sem autorização",
    "testing": "Em aquecimento",
    "healthy": "Saudável",
    "paused": "Pausado",
    "auto_paused": "Pausado pela saúde",
    "restricted": "Restrito",
    "banned": "Banido",
    "unknown": "Ainda sem dados",
    "high": "Boa",
    "medium": "Atenção",
    "low": "Ruim",
    "critical": "Crítico",
    "warning": "Atenção",
    "safe": "Baixo",
}


def friendly_status(value: object) -> str:
    text = str(value or "").strip()
    return STATUS_LABELS.get(text, text)


class MezzoldApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        self.current_user: auth.User | None = None
        self.content: ttk.Frame | None = None
        self.status_var = tk.StringVar(value="Tudo pronto.")
        self.running_events: dict[int, threading.Event] = {}
        self.running_warmups: dict[int, threading.Event] = {}
        self.current_screen = ""

        self._configure_style()
        self.show_login()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f6f7fb")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Sidebar.TFrame", background="#1f2937")
        style.configure("TLabel", background="#f6f7fb", foreground="#111827", font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background="#ffffff")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18), background="#f6f7fb")
        style.configure("Metric.TLabel", font=("Segoe UI Semibold", 20), background="#ffffff")
        style.configure("Muted.TLabel", foreground="#6b7280", background="#ffffff")
        style.configure("Sidebar.TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(12, 8))
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _clear(self) -> None:
        for child in self.winfo_children():
            child.destroy()

    def show_login(self) -> None:
        self._clear()
        wrapper = ttk.Frame(self, padding=32)
        wrapper.pack(fill="both", expand=True)

        panel = ttk.Frame(wrapper, style="Panel.TFrame", padding=28)
        panel.place(relx=0.5, rely=0.5, anchor="center", width=460)

        ttk.Label(panel, text=APP_TITLE, style="Panel.TLabel", font=("Segoe UI Semibold", 22)).pack(anchor="w")
        initial = auth.user_count() == 0
        subtitle = "Crie o primeiro acesso do sistema." if initial else "Entre para cuidar dos clientes e envios."
        ttk.Label(panel, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

        username = tk.StringVar()
        password = tk.StringVar()
        confirm = tk.StringVar()

        self._entry(panel, "Usuário", username).pack(fill="x", pady=(0, 12))
        self._entry(panel, "Senha", password, show="*").pack(fill="x", pady=(0, 12))
        confirm_frame = self._entry(panel, "Confirmar senha", confirm, show="*")
        if initial:
            confirm_frame.pack(fill="x", pady=(0, 12))

        def do_login() -> None:
            user = auth.authenticate(username.get(), password.get())
            if not user:
                messagebox.showerror(APP_TITLE, "Usuário ou senha não conferem.")
                return
            self.current_user = user
            self.show_main()

        def do_create() -> None:
            if initial and password.get() != confirm.get():
                messagebox.showerror(APP_TITLE, "As senhas não conferem.")
                return
            try:
                user = auth.create_user(username.get(), password.get())
            except auth.AuthError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            self.current_user = user
            messagebox.showinfo(APP_TITLE, "Acesso criado com sucesso.")
            self.show_main()

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Entrar", style="Accent.TButton", command=do_login).pack(side="left")
        ttk.Button(actions, text="Criar acesso", command=do_create).pack(side="left", padx=(8, 0))

    def show_main(self) -> None:
        self._clear()
        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=(16, 18))
        sidebar.pack(side="left", fill="y")
        ttk.Label(
            sidebar,
            text=APP_TITLE,
            foreground="#ffffff",
            background="#1f2937",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            sidebar,
            text=f"{self.current_user.username if self.current_user else ''}",
            foreground="#cbd5e1",
            background="#1f2937",
        ).pack(anchor="w", pady=(0, 18))

        buttons = [
            ("Início", self.show_dashboard),
            ("Clientes", self.show_contacts),
            ("Importar clientes", self.show_import_contacts),
            ("Nova campanha", self.show_create_campaign),
            ("Agenda de envios", self.show_schedule),
            ("Aquecer números", self.show_number_health),
            ("Conferir risco", self.show_risk),
            ("Histórico", self.show_history),
            ("Configurações", self.show_settings),
        ]
        for label, command in buttons:
            ttk.Button(sidebar, text=label, style="Sidebar.TButton", command=command).pack(fill="x", pady=3)

        ttk.Button(sidebar, text="Trocar usuário", command=self.show_login).pack(fill="x", side="bottom")

        main_area = ttk.Frame(shell)
        main_area.pack(side="left", fill="both", expand=True)
        self.content = ttk.Frame(main_area, padding=22)
        self.content.pack(fill="both", expand=True)
        status = ttk.Label(main_area, textvariable=self.status_var, anchor="w", padding=(10, 6))
        status.pack(fill="x", side="bottom")

        self.show_dashboard()
        self._resume_interrupted_campaigns()
        self.after(15000, self._scheduler_tick)

    def _screen(self, title: str) -> ttk.Frame:
        self.current_screen = title
        if self.content is None:
            raise RuntimeError("Área principal não inicializada.")
        for child in self.content.winfo_children():
            child.destroy()
        ttk.Label(self.content, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 16))
        frame = ttk.Frame(self.content)
        frame.pack(fill="both", expand=True)
        return frame

    def _scrollable_frame(self, parent: tk.Widget) -> ttk.Frame:
        canvas = tk.Canvas(parent, background="#f6f7fb", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def configure_inner(_event: object | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def configure_canvas(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", configure_inner)
        canvas.bind("<Configure>", configure_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return inner

    def _entry(self, parent: tk.Widget, label: str, variable: tk.StringVar, show: str | None = None) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        ttk.Label(frame, text=label, style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(frame, textvariable=variable, show=show).pack(fill="x")
        return frame

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def show_dashboard(self) -> None:
        frame = self._screen("Início")
        metrics = ttk.Frame(frame)
        metrics.pack(fill="x")

        stats = campaigns.dashboard_stats()
        labels = [
            ("Clientes", stats["contacts"]),
            ("Autorizados", stats["opt_in"]),
            ("Bloqueados", stats["blocked"]),
            ("Campanhas", stats["campaigns"]),
            ("Agendadas", stats["scheduled"]),
            ("Enviadas", stats["sent"]),
            ("Com erro", stats["failed"]),
        ]
        for label, value in labels:
            card = ttk.Frame(metrics, style="Panel.TFrame", padding=16)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, text=str(value), style="Metric.TLabel").pack(anchor="w")
            ttk.Label(card, text=label, style="Muted.TLabel").pack(anchor="w")

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=18)
        ttk.Button(actions, text="Atualizar", command=self.show_dashboard).pack(side="left")
        ttk.Button(actions, text="Enviar o que está atrasado", command=self._send_due_campaigns).pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="Últimas campanhas", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(12, 8))
        tree = self._campaign_tree(frame)
        tree.pack(fill="both", expand=True)
        self._fill_campaign_tree(tree)

    def show_contacts(self) -> None:
        return self._show_contacts_by_folder()

        frame = self._screen("Clientes")
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 10))
        search = tk.StringVar()
        folder_filter = tk.StringVar()
        ttk.Label(top, text="Buscar").pack(side="left")
        ttk.Entry(top, textvariable=search, width=34).pack(side="left", padx=(8, 8))
        ttk.Label(top, text="Pasta").pack(side="left")
        folder_combo = ttk.Combobox(top, textvariable=folder_filter, values=[""] + contacts.list_groups(), width=18, state="readonly")
        folder_combo.pack(side="left", padx=(8, 8))
        ttk.Button(top, text="Filtrar", command=lambda: refresh()).pack(side="left")
        ttk.Button(top, text="Importar lista", command=self.show_import_contacts).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Nova pasta", command=lambda: create_folder()).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Renomear pasta", command=lambda: rename_folder()).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Excluir pasta", command=lambda: delete_folder()).pack(side="left", padx=(8, 0))

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        tree_frame = ttk.Frame(body)
        tree_frame.pack(side="left", fill="both", expand=True)
        columns = ("id", "name", "phone", "group", "opt_in", "source", "blacklisted")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "ID",
            "name": "Cliente",
            "phone": "Telefone",
            "group": "Grupo",
            "opt_in": "Autorizado",
            "source": "Origem",
            "blacklisted": "Bloqueado",
        }
        widths = {"id": 55, "name": 190, "phone": 130, "group": 120, "opt_in": 70, "source": 130, "blacklisted": 90}
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        form = ttk.Frame(body, style="Panel.TFrame", padding=16)
        form.pack(side="right", fill="y", padx=(16, 0))
        selected_id = tk.IntVar(value=0)
        name = tk.StringVar()
        phone = tk.StringVar()
        email = tk.StringVar()
        group_name = tk.StringVar()
        notes = tk.StringVar()
        opt_in_source = tk.StringVar(value="manual")
        opt_in_category = tk.StringVar(value="marketing")
        opt_in_at = tk.StringVar()
        consent_notes = tk.StringVar()
        last_inbound_at = tk.StringVar()
        opt_in = tk.BooleanVar(value=True)
        blacklisted = tk.BooleanVar(value=False)

        for label, variable in [
            ("Nome do cliente", name),
            ("Telefone com DDD", phone),
            ("E-mail", email),
            ("Grupo/lista", group_name),
            ("Onde autorizou receber mensagens", opt_in_source),
            ("Tipo de mensagem autorizada", opt_in_category),
            ("Data da autorização", opt_in_at),
            ("Última resposta recebida", last_inbound_at),
            ("Comprovante ou observação da autorização", consent_notes),
            ("Observações internas", notes),
        ]:
            self._entry(form, label, variable).pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(form, text="Cliente autorizou receber mensagens", variable=opt_in).pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(form, text="Bloquear este cliente para envios", variable=blacklisted).pack(anchor="w", pady=(0, 12))

        def clear_form() -> None:
            selected_id.set(0)
            for variable in (name, phone, email, group_name, notes, consent_notes, opt_in_at, last_inbound_at):
                variable.set("")
            opt_in_source.set("manual")
            opt_in_category.set("marketing")
            opt_in.set(True)
            blacklisted.set(False)

        def refresh_folders() -> None:
            values = [""] + contacts.list_groups()
            folder_combo.configure(values=values)

        def create_folder() -> None:
            folder_name = simpledialog.askstring(APP_TITLE, "Nome da nova pasta:", parent=self)
            if not folder_name:
                return
            try:
                contacts.create_folder(folder_name)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders()
            folder_filter.set(folder_name.strip())
            group_name.set(folder_name.strip())
            refresh()

        def rename_folder() -> None:
            current_name = folder_filter.get().strip()
            if not current_name:
                messagebox.showwarning(APP_TITLE, "Escolha uma pasta para renomear.")
                return
            folder = next((item for item in contacts.list_folders() if str(item["name"]) == current_name), None)
            if not folder:
                messagebox.showerror(APP_TITLE, "Pasta não encontrada.")
                return
            new_name = simpledialog.askstring(APP_TITLE, "Novo nome da pasta:", initialvalue=current_name, parent=self)
            if not new_name:
                return
            try:
                contacts.rename_folder(int(folder["id"]), new_name)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders()
            folder_filter.set(new_name.strip())
            if group_name.get().strip() == current_name:
                group_name.set(new_name.strip())
            refresh()

        def delete_folder() -> None:
            current_name = folder_filter.get().strip()
            if not current_name:
                messagebox.showwarning(APP_TITLE, "Escolha uma pasta para excluir.")
                return
            folder = next((item for item in contacts.list_folders() if str(item["name"]) == current_name), None)
            if not folder:
                messagebox.showerror(APP_TITLE, "Pasta não encontrada.")
                return
            if int(folder.get("is_default") or 0):
                messagebox.showerror(APP_TITLE, "A pasta padrão não pode ser excluída.")
                return
            if not messagebox.askyesno(APP_TITLE, f"Excluir a pasta '{current_name}'? Os contatos serão movidos para Importados."):
                return
            try:
                moved = contacts.delete_folder(int(folder["id"]))
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders()
            folder_filter.set("Importados")
            if group_name.get().strip() == current_name:
                group_name.set("Importados")
            refresh()
            self._set_status(f"Pasta excluída. {moved} contato(s) movido(s) para Importados.")

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for item in contacts.list_contacts(search.get(), folder_filter.get()):
                tree.insert(
                    "",
                    "end",
                    values=(
                        item["id"],
                        item["name"],
                        item["phone"],
                        item["group_name"],
                        "Sim" if item["opt_in"] else "Não",
                        item.get("opt_in_source") or "",
                        "Sim" if item["blacklisted"] else "Não",
                    ),
                )
            self._set_status("Lista de clientes atualizada.")

        def on_select(_event: object) -> None:
            if not tree.selection():
                return
            item_id = tree.item(tree.selection()[0], "values")[0]
            data = contacts.get_contact(int(item_id))
            if not data:
                return
            selected_id.set(int(data["id"]))
            name.set(str(data["name"]))
            phone.set(str(data["phone"]))
            email.set(str(data["email"] or ""))
            group_name.set(str(data["group_name"] or ""))
            notes.set(str(data["notes"] or ""))
            opt_in_source.set(str(data.get("opt_in_source") or ""))
            opt_in_category.set(str(data.get("opt_in_category") or "marketing"))
            opt_in_at.set(str(data.get("opt_in_at") or ""))
            consent_notes.set(str(data.get("consent_notes") or ""))
            last_inbound_at.set(str(data.get("last_inbound_at") or ""))
            opt_in.set(bool(data["opt_in"]))
            blacklisted.set(bool(data["blacklisted"]))

        def save() -> None:
            try:
                if selected_id.get():
                    contacts.update_contact(
                        selected_id.get(),
                        name=name.get(),
                        phone=phone.get(),
                        email=email.get(),
                        group_name=group_name.get(),
                        notes=notes.get(),
                        opt_in=opt_in.get(),
                        opt_in_source=opt_in_source.get(),
                        opt_in_category=opt_in_category.get(),
                        opt_in_at=opt_in_at.get(),
                        consent_notes=consent_notes.get(),
                        last_inbound_at=last_inbound_at.get(),
                        blacklisted=blacklisted.get(),
                    )
                else:
                    new_id = contacts.add_contact(
                        name.get(),
                        phone.get(),
                        email.get(),
                        group_name.get(),
                        int(opt_in.get()),
                        opt_in_source.get(),
                        opt_in_category.get(),
                        opt_in_at.get(),
                        consent_notes.get(),
                        notes.get(),
                    )
                    selected_id.set(new_id)
                    contacts.set_blacklist(new_id, blacklisted.get())
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh()
            self._set_status("Cliente salvo.")

        def delete() -> None:
            if not selected_id.get():
                return
            if not messagebox.askyesno(APP_TITLE, "Excluir este cliente?"):
                return
            contacts.delete_contact(selected_id.get())
            clear_form()
            refresh()

        tree.bind("<<TreeviewSelect>>", on_select)

        ttk.Button(form, text="Novo", command=clear_form).pack(fill="x", pady=(4, 6))
        ttk.Button(form, text="Salvar", style="Accent.TButton", command=save).pack(fill="x", pady=6)
        ttk.Button(form, text="Marcar como pediu para sair", command=lambda: mark_opt_out()).pack(fill="x", pady=6)
        ttk.Button(form, text="Excluir", command=delete).pack(fill="x", pady=6)

        def mark_opt_out() -> None:
            if not selected_id.get():
                return
            contacts.mark_opt_out(selected_id.get(), "Cliente pediu para nao receber mais mensagens.")
            refresh()
            clear_form()
        refresh()

    def _show_contacts_by_folder(self) -> None:
        frame = self._screen("Clientes")
        search = tk.StringVar()
        selected_folder = tk.StringVar()
        selected_title = tk.StringVar(value="Selecione uma pasta")
        count_text = tk.StringVar(value="")
        empty_text = tk.StringVar(value="")
        folder_records: list[dict[str, object]] = []
        folder_by_iid: dict[str, dict[str, object]] = {}

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Buscar").pack(side="left")
        search_entry = ttk.Entry(toolbar, textvariable=search, width=34)
        search_entry.pack(side="left", padx=(8, 8))
        refresh_button = ttk.Button(toolbar, text="Atualizar")
        refresh_button.pack(side="left")
        new_folder_button = ttk.Button(toolbar, text="Nova pasta")
        new_folder_button.pack(side="left", padx=(8, 0))
        rename_folder_button = ttk.Button(toolbar, text="Renomear pasta")
        rename_folder_button.pack(side="left", padx=(8, 0))
        delete_folder_button = ttk.Button(toolbar, text="Excluir pasta")
        delete_folder_button.pack(side="left", padx=(8, 0))

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)

        folders_panel = ttk.Frame(body, style="Panel.TFrame", padding=12)
        folders_panel.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(folders_panel, text="Pastas", style="Panel.TLabel").pack(anchor="w", pady=(0, 8))
        folder_tree = ttk.Treeview(folders_panel, columns=("name", "total"), show="headings", selectmode="browse", height=18)
        folder_tree.heading("name", text="Nome")
        folder_tree.heading("total", text="Total")
        folder_tree.column("name", width=170, anchor="w")
        folder_tree.column("total", width=55, anchor="center", stretch=False)
        folder_tree.pack(fill="y", expand=True)
        ttk.Label(folders_panel, textvariable=empty_text, style="Muted.TLabel", wraplength=220).pack(anchor="w", pady=(10, 0))
        first_folder_button = ttk.Button(folders_panel, text="Criar primeira pasta")
        first_folder_button.pack(fill="x", pady=(10, 0))

        content = ttk.Frame(body)
        content.pack(side="left", fill="both", expand=True)
        content_header = ttk.Frame(content)
        content_header.pack(fill="x", pady=(0, 10))
        ttk.Label(content_header, textvariable=selected_title, font=("Segoe UI Semibold", 13)).pack(side="left")
        ttk.Label(content_header, textvariable=count_text, style="Muted.TLabel").pack(side="left", padx=(12, 0))
        content_actions = ttk.Frame(content)
        content_actions.pack(fill="x", pady=(0, 10))
        add_contact_button = ttk.Button(content_actions, text="Adicionar contato")
        add_contact_button.pack(side="left")
        edit_contact_button = ttk.Button(content_actions, text="Editar contato")
        edit_contact_button.pack(side="left", padx=(8, 0))
        import_folder_button = ttk.Button(content_actions, text="Importar para esta pasta")
        import_folder_button.pack(side="left", padx=(8, 0))

        notebook = ttk.Notebook(content)
        notebook.pack(fill="both", expand=True)
        contacts_tab = ttk.Frame(notebook)
        used_tab = ttk.Frame(notebook)
        optin_tab = ttk.Frame(notebook)
        blacklist_tab = ttk.Frame(notebook)
        notebook.add(contacts_tab, text="Contatos da pasta")
        notebook.add(used_tab, text="Ja enviados/usados")
        notebook.add(optin_tab, text="Com opt-in")
        notebook.add(blacklist_tab, text="Blacklist")

        def make_tree(parent: ttk.Frame, columns: tuple[str, ...], headings: dict[str, str], widths: dict[str, int]) -> ttk.Treeview:
            tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
            for column in columns:
                tree.heading(column, text=headings[column])
                tree.column(column, width=widths[column], anchor="w")
            tree.pack(side="left", fill="both", expand=True)
            scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
            scrollbar.pack(side="right", fill="y")
            tree.configure(yscrollcommand=scrollbar.set)
            return tree

        contact_columns = ("id", "name", "phone", "group", "opt_in", "source", "blacklisted")
        contact_headings = {
            "id": "ID",
            "name": "Cliente",
            "phone": "Telefone",
            "group": "Pasta",
            "opt_in": "Opt-in",
            "source": "Origem",
            "blacklisted": "Blacklist",
        }
        contact_widths = {"id": 55, "name": 220, "phone": 140, "group": 140, "opt_in": 70, "source": 130, "blacklisted": 90}
        contacts_tree = make_tree(contacts_tab, contact_columns, contact_headings, contact_widths)
        optin_tree = make_tree(optin_tab, contact_columns, contact_headings, contact_widths)
        blacklist_tree = make_tree(blacklist_tab, contact_columns, contact_headings, contact_widths)

        used_columns = ("phone", "name", "campaign", "status", "attempts", "last_sent")
        used_headings = {
            "phone": "Telefone",
            "name": "Cliente",
            "campaign": "Campanha",
            "status": "Status",
            "attempts": "Tentativas",
            "last_sent": "Ultimo uso",
        }
        used_widths = {"phone": 140, "name": 220, "campaign": 210, "status": 130, "attempts": 80, "last_sent": 150}
        used_tree = make_tree(used_tab, used_columns, used_headings, used_widths)

        editable_trees = {
            str(contacts_tab): contacts_tree,
            str(optin_tab): optin_tree,
            str(blacklist_tab): blacklist_tree,
        }

        def current_folder_name() -> str:
            return selected_folder.get().strip()

        def folder_total(folder_name: str) -> int:
            for item in folder_records:
                if str(item.get("name") or "") == folder_name:
                    return int(item.get("total_contacts") or 0)
            return 0

        def fill_contact_tree(tree: ttk.Treeview, items: list[dict[str, object]]) -> None:
            tree.delete(*tree.get_children())
            for item in items:
                tree.insert(
                    "",
                    "end",
                    values=(
                        item.get("id") or "",
                        item.get("name") or "",
                        item.get("phone") or "",
                        item.get("group_name") or "",
                        "Sim" if item.get("opt_in") else "Nao",
                        item.get("opt_in_source") or "",
                        "Sim" if item.get("blacklisted") else "Nao",
                    ),
                )

        def fill_used_tree(items: list[dict[str, object]]) -> None:
            used_tree.delete(*used_tree.get_children())
            for item in items:
                status = STATUS_LABELS.get(str(item.get("status") or ""), str(item.get("status") or ""))
                used_tree.insert(
                    "",
                    "end",
                    values=(
                        item.get("phone") or "",
                        item.get("recipient_name") or "",
                        item.get("campaign_name") or "",
                        status,
                        item.get("attempts") or 0,
                        item.get("last_sent_at") or "",
                    ),
                )

        def refresh_contacts() -> None:
            folder_name = current_folder_name()
            contacts_tree.delete(*contacts_tree.get_children())
            optin_tree.delete(*optin_tree.get_children())
            blacklist_tree.delete(*blacklist_tree.get_children())
            used_tree.delete(*used_tree.get_children())
            if not folder_name:
                selected_title.set("Selecione uma pasta")
                count_text.set("Nenhuma pasta selecionada.")
                return

            items = contacts.list_contacts(search.get(), folder_name)
            optin_items = [item for item in items if item.get("opt_in") and not item.get("blacklisted")]
            blacklist_items = [item for item in items if item.get("blacklisted")]
            used_items = contacts.list_used_contacts(folder_name=folder_name, search=search.get())
            fill_contact_tree(contacts_tree, items)
            fill_contact_tree(optin_tree, optin_items)
            fill_contact_tree(blacklist_tree, blacklist_items)
            fill_used_tree(used_items)
            selected_title.set(folder_name)
            count_text.set(
                f"Total: {folder_total(folder_name)} | Filtrados: {len(items)} | "
                f"Opt-in: {len(optin_items)} | Blacklist: {len(blacklist_items)} | Usados: {len(used_items)}"
            )
            self._set_status(f"Pasta '{folder_name}' atualizada.")

        def refresh_folders(select_name: str = "") -> None:
            folder_tree.delete(*folder_tree.get_children())
            folder_by_iid.clear()
            folder_records[:] = contacts.list_folders()
            for item in folder_records:
                iid = f"folder:{item.get('id')}"
                folder_by_iid[iid] = item
                folder_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(item.get("name") or "", item.get("total_contacts") or 0),
                )

            if not folder_records:
                selected_folder.set("")
                empty_text.set("Nenhuma pasta criada ainda. Crie a primeira pasta para organizar seus contatos.")
                if not first_folder_button.winfo_ismapped():
                    first_folder_button.pack(fill="x", pady=(10, 0))
                refresh_contacts()
                return

            empty_text.set("")
            if first_folder_button.winfo_ismapped():
                first_folder_button.pack_forget()
            target_name = select_name.strip() or current_folder_name() or str(folder_records[0].get("name") or "")
            target_iid = ""
            for iid, item in folder_by_iid.items():
                if str(item.get("name") or "") == target_name:
                    target_iid = iid
                    break
            if not target_iid:
                target_iid = next(iter(folder_by_iid))
            folder_tree.selection_set(target_iid)
            folder_tree.focus(target_iid)
            selected_folder.set(str(folder_by_iid[target_iid].get("name") or ""))
            refresh_contacts()

        def on_folder_select(_event: object) -> None:
            selection = folder_tree.selection()
            if not selection:
                return
            item = folder_by_iid.get(selection[0])
            if not item:
                return
            selected_folder.set(str(item.get("name") or ""))
            refresh_contacts()

        def create_folder() -> None:
            folder_name = simpledialog.askstring(APP_TITLE, "Nome da nova pasta:", parent=self)
            if not folder_name:
                return
            try:
                contacts.create_folder(folder_name)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders(folder_name.strip())

        def selected_folder_record() -> dict[str, object] | None:
            folder_name = current_folder_name()
            for item in folder_records:
                if str(item.get("name") or "") == folder_name:
                    return item
            return None

        def rename_folder() -> None:
            item = selected_folder_record()
            if not item:
                messagebox.showwarning(APP_TITLE, "Escolha uma pasta para renomear.")
                return
            current_name = str(item.get("name") or "")
            new_name = simpledialog.askstring(APP_TITLE, "Novo nome da pasta:", initialvalue=current_name, parent=self)
            if not new_name:
                return
            try:
                contacts.rename_folder(int(item["id"]), new_name)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders(new_name.strip())

        def delete_folder() -> None:
            item = selected_folder_record()
            if not item:
                messagebox.showwarning(APP_TITLE, "Escolha uma pasta para excluir.")
                return
            current_name = str(item.get("name") or "")
            if int(item.get("is_default") or 0):
                messagebox.showerror(APP_TITLE, "A pasta padrao nao pode ser excluida.")
                return
            if not messagebox.askyesno(APP_TITLE, f"Excluir a pasta '{current_name}'? Os contatos serao movidos para Importados."):
                return
            try:
                moved = contacts.delete_folder(int(item["id"]))
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders("Importados")
            self._set_status(f"Pasta excluida. {moved} contato(s) movido(s) para Importados.")

        def selected_contact_id() -> int:
            current_tab = notebook.select()
            tree = editable_trees.get(str(current_tab))
            if not tree or not tree.selection():
                return 0
            values = tree.item(tree.selection()[0], "values")
            try:
                return int(values[0])
            except (TypeError, ValueError, IndexError):
                return 0

        def open_contact_dialog(contact_id: int = 0) -> None:
            folder_name = current_folder_name()
            if not folder_name:
                messagebox.showwarning(APP_TITLE, "Crie ou selecione uma pasta antes de adicionar contatos.")
                return

            data = contacts.get_contact(contact_id) if contact_id else None
            dialog = tk.Toplevel(self)
            dialog.title("Contato")
            dialog.transient(self)
            dialog.grab_set()
            dialog.resizable(False, False)
            panel = ttk.Frame(dialog, padding=18)
            panel.pack(fill="both", expand=True)

            name = tk.StringVar(value=str(data.get("name") or "") if data else "")
            phone = tk.StringVar(value=str(data.get("phone") or "") if data else "")
            email = tk.StringVar(value=str(data.get("email") or "") if data else "")
            group_name = tk.StringVar(value=str(data.get("group_name") or folder_name) if data else folder_name)
            notes = tk.StringVar(value=str(data.get("notes") or "") if data else "")
            opt_in_source = tk.StringVar(value=str(data.get("opt_in_source") or "manual") if data else "manual")
            opt_in_category = tk.StringVar(value=str(data.get("opt_in_category") or "marketing") if data else "marketing")
            opt_in_at = tk.StringVar(value=str(data.get("opt_in_at") or "") if data else "")
            consent_notes = tk.StringVar(value=str(data.get("consent_notes") or "") if data else "")
            opt_in = tk.BooleanVar(value=bool(data.get("opt_in")) if data else True)
            blacklisted = tk.BooleanVar(value=bool(data.get("blacklisted")) if data else False)

            fields = [
                ("Nome do cliente", name),
                ("Telefone com DDD", phone),
                ("E-mail", email),
                ("Origem do opt-in", opt_in_source),
                ("Categoria do opt-in", opt_in_category),
                ("Data do opt-in", opt_in_at),
                ("Comprovante/observacao", consent_notes),
                ("Observacoes internas", notes),
            ]
            for label, variable in fields:
                self._entry(panel, label, variable).pack(fill="x", pady=(0, 10))

            folder_row = ttk.Frame(panel)
            folder_row.pack(fill="x", pady=(0, 10))
            ttk.Label(folder_row, text="Pasta").pack(anchor="w", pady=(0, 4))
            ttk.Combobox(folder_row, textvariable=group_name, values=contacts.list_groups(), state="readonly").pack(fill="x")
            ttk.Checkbutton(panel, text="Contato tem opt-in", variable=opt_in).pack(anchor="w", pady=(0, 8))
            ttk.Checkbutton(panel, text="Contato esta em blacklist", variable=blacklisted).pack(anchor="w", pady=(0, 12))

            buttons = ttk.Frame(panel)
            buttons.pack(fill="x")

            def save_contact() -> None:
                try:
                    if contact_id:
                        contacts.update_contact(
                            contact_id,
                            name=name.get(),
                            phone=phone.get(),
                            email=email.get(),
                            group_name=group_name.get(),
                            opt_in=opt_in.get(),
                            opt_in_source=opt_in_source.get(),
                            opt_in_category=opt_in_category.get(),
                            opt_in_at=opt_in_at.get(),
                            consent_notes=consent_notes.get(),
                            notes=notes.get(),
                            blacklisted=blacklisted.get(),
                        )
                    else:
                        contacts.create_contact(
                            name.get(),
                            phone.get(),
                            email.get(),
                            group_name.get(),
                            opt_in=int(opt_in.get()),
                            opt_in_source=opt_in_source.get(),
                            opt_in_category=opt_in_category.get(),
                            opt_in_at=opt_in_at.get(),
                            consent_notes=consent_notes.get(),
                            notes=notes.get(),
                            blacklisted=blacklisted.get(),
                        )
                except contacts.ContactError as exc:
                    messagebox.showerror(APP_TITLE, str(exc))
                    return
                dialog.destroy()
                refresh_folders(group_name.get())
                self._set_status("Contato salvo.")

            def delete_contact() -> None:
                if not contact_id:
                    return
                if not messagebox.askyesno(APP_TITLE, "Excluir este contato?"):
                    return
                contacts.delete_contact(contact_id)
                dialog.destroy()
                refresh_folders(group_name.get())
                self._set_status("Contato excluido.")

            ttk.Button(buttons, text="Salvar", style="Accent.TButton", command=save_contact).pack(side="left")
            if contact_id:
                ttk.Button(buttons, text="Excluir", command=delete_contact).pack(side="left", padx=(8, 0))
            ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="right")

        def edit_selected_contact() -> None:
            contact_id = selected_contact_id()
            if not contact_id:
                messagebox.showwarning(APP_TITLE, "Selecione um contato nas abas de contatos, opt-in ou blacklist.")
                return
            open_contact_dialog(contact_id)

        def import_to_current_folder() -> None:
            folder_name = current_folder_name()
            if not folder_name:
                messagebox.showwarning(APP_TITLE, "Selecione uma pasta antes de importar.")
                return
            self.show_import_contacts(folder_name)

        folder_tree.bind("<<TreeviewSelect>>", on_folder_select)
        search_entry.bind("<Return>", lambda _event: refresh_contacts())
        notebook.bind("<<NotebookTabChanged>>", lambda _event: refresh_contacts())
        for tree in (contacts_tree, optin_tree, blacklist_tree):
            tree.bind("<Double-1>", lambda _event: edit_selected_contact())

        refresh_button.configure(command=refresh_contacts)
        new_folder_button.configure(command=create_folder)
        first_folder_button.configure(command=create_folder)
        rename_folder_button.configure(command=rename_folder)
        delete_folder_button.configure(command=delete_folder)
        add_contact_button.configure(command=lambda: open_contact_dialog())
        edit_contact_button.configure(command=edit_selected_contact)
        import_folder_button.configure(command=import_to_current_folder)

        refresh_folders()

    def show_import_contacts(self, folder_name: str = "") -> None:
        frame = self._screen("Importar clientes")
        panel = ttk.Frame(frame, style="Panel.TFrame", padding=18)
        panel.pack(fill="x")
        path = tk.StringVar()
        result = tk.StringVar(
            value="Escolha uma planilha CSV ou Excel com pelo menos nome e telefone. Se tiver autorização, informe também origem e data."
        )

        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 12))
        ttk.Entry(row, textvariable=path).pack(side="left", fill="x", expand=True)
        ttk.Button(
            row,
            text="Escolher planilha",
            command=lambda: path.set(filedialog.askopenfilename(filetypes=[("Planilhas", "*.csv *.txt *.xlsx"), ("Todos", "*.*")])),
        ).pack(side="left", padx=(8, 0))

        destination_folder = folder_name.strip() or DEFAULT_CONTACT_FOLDER
        try:
            contacts.create_folder(destination_folder)
        except contacts.ContactError:
            destination_folder = DEFAULT_CONTACT_FOLDER
        folder = tk.StringVar(value=destination_folder)
        folder_row = ttk.Frame(panel, style="Panel.TFrame")
        folder_row.pack(fill="x", pady=(0, 12))
        ttk.Label(folder_row, text="Importar para pasta", style="Panel.TLabel").pack(side="left")

        def import_folder_values() -> list[str]:
            values = contacts.list_groups()
            if DEFAULT_CONTACT_FOLDER not in values:
                values.insert(0, DEFAULT_CONTACT_FOLDER)
            return values

        folder_combo = ttk.Combobox(folder_row, textvariable=folder, values=import_folder_values(), state="readonly")
        folder_combo.pack(side="left", fill="x", expand=True, padx=(8, 8))

        def create_import_folder() -> None:
            folder_name = simpledialog.askstring(APP_TITLE, "Nome da nova pasta:", parent=self)
            if not folder_name:
                return
            try:
                contacts.create_folder(folder_name)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            folder_combo.configure(values=import_folder_values())
            folder.set(folder_name.strip())

        ttk.Button(folder_row, text="Nova pasta", command=create_import_folder).pack(side="left")

        ttk.Label(panel, textvariable=result, style="Panel.TLabel", wraplength=760).pack(anchor="w", pady=(0, 12))

        def do_import() -> None:
            selected_folder = folder.get().strip() or DEFAULT_CONTACT_FOLDER
            try:
                contacts.create_folder(selected_folder)
                summary = contacts.import_contacts(path.get(), folder_name=selected_folder)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            errors = "\n".join(summary.errors[:5])
            text = (
                f"Pasta de destino: {selected_folder}\n"
                f"Contatos importados: {summary.imported} | Atualizados: {summary.updated} | "
                f"Duplicados: {summary.duplicates} | Invalidos/ignorados: {summary.skipped}"
            )
            if errors:
                text += f"\nO que revisar primeiro:\n{errors}"
            result.set(text)
            self._set_status(f"Importacao concluida em '{selected_folder}'.")

        ttk.Button(panel, text="Importar clientes", style="Accent.TButton", command=do_import).pack(anchor="w")

    def show_create_campaign(self) -> None:
        return self._show_create_campaign_by_folder()

        frame = self._screen("Nova campanha")
        form = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        form.pack(side="left", fill="both", expand=True)
        name = tk.StringVar()
        template_name = tk.StringVar(value=whatsapp.load_config().default_template)
        template_language = tk.StringVar(value=whatsapp.load_config().default_language)
        message_categories = {
            "Marketing": "marketing",
            "Aviso ou serviço": "utility",
            "Código de acesso": "authentication",
            "Atendimento": "service",
        }
        message_category = tk.StringVar(value="Marketing")
        media_path = tk.StringVar()

        self._entry(form, "Nome para identificar esta campanha", name).pack(fill="x", pady=(0, 10))
        category_frame = ttk.Frame(form, style="Panel.TFrame")
        category_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(category_frame, text="Tipo de mensagem", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(
            category_frame,
            textvariable=message_category,
            values=tuple(message_categories.keys()),
            state="readonly",
        ).pack(fill="x")
        template_row = ttk.Frame(form, style="Panel.TFrame")
        template_row.pack(fill="x", pady=(0, 10))
        self._entry(template_row, "Nome do modelo aprovado na Meta", template_name).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(template_row, "Idioma", template_language).pack(side="left", fill="x")

        ttk.Label(form, text="Mensagem principal", style="Panel.TLabel").pack(anchor="w")
        message = tk.Text(form, height=8, wrap="word")
        message.pack(fill="both", expand=True, pady=(4, 10))

        ttk.Label(form, text="Outras versões da mensagem", style="Panel.TLabel").pack(anchor="w")
        message_variants = tk.Text(form, height=5, wrap="word")
        message_variants.pack(fill="both", expand=True, pady=(4, 10))

        media_row = ttk.Frame(form, style="Panel.TFrame")
        media_row.pack(fill="x", pady=(0, 12))
        ttk.Entry(media_row, textvariable=media_path).pack(side="left", fill="x", expand=True)
        ttk.Button(
            media_row,
            text="Imagem, arquivo ou link",
            command=lambda: media_path.set(filedialog.askopenfilename() or media_path.get()),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(form, text="Outras imagens, arquivos ou links", style="Panel.TLabel").pack(anchor="w")
        media_variants = tk.Text(form, height=3, wrap="word")
        media_variants.pack(fill="x", pady=(4, 10))

        contact_panel = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        contact_panel.pack(side="right", fill="both", expand=True, padx=(16, 0))
        ttk.Label(contact_panel, text="Clientes que autorizaram mensagens", style="Panel.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        filters = ttk.Frame(contact_panel, style="Panel.TFrame")
        filters.pack(fill="x", pady=(8, 8))
        group_filter = tk.StringVar()
        groups = [""] + contacts.list_groups()
        group_combo = ttk.Combobox(filters, textvariable=group_filter, values=groups, state="readonly")
        group_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(filters, text="Filtrar", command=lambda: refresh_contacts()).pack(side="left", padx=(8, 0))

        tree = ttk.Treeview(contact_panel, columns=("id", "name", "phone", "group"), show="headings", selectmode="extended")
        for column, heading, width in [
            ("id", "ID", 50),
            ("name", "Cliente", 190),
            ("phone", "Telefone", 130),
            ("group", "Grupo", 120),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width)
        tree.pack(fill="both", expand=True)

        def refresh_contacts() -> None:
            tree.delete(*tree.get_children())
            for item in contacts.list_contacts(group_name=group_filter.get()):
                if item["opt_in"] and not item["blacklisted"]:
                    tree.insert("", "end", values=(item["id"], item["name"], item["phone"], item["group_name"]))

        def select_all() -> None:
            tree.selection_set(tree.get_children())

        def create() -> None:
            selected = [int(tree.item(item, "values")[0]) for item in tree.selection()]
            try:
                campaign_id = campaigns.create_campaign(
                    name=name.get(),
                    message=message.get("1.0", "end").strip(),
                    contact_ids=selected,
                    media_path=media_path.get(),
                    template_name=template_name.get(),
                    template_language=template_language.get(),
                    message_category=message_categories.get(message_category.get(), "marketing"),
                    message_variants=parse_variants(message_variants.get("1.0", "end")),
                    media_variants=parse_variants(media_variants.get("1.0", "end")),
                )
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            messagebox.showinfo(APP_TITLE, "Campanha salva. Agora você pode agendar ou enviar.")
            self.show_schedule()

        actions = ttk.Frame(contact_panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Marcar todos", command=select_all).pack(side="left")
        ttk.Button(actions, text="Salvar campanha", style="Accent.TButton", command=create).pack(side="right")
        refresh_contacts()

    def _show_create_campaign_by_folder(self) -> None:
        frame = self._screen("Nova campanha")
        form = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        form.pack(side="left", fill="both", expand=True)
        name = tk.StringVar()
        template_name = tk.StringVar(value=whatsapp.load_config().default_template)
        template_language = tk.StringVar(value=whatsapp.load_config().default_language)
        message_categories = {
            "Marketing": "marketing",
            "Aviso ou servico": "utility",
            "Codigo de acesso": "authentication",
            "Atendimento": "service",
        }
        message_category = tk.StringVar(value="Marketing")
        media_path = tk.StringVar()
        start_mode = tk.StringVar(value="now")
        start_at = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        delay_min = tk.StringVar(value=str(campaigns.DEFAULT_DELAY_MIN_SECONDS))
        delay_max = tk.StringVar(value=str(campaigns.DEFAULT_DELAY_MAX_SECONDS))
        delay_info = tk.StringVar(value="")
        delay_customized = tk.BooleanVar(value=False)

        self._entry(form, "Nome para identificar esta campanha", name).pack(fill="x", pady=(0, 10))
        category_frame = ttk.Frame(form, style="Panel.TFrame")
        category_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(category_frame, text="Tipo de mensagem", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(
            category_frame,
            textvariable=message_category,
            values=tuple(message_categories.keys()),
            state="readonly",
        ).pack(fill="x")
        template_row = ttk.Frame(form, style="Panel.TFrame")
        template_row.pack(fill="x", pady=(0, 10))
        self._entry(template_row, "Nome do modelo aprovado na Meta", template_name).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(template_row, "Idioma", template_language).pack(side="left", fill="x")

        ttk.Label(form, text="Mensagem principal", style="Panel.TLabel").pack(anchor="w")
        message = tk.Text(form, height=8, wrap="word")
        message.pack(fill="both", expand=True, pady=(4, 10))

        ttk.Label(form, text="Outras versoes da mensagem", style="Panel.TLabel").pack(anchor="w")
        message_variants = tk.Text(form, height=5, wrap="word")
        message_variants.pack(fill="both", expand=True, pady=(4, 10))

        media_row = ttk.Frame(form, style="Panel.TFrame")
        media_row.pack(fill="x", pady=(0, 12))
        ttk.Entry(media_row, textvariable=media_path).pack(side="left", fill="x", expand=True)
        ttk.Button(
            media_row,
            text="Imagem, arquivo ou link",
            command=lambda: media_path.set(filedialog.askopenfilename() or media_path.get()),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(form, text="Outras imagens, arquivos ou links", style="Panel.TLabel").pack(anchor="w")
        media_variants = tk.Text(form, height=3, wrap="word")
        media_variants.pack(fill="x", pady=(4, 10))

        send_mode = ttk.Frame(form, style="Panel.TFrame")
        send_mode.pack(fill="x", pady=(0, 12))
        ttk.Label(send_mode, text="Quando enviar", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Radiobutton(send_mode, text="Iniciar campanha agora", variable=start_mode, value="now").pack(anchor="w")
        schedule_row = ttk.Frame(send_mode, style="Panel.TFrame")
        schedule_row.pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(schedule_row, text="Agendar para", variable=start_mode, value="schedule").pack(side="left")
        ttk.Entry(schedule_row, textvariable=start_at, width=22).pack(side="left", padx=(8, 0))

        delay_panel = ttk.Frame(form, style="Panel.TFrame")
        delay_panel.pack(fill="x", pady=(0, 12))
        ttk.Label(delay_panel, text="Intervalo entre mensagens", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        delay_row = ttk.Frame(delay_panel, style="Panel.TFrame")
        delay_row.pack(fill="x")
        self._entry(delay_row, "Mínimo (segundos)", delay_min).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(delay_row, "Máximo (segundos)", delay_max).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(delay_row, text="Usar recomendacao", command=lambda: apply_delay_recommendation()).pack(side="left", pady=(20, 0))
        ttk.Label(delay_panel, textvariable=delay_info, style="Muted.TLabel", wraplength=640).pack(anchor="w", pady=(6, 0))

        folder_panel = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        folder_panel.pack(side="right", fill="y", padx=(16, 0))
        ttk.Label(folder_panel, text="Pasta de contatos", style="Panel.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        selected_folder = tk.StringVar()
        folder_combo = ttk.Combobox(folder_panel, textvariable=selected_folder, values=contacts.list_groups(), state="readonly", width=34)
        folder_combo.pack(fill="x", pady=(8, 10))

        folder_stats = tk.StringVar(value="Escolha uma pasta para ver os contatos.")
        ttk.Label(folder_panel, textvariable=folder_stats, style="Panel.TLabel", wraplength=320, justify="left").pack(anchor="w", pady=(0, 12))

        folder_actions = ttk.Frame(folder_panel, style="Panel.TFrame")
        folder_actions.pack(fill="x", pady=(0, 12))
        new_folder_button = ttk.Button(folder_actions, text="Nova pasta")
        new_folder_button.pack(side="left")
        import_button = ttk.Button(folder_actions, text="Importar contatos")
        import_button.pack(side="left", padx=(8, 0))

        save_button = ttk.Button(folder_panel, text="Criar campanha", style="Accent.TButton")
        save_button.pack(fill="x", pady=(10, 0))

        def folder_values() -> list[str]:
            values = contacts.list_groups()
            if DEFAULT_CONTACT_FOLDER not in values:
                values.insert(0, DEFAULT_CONTACT_FOLDER)
            return values

        def folder_contacts(folder_name: str) -> list[dict[str, object]]:
            return contacts.list_contacts(group_name=folder_name)

        def eligible_contacts(folder_name: str) -> list[dict[str, object]]:
            return [
                item
                for item in folder_contacts(folder_name)
                if item.get("opt_in") and not item.get("blacklisted")
            ]

        def update_delay_info() -> None:
            try:
                delay_min_value, delay_max_value = campaigns.normalize_campaign_delay(delay_min.get(), delay_max.get())
                level, message = campaigns.delay_recommendation_message(delay_min_value, delay_max_value)
                delay_info.set(f"{message} Configurado: {delay_min_value}-{delay_max_value}s.")
            except campaigns.CampaignError as exc:
                delay_info.set(str(exc))

        def apply_delay_recommendation() -> None:
            folder_name = selected_folder.get().strip()
            total = len(eligible_contacts(folder_name)) if folder_name else 0
            recommended_min, recommended_max = campaigns.recommended_delay_for_contacts(total)
            delay_min.set(str(recommended_min))
            delay_max.set(str(recommended_max))
            delay_customized.set(False)
            update_delay_info()

        def refresh_folder_stats() -> None:
            folder_name = selected_folder.get().strip()
            if not folder_name:
                folder_stats.set("Escolha uma pasta para ver os contatos.")
                update_delay_info()
                return
            items = folder_contacts(folder_name)
            opt_in_count = sum(1 for item in items if item.get("opt_in") and not item.get("blacklisted"))
            blacklist_count = sum(1 for item in items if item.get("blacklisted"))
            used_count = len(contacts.list_used_contacts(folder_name=folder_name))
            folder_stats.set(
                f"Total de contatos: {len(items)}\n"
                f"Com opt-in: {opt_in_count}\n"
                f"Ja usados/enviados: {used_count}\n"
                f"Blacklist: {blacklist_count}"
            )
            if not delay_customized.get():
                apply_delay_recommendation()
            else:
                update_delay_info()

        def refresh_folders(select_name: str = "") -> None:
            values = folder_values()
            folder_combo.configure(values=values)
            if select_name.strip():
                selected_folder.set(select_name.strip())
            elif not selected_folder.get().strip() and values:
                selected_folder.set(values[0])
            refresh_folder_stats()

        def create_folder() -> None:
            folder_name = simpledialog.askstring(APP_TITLE, "Nome da nova pasta:", parent=self)
            if not folder_name:
                return
            try:
                contacts.create_folder(folder_name)
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh_folders(folder_name)

        def open_import() -> None:
            self.show_import_contacts(selected_folder.get().strip() or DEFAULT_CONTACT_FOLDER)

        def create() -> None:
            folder_name = selected_folder.get().strip()
            if not folder_name:
                messagebox.showerror(APP_TITLE, "Escolha uma pasta de contatos.")
                return
            items = folder_contacts(folder_name)
            if not items:
                messagebox.showerror(APP_TITLE, "A pasta selecionada esta vazia.")
                return
            selected = [int(item["id"]) for item in eligible_contacts(folder_name)]
            if not selected:
                messagebox.showerror(APP_TITLE, "A pasta selecionada nao tem contatos com opt-in liberados.")
                return
            try:
                delay_min_value, delay_max_value = campaigns.normalize_campaign_delay(delay_min.get(), delay_max.get(), len(selected))
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            delay_level, delay_message = campaigns.delay_recommendation_message(delay_min_value, delay_max_value)
            if delay_level == "alto" and not messagebox.askyesno(
                APP_TITLE,
                f"{delay_message}\n\nDeseja criar a campanha mesmo assim?",
            ):
                return
            scheduled_value = ""
            if start_mode.get() == "schedule":
                try:
                    scheduled_value = parse_datetime(start_at.get())
                except campaigns.CampaignError as exc:
                    messagebox.showerror(APP_TITLE, str(exc))
                    return
            try:
                campaign_id = campaigns.create_campaign(
                    name=name.get(),
                    message=message.get("1.0", "end").strip(),
                    contact_ids=selected,
                    media_path=media_path.get(),
                    template_name=template_name.get(),
                    template_language=template_language.get(),
                    message_category=message_categories.get(message_category.get(), "marketing"),
                    message_variants=parse_variants(message_variants.get("1.0", "end")),
                    media_variants=parse_variants(media_variants.get("1.0", "end")),
                    folder_name=folder_name,
                    scheduled_at=scheduled_value or None,
                    delay_min_seconds=delay_min_value,
                    delay_max_seconds=delay_max_value,
                )
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            if start_mode.get() == "now":
                self._set_status(f"Campanha #{campaign_id} criada. Iniciando envio agora.")
                self._start_campaign_thread(campaign_id, source="ui_create_now")
                messagebox.showinfo(APP_TITLE, f"Campanha criada para a pasta '{folder_name}' e envio iniciado.")
            else:
                self._set_status(f"Campanha #{campaign_id} agendada para {scheduled_value}.")
                messagebox.showinfo(APP_TITLE, f"Campanha criada para a pasta '{folder_name}' e agendada.")
            self.show_schedule()

        def on_delay_edit(*_args: object) -> None:
            delay_customized.set(True)
            update_delay_info()

        delay_min.trace_add("write", on_delay_edit)
        delay_max.trace_add("write", on_delay_edit)
        folder_combo.bind("<<ComboboxSelected>>", lambda _event: refresh_folder_stats())
        new_folder_button.configure(command=create_folder)
        import_button.configure(command=open_import)
        save_button.configure(command=create)
        refresh_folders()

    def show_schedule(self) -> None:
        return self._show_campaigns_center()

        frame = self._screen("Agenda de envios")
        tree = self._campaign_tree(frame)
        tree.pack(fill="both", expand=True)

        controls = ttk.Frame(frame, style="Panel.TFrame", padding=14)
        controls.pack(fill="x", pady=(12, 0))
        scheduled_at = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        ttk.Label(controls, text="Quando enviar").pack(side="left")
        ttk.Entry(controls, textvariable=scheduled_at, width=22).pack(side="left", padx=(8, 10))
        progress = tk.StringVar(value="Escolha uma campanha.")
        ttk.Label(controls, textvariable=progress).pack(side="left", padx=(8, 0))

        def selected_campaign_id() -> int | None:
            if not tree.selection():
                messagebox.showwarning(APP_TITLE, "Escolha uma campanha primeiro.")
                return None
            return int(tree.item(tree.selection()[0], "values")[0])

        def refresh() -> None:
            self._fill_campaign_tree(tree)

        def schedule() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            try:
                campaigns.schedule_campaign(campaign_id, parse_datetime(scheduled_at.get()))
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh()
            self._set_status("Envio agendado.")

        def send_now() -> None:
            campaign_id = selected_campaign_id()
            if campaign_id:
                self._start_campaign_thread(campaign_id, progress, source="ui_manual")

        def pause() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            event = self.running_events.get(campaign_id)
            if event:
                event.set()
            try:
                campaigns.pause_campaign(campaign_id)
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh()

        def cancel() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            if messagebox.askyesno(APP_TITLE, "Cancelar esta campanha? Ela não será enviada."):
                campaigns.cancel_campaign(campaign_id)
                refresh()

        ttk.Button(controls, text="Agendar", command=schedule).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Enviar agora", style="Accent.TButton", command=send_now).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Pausar envio", command=pause).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Cancelar envio", command=cancel).pack(side="left", padx=(8, 0))
        refresh()

    def _show_campaigns_center(self) -> None:
        frame = self._screen("Agenda de envios")
        campaign_by_id: dict[int, dict[str, object]] = {}
        name_var = tk.StringVar()
        scheduled_at = tk.StringVar()
        delay_min_var = tk.StringVar()
        delay_max_var = tk.StringVar()
        delay_details = tk.StringVar()
        progress = tk.StringVar(value="Escolha uma campanha.")
        details = tk.StringVar(value="Nenhuma campanha selecionada.")
        empty_text = tk.StringVar()

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 8))
        refresh_button = ttk.Button(top, text="Atualizar")
        refresh_button.pack(side="left")
        open_button = ttk.Button(top, text="Abrir campanha")
        open_button.pack(side="left", padx=(8, 0))
        send_button = ttk.Button(top, text="Iniciar agora", style="Accent.TButton")
        send_button.pack(side="left", padx=(8, 0))
        schedule_button = ttk.Button(top, text="Agendar")
        schedule_button.pack(side="left", padx=(8, 0))
        pause_button = ttk.Button(top, text="Pausar")
        pause_button.pack(side="left", padx=(8, 0))
        continue_button = ttk.Button(top, text="Continuar")
        continue_button.pack(side="left", padx=(8, 0))
        cancel_button = ttk.Button(top, text="Cancelar")
        cancel_button.pack(side="left", padx=(8, 0))
        history_button = ttk.Button(top, text="Ver historico")
        history_button.pack(side="left", padx=(8, 0))

        ttk.Label(frame, textvariable=empty_text, style="Muted.TLabel").pack(anchor="w", pady=(0, 6))

        columns = ("name", "status", "risk", "scheduled", "folder", "delay", "total", "sent", "failed", "progress", "updated")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=13)
        headings = {
            "name": "Nome da campanha",
            "status": "Status",
            "risk": "Risco",
            "scheduled": "Agendamento",
            "folder": "Pasta",
            "delay": "Delay",
            "total": "Total",
            "sent": "Enviados",
            "failed": "Falhas",
            "progress": "Progresso",
            "updated": "Ultima atualizacao",
        }
        widths = {
            "name": 220,
            "status": 110,
            "risk": 70,
            "scheduled": 145,
            "folder": 145,
            "delay": 90,
            "total": 60,
            "sent": 70,
            "failed": 60,
            "progress": 110,
            "updated": 145,
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="w")
        tree.pack(fill="both", expand=True)

        edit_panel = ttk.Frame(frame, style="Panel.TFrame", padding=14)
        edit_panel.pack(fill="x", pady=(12, 0))
        ttk.Label(edit_panel, textvariable=details, style="Panel.TLabel", wraplength=980, justify="left").pack(anchor="w", pady=(0, 10))
        edit_row = ttk.Frame(edit_panel, style="Panel.TFrame")
        edit_row.pack(fill="x")
        self._entry(edit_row, "Nome da campanha", name_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(edit_row, "Agendamento", scheduled_at).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(edit_row, "Delay min", delay_min_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(edit_row, "Delay max", delay_max_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        save_button = ttk.Button(edit_row, text="Salvar alteracoes")
        save_button.pack(side="left", padx=(0, 8), pady=(20, 0))
        ttk.Label(edit_panel, textvariable=delay_details, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Label(edit_panel, textvariable=progress, style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

        def selected_campaign_id(show_warning: bool = True) -> int | None:
            selection = tree.selection()
            if not selection:
                if show_warning:
                    messagebox.showwarning(APP_TITLE, "Escolha uma campanha primeiro.")
                return None
            try:
                return int(selection[0])
            except ValueError:
                return None

        def selected_campaign() -> dict[str, object] | None:
            campaign_id = selected_campaign_id(show_warning=False)
            return campaign_by_id.get(campaign_id or 0)

        def progress_label(item: dict[str, object]) -> str:
            total = int(item.get("total_contacts") or 0)
            processed = int(item.get("processed_contacts") or 0)
            percent = int(item.get("progress_percent") or 0)
            return f"{percent}% ({processed}/{total})" if total else "0% (0/0)"

        def folder_label(item: dict[str, object]) -> str:
            return str(item.get("folder_name") or "Campanha antiga")

        def delay_label(item: dict[str, object]) -> str:
            minimum = int(item.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS)
            maximum = int(item.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS)
            return f"{minimum}-{maximum}s"

        def on_select(_event: object | None = None) -> None:
            item = selected_campaign()
            if not item:
                name_var.set("")
                scheduled_at.set("")
                delay_min_var.set("")
                delay_max_var.set("")
                delay_details.set("")
                details.set("Nenhuma campanha selecionada.")
                progress.set("Escolha uma campanha.")
                return
            name_var.set(str(item.get("name") or ""))
            scheduled_at.set(str(item.get("scheduled_at") or ""))
            delay_min_var.set(str(item.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS))
            delay_max_var.set(str(item.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS))
            level, delay_message = campaigns.delay_recommendation_message(delay_min_var.get(), delay_max_var.get())
            delay_details.set(f"{delay_message} Configurado: {delay_label(item)}.")
            total = int(item.get("total_contacts") or 0)
            sent = int(item.get("sent_contacts") or 0)
            failed = int(item.get("failed_contacts") or 0)
            details.set(
                f"Status: {friendly_status(item.get('status'))} | "
                f"Pasta: {folder_label(item)} | "
                f"Delay: {delay_label(item)} | "
                f"Contatos: {total} | Enviados: {sent} | Falhas: {failed} | "
                f"Atualizada em: {item.get('updated_at') or ''}"
            )
            progress.set(progress_label(item))

        def refresh(select_id: int | None = None) -> None:
            current = select_id or selected_campaign_id(show_warning=False)
            tree.delete(*tree.get_children())
            campaign_by_id.clear()
            items = campaigns.list_campaigns()
            empty_text.set("" if items else "Nenhuma campanha criada ainda. Crie uma campanha em Nova campanha para comecar.")
            for item in items:
                campaign_id = int(item["id"])
                try:
                    risk = compliance.refresh_campaign_risk(campaign_id)
                    item["risk_score"] = risk["score"]
                except ValueError:
                    item["risk_score"] = item.get("risk_score") or 0
                campaign_by_id[campaign_id] = item
                tree.insert(
                    "",
                    "end",
                    iid=str(campaign_id),
                    values=(
                        item.get("name") or "",
                        friendly_status(item.get("status")),
                        f"{item.get('risk_score') or 0}%",
                        item.get("scheduled_at") or "",
                        folder_label(item),
                        delay_label(item),
                        item.get("total_contacts") or 0,
                        item.get("sent_contacts") or 0,
                        item.get("failed_contacts") or 0,
                        progress_label(item),
                        item.get("updated_at") or "",
                    ),
                )
            if items:
                target = str(current) if current in campaign_by_id else str(int(items[0]["id"]))
                tree.selection_set(target)
                tree.focus(target)
            on_select()

        def schedule_selected() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            try:
                campaigns.schedule_campaign(campaign_id, parse_datetime(scheduled_at.get()))
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh(campaign_id)
            self._set_status("Envio agendado.")

        def send_now() -> None:
            campaign_id = selected_campaign_id()
            if campaign_id:
                self._start_campaign_thread(campaign_id, progress, source="ui_manual")

        def continue_campaign() -> None:
            campaign_id = selected_campaign_id()
            if campaign_id:
                self._start_campaign_thread(campaign_id, progress, source="ui_continue", allow_resume=True)

        def pause() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            event = self.running_events.get(campaign_id)
            if event:
                event.set()
            try:
                campaigns.pause_campaign(campaign_id)
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh(campaign_id)
            self._set_status("Campanha pausada.")

        def cancel() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            if not messagebox.askyesno(APP_TITLE, "Cancelar esta campanha? Ela nao sera enviada."):
                return
            campaigns.cancel_campaign(campaign_id)
            refresh(campaign_id)
            self._set_status("Campanha cancelada.")

        def save_changes() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            try:
                scheduled_value = parse_datetime(scheduled_at.get()) if scheduled_at.get().strip() else ""
                delay_min_value, delay_max_value = campaigns.normalize_campaign_delay(delay_min_var.get(), delay_max_var.get())
                delay_level, delay_message = campaigns.delay_recommendation_message(delay_min_value, delay_max_value)
                if delay_level == "alto" and not messagebox.askyesno(
                    APP_TITLE,
                    f"{delay_message}\n\nDeseja salvar esse delay mesmo assim?",
                ):
                    return
                campaigns.update_campaign_details(
                    campaign_id,
                    name_var.get(),
                    scheduled_value,
                    delay_min_seconds=delay_min_value,
                    delay_max_seconds=delay_max_value,
                )
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh(campaign_id)
            self._set_status("Campanha atualizada.")

        def open_campaign() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            campaign = campaigns.get_campaign(campaign_id)
            if not campaign:
                messagebox.showerror(APP_TITLE, "Campanha nao encontrada.")
                return
            dialog = tk.Toplevel(self)
            dialog.title(f"Campanha #{campaign_id}")
            dialog.geometry("860x520")
            panel = ttk.Frame(dialog, padding=16)
            panel.pack(fill="both", expand=True)
            summary = (
                f"{campaign.get('name') or ''}\n"
                f"Status: {friendly_status(campaign.get('status'))} | "
                f"Pasta: {campaign.get('folder_name') or 'Campanha antiga'} | "
                f"Agendamento: {campaign.get('scheduled_at') or ''}\n"
                f"Template: {campaign.get('template_name') or ''} | Idioma: {campaign.get('template_language') or ''} | "
                f"Delay: {campaign.get('delay_min_seconds') or campaigns.DEFAULT_DELAY_MIN_SECONDS}-{campaign.get('delay_max_seconds') or campaigns.DEFAULT_DELAY_MAX_SECONDS}s"
            )
            ttk.Label(panel, text=summary, style="Panel.TLabel", justify="left", wraplength=820).pack(anchor="w", pady=(0, 10))
            dialog_delay_min = tk.StringVar(value=str(campaign.get("delay_min_seconds") or campaigns.DEFAULT_DELAY_MIN_SECONDS))
            dialog_delay_max = tk.StringVar(value=str(campaign.get("delay_max_seconds") or campaigns.DEFAULT_DELAY_MAX_SECONDS))
            delay_row = ttk.Frame(panel)
            delay_row.pack(fill="x", pady=(0, 10))
            self._entry(delay_row, "Delay mínimo", dialog_delay_min).pack(side="left", fill="x", expand=True, padx=(0, 8))
            self._entry(delay_row, "Delay máximo", dialog_delay_max).pack(side="left", fill="x", expand=True, padx=(0, 8))

            def save_dialog_delay() -> None:
                try:
                    delay_min_value, delay_max_value = campaigns.normalize_campaign_delay(dialog_delay_min.get(), dialog_delay_max.get())
                    level, message = campaigns.delay_recommendation_message(delay_min_value, delay_max_value)
                    if level == "alto" and not messagebox.askyesno(APP_TITLE, f"{message}\n\nDeseja salvar mesmo assim?"):
                        return
                    campaigns.update_campaign_details(
                        campaign_id,
                        str(campaign.get("name") or ""),
                        str(campaign.get("scheduled_at") or ""),
                        delay_min_seconds=delay_min_value,
                        delay_max_seconds=delay_max_value,
                    )
                except campaigns.CampaignError as exc:
                    messagebox.showerror(APP_TITLE, str(exc))
                    return
                self._set_status("Delay da campanha atualizado.")
                dialog.destroy()
                refresh(campaign_id)

            ttk.Button(delay_row, text="Salvar delay", command=save_dialog_delay).pack(side="left", pady=(20, 0))
            message_box = tk.Text(panel, height=5, wrap="word")
            message_box.pack(fill="x", pady=(0, 10))
            message_box.insert("1.0", str(campaign.get("message") or ""))
            message_box.configure(state="disabled")
            contact_tree = ttk.Treeview(panel, columns=("name", "phone", "status", "error"), show="headings")
            for column, heading, width in [
                ("name", "Contato", 210),
                ("phone", "Telefone", 130),
                ("status", "Status", 130),
                ("error", "Ultimo erro", 360),
            ]:
                contact_tree.heading(column, text=heading)
                contact_tree.column(column, width=width, anchor="w")
            contact_tree.pack(fill="both", expand=True)
            for contact in campaigns.get_campaign_contacts(campaign_id):
                contact_tree.insert(
                    "",
                    "end",
                    values=(
                        contact.get("name") or "",
                        contact.get("phone") or "",
                        friendly_status(contact.get("campaign_status")),
                        contact.get("last_error") or "",
                    ),
                )

        def show_campaign_history() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            dialog = tk.Toplevel(self)
            dialog.title(f"Historico da campanha #{campaign_id}")
            dialog.geometry("980x520")
            panel = ttk.Frame(dialog, padding=16)
            panel.pack(fill="both", expand=True)
            logs = campaigns.list_campaign_logs(campaign_id)
            ttk.Label(
                panel,
                text="" if logs else "Esta campanha ainda nao tem historico de envio.",
                style="Muted.TLabel",
            ).pack(anchor="w", pady=(0, 8))
            log_tree = ttk.Treeview(panel, columns=("created", "recipient", "phone", "status", "action", "error"), show="headings")
            for column, heading, width in [
                ("created", "Data/hora", 145),
                ("recipient", "Contato", 170),
                ("phone", "Telefone", 130),
                ("status", "Status", 120),
                ("action", "Manual", 110),
                ("error", "Erro", 360),
            ]:
                log_tree.heading(column, text=heading)
                log_tree.column(column, width=width, anchor="w")
            log_tree.pack(fill="both", expand=True)
            action_urls: dict[str, str] = {}
            for log in logs:
                node = log_tree.insert(
                    "",
                    "end",
                    values=(
                        log.get("created_at") or "",
                        log.get("recipient_name") or "",
                        log.get("phone") or "",
                        friendly_status(log.get("status")),
                        "Abrir" if log.get("action_url") else "",
                        log.get("error_message") or "",
                    ),
                )
                if log.get("action_url"):
                    action_urls[node] = str(log["action_url"])

            def open_manual_link() -> None:
                if not log_tree.selection():
                    messagebox.showwarning(APP_TITLE, "Escolha uma linha com link manual.")
                    return
                url = action_urls.get(log_tree.selection()[0])
                if not url:
                    messagebox.showwarning(APP_TITLE, "Esta linha nao tem link manual.")
                    return
                webbrowser.open(url)

            ttk.Button(panel, text="Abrir link manual", command=open_manual_link).pack(anchor="w", pady=(10, 0))

        tree.bind("<<TreeviewSelect>>", on_select)
        refresh_button.configure(command=refresh)
        open_button.configure(command=open_campaign)
        send_button.configure(command=send_now)
        schedule_button.configure(command=schedule_selected)
        pause_button.configure(command=pause)
        continue_button.configure(command=continue_campaign)
        cancel_button.configure(command=cancel)
        history_button.configure(command=show_campaign_history)
        save_button.configure(command=save_changes)
        refresh()

    def show_risk(self) -> None:
        frame = self._screen("Conferir risco")
        risks = compliance.list_campaign_risks()

        chart = tk.Canvas(frame, height=190, background="#ffffff", highlightthickness=0)
        chart.pack(fill="x", pady=(0, 14))
        self._draw_risk_chart(chart, risks[:6])

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)

        columns = ("id", "campaign", "score", "level", "summary")
        tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in [
            ("id", "ID", 55),
            ("campaign", "Campanha", 220),
            ("score", "Risco", 80),
            ("level", "Alerta", 100),
            ("summary", "Principal motivo", 420),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        tree.pack(side="left", fill="both", expand=True)

        detail = ttk.Frame(body, style="Panel.TFrame", padding=16)
        detail.pack(side="right", fill="both", expand=True, padx=(16, 0))
        score_var = tk.StringVar(value="Escolha uma campanha para ver os cuidados.")
        notes_var = tk.StringVar(value="")
        ttk.Label(detail, textvariable=score_var, style="Panel.TLabel", font=("Segoe UI Semibold", 14)).pack(anchor="w")
        detail_bar = tk.Canvas(detail, height=28, background="#ffffff", highlightthickness=0)
        detail_bar.pack(fill="x", pady=(12, 12))
        ttk.Label(detail, textvariable=notes_var, style="Panel.TLabel", wraplength=420, justify="left").pack(anchor="w")

        risk_by_id = {}
        for risk in risks:
            risk_by_id[int(risk["campaign_id"])] = risk
            notes = risk["notes"]
            tree.insert(
                "",
                "end",
                values=(
                    risk["campaign_id"],
                    risk["campaign_name"],
                    f"{risk['score']}%",
                    friendly_status(risk["level"]),
                    notes[0] if notes else "",
                ),
            )

        def show_detail(_event: object | None = None) -> None:
            if not tree.selection():
                return
            campaign_id = int(tree.item(tree.selection()[0], "values")[0])
            risk = risk_by_id[campaign_id]
            score_var.set(f"{risk['score']}% - {friendly_status(risk['level']).upper()}")
            notes_var.set("\n".join(f"- {note}" for note in risk["notes"]))
            self._draw_single_risk_bar(detail_bar, int(risk["score"]))

        tree.bind("<<TreeviewSelect>>", show_detail)
        if tree.get_children():
            tree.selection_set(tree.get_children()[0])
            show_detail()

    def _draw_risk_chart(self, canvas: tk.Canvas, risks: list[dict[str, object]]) -> None:
        def redraw(_event: object | None = None) -> None:
            canvas.delete("all")
            width = max(canvas.winfo_width(), 400)
            if not risks:
                canvas.create_text(20, 90, text="Nenhuma campanha salva ainda.", anchor="w", fill="#6b7280")
                return
            left = 140
            top = 18
            bar_width = max(width - left - 45, 180)
            for index, risk in enumerate(risks):
                y = top + index * 26
                score = int(risk["score"])
                name = str(risk["campaign_name"])[:22]
                color = self._risk_color(score)
                canvas.create_text(12, y + 9, text=name, anchor="w", fill="#111827", font=("Segoe UI", 9))
                canvas.create_rectangle(left, y, left + bar_width, y + 16, fill="#e5e7eb", outline="")
                canvas.create_rectangle(left, y, left + int(bar_width * score / 100), y + 16, fill=color, outline="")
                canvas.create_text(left + bar_width + 8, y + 8, text=f"{score}%", anchor="w", fill="#111827")

        canvas.bind("<Configure>", redraw)
        redraw()

    def _draw_single_risk_bar(self, canvas: tk.Canvas, score: int) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 260)
        canvas.create_rectangle(0, 4, width, 24, fill="#e5e7eb", outline="")
        canvas.create_rectangle(0, 4, int(width * score / 100), 24, fill=self._risk_color(score), outline="")
        canvas.create_text(width / 2, 14, text=f"{score}%", fill="#111827", font=("Segoe UI Semibold", 10))

    def _risk_color(self, score: int) -> str:
        if score >= 75:
            return "#dc2626"
        if score >= 50:
            return "#f97316"
        if score >= 25:
            return "#eab308"
        return "#16a34a"

    def show_history(self) -> None:
        frame = self._screen("Histórico de envios")
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="Atualizar", command=self.show_history).pack(side="left")
        ttk.Button(top, text="Abrir WhatsApp manual", command=lambda: open_action()).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Telefones já usados", command=self.show_sent_numbers).pack(side="left", padx=(8, 0))
        columns = ("created_at", "campaign", "recipient", "phone", "status", "action", "error")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, heading, width in [
            ("created_at", "Data/hora", 150),
            ("campaign", "Campanha", 180),
            ("recipient", "Contato", 160),
            ("phone", "Telefone", 130),
            ("status", "Status", 110),
            ("action", "Abrir manualmente", 160),
            ("error", "Erro", 360),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        action_urls: dict[str, str] = {}
        for item in campaigns.list_logs():
            node = tree.insert(
                "",
                "end",
                values=(
                    item["created_at"],
                    item.get("campaign_name") or "",
                    item["recipient_name"],
                    item["phone"],
                    friendly_status(item["status"]),
                    "Abrir WhatsApp" if item.get("action_url") else "",
                    item["error_message"],
                ),
            )
            if item.get("action_url"):
                action_urls[node] = str(item["action_url"])

        def open_action() -> None:
            if not tree.selection():
                messagebox.showwarning(APP_TITLE, "Escolha uma linha que tenha link para abrir manualmente.")
                return
            url = action_urls.get(tree.selection()[0])
            if not url:
                messagebox.showinfo(APP_TITLE, "Essa linha não tem link manual.")
                return
            self._open_external_link(url)

    def show_sent_numbers(self) -> None:
        window = tk.Toplevel(self)
        window.title("Telefones já usados")
        window.geometry("780x460")
        window.transient(self)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        columns = ("phone", "name", "campaign", "status", "attempts", "last")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, heading, width in [
            ("phone", "Telefone", 130),
            ("name", "Cliente", 160),
            ("campaign", "Campanha", 180),
            ("status", "Status", 120),
            ("attempts", "Vezes", 80),
            ("last", "Última vez", 150),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        for item in contacts.list_used_phones():
            tree.insert(
                "",
                "end",
                values=(
                    item["phone"],
                    item["recipient_name"],
                    item.get("campaign_name") or "",
                    friendly_status(item["status"]),
                    item["attempts"],
                    item["last_sent_at"],
                ),
            )

    def show_number_health(self) -> None:
        frame = self._screen("Aquecimento dos números")
        stats = warmup.dashboard_stats()
        metrics = ttk.Frame(frame)
        metrics.pack(fill="x", pady=(0, 12))
        for label, value in [
            ("Números", stats["total"]),
            ("Ativos", stats["active"]),
            ("Prontos para campanha", stats["ready"]),
            ("Pausados", stats["paused"]),
        ]:
            card = ttk.Frame(metrics, style="Panel.TFrame", padding=12)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, text=str(value), style="Metric.TLabel").pack(anchor="w")
            ttk.Label(card, text=label, style="Muted.TLabel").pack(anchor="w")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        columns = ("id", "name", "phone", "status", "score", "quality", "target", "today", "rest", "ready")
        tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=10)
        for column, heading, width in [
            ("id", "ID", 50),
            ("name", "Nome", 150),
            ("phone", "Telefone", 120),
            ("status", "Status", 90),
            ("score", "Score", 65),
            ("quality", "Qualidade", 80),
            ("target", "Pode enviar hoje", 100),
            ("today", "Já enviou", 75),
            ("rest", "Não enviar", 110),
            ("ready", "Pronto", 65),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="x")

        event_columns = ("created_at", "number", "recipient", "phone", "status", "error")
        event_tree = ttk.Treeview(left, columns=event_columns, show="headings")
        ttk.Label(left, text="Últimos testes de aquecimento", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(14, 6))
        for column, heading, width in [
            ("created_at", "Data/hora", 145),
            ("number", "Número usado", 130),
            ("recipient", "Cliente", 150),
            ("phone", "Telefone", 120),
            ("status", "Status", 100),
            ("error", "Erro", 280),
        ]:
            event_tree.heading(column, text=heading)
            event_tree.column(column, width=width, anchor="w")
        event_tree.pack(fill="both", expand=True)

        form = ttk.Frame(body, style="Panel.TFrame", padding=16)
        form.pack(side="right", fill="y", padx=(16, 0))
        selected_id = tk.IntVar(value=0)
        display_name = tk.StringVar()
        phone = tk.StringVar()
        phone_number_id = tk.StringVar()
        provider = tk.StringVar(value="oficial")
        status = tk.StringVar(value="testing")
        quality = tk.StringVar(value="unknown")
        messaging_limit = tk.StringVar(value="250")
        daily_target = tk.StringVar(value="20")
        max_daily_target = tk.StringVar(value="500")
        rest_start = tk.StringVar(value="00:00")
        rest_end = tk.StringVar(value="07:00")
        group_name = tk.StringVar()
        notes = tk.StringVar()
        active = tk.BooleanVar(value=True)
        ready = tk.BooleanVar(value=False)
        progress = tk.StringVar(value="Escolha um número e clique em Iniciar aquecimento.")

        for label, variable in [
            ("Nome para identificar o número", display_name),
            ("Telefone do número", phone),
            ("ID do número na Meta", phone_number_id),
            ("Tipo de envio deste número", provider),
        ]:
            self._entry(form, label, variable).pack(fill="x", pady=(0, 8))

        for label, variable, values in [
            ("Status", status, ("testing", "healthy", "paused", "auto_paused", "restricted", "banned")),
            ("Qualidade", quality, ("unknown", "high", "medium", "low")),
        ]:
            holder = ttk.Frame(form, style="Panel.TFrame")
            holder.pack(fill="x", pady=(0, 8))
            ttk.Label(holder, text=label, style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
            ttk.Combobox(holder, textvariable=variable, values=values).pack(fill="x")

        for label, variable in [
            ("Limite da conta", messaging_limit),
            ("Começar com envios por dia", daily_target),
            ("Limite máximo por dia", max_daily_target),
            ("Não enviar de HH:MM", rest_start),
            ("Voltar a enviar em HH:MM", rest_end),
            ("Notas", notes),
        ]:
            self._entry(form, label, variable).pack(fill="x", pady=(0, 8))

        ttk.Checkbutton(form, text="Número ativo", variable=active).pack(anchor="w")
        ttk.Checkbutton(form, text="Já pode usar em campanhas", variable=ready).pack(anchor="w", pady=(0, 8))

        holder = ttk.Frame(form, style="Panel.TFrame")
        holder.pack(fill="x", pady=(4, 8))
        ttk.Label(holder, text="Grupo de clientes para testar", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        groups = [""] + contacts.list_groups()
        ttk.Combobox(holder, textvariable=group_name, values=groups).pack(fill="x")
        ttk.Label(form, textvariable=progress, style="Muted.TLabel", wraplength=310).pack(anchor="w", pady=(0, 8))

        def selected_number_id() -> int | None:
            if not tree.selection():
                messagebox.showwarning(APP_TITLE, "Escolha um número primeiro.")
                return None
            return int(tree.item(tree.selection()[0], "values")[0])

        def clear_form() -> None:
            selected_id.set(0)
            for variable in (display_name, phone, phone_number_id, notes):
                variable.set("")
            provider.set("oficial")
            status.set("testing")
            quality.set("unknown")
            messaging_limit.set("250")
            daily_target.set("20")
            max_daily_target.set("500")
            rest_start.set("00:00")
            rest_end.set("07:00")
            active.set(True)
            ready.set(False)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for item in warmup.list_numbers():
                tree.insert(
                    "",
                    "end",
                    values=(
                        item["id"],
                        item["display_name"],
                        item["phone"],
                        friendly_status(item["status"]),
                        item.get("health_score") or 85,
                        friendly_status(item["quality_rating"]),
                        item.get("current_daily_target") or item["daily_target"],
                        item.get("sent_today") or 0,
                        f"{item['rest_start']}-{item['rest_end']}",
                        "Sim" if item["ready_for_campaigns"] else "Nao",
                    ),
                )
            event_tree.delete(*event_tree.get_children())
            for event in warmup.list_recent_events():
                event_tree.insert(
                    "",
                    "end",
                    values=(
                        event["created_at"],
                        event["number_name"],
                        event["recipient_name"],
                        event["phone"],
                        friendly_status(event["status"]),
                        event["error_message"],
                    ),
                )

        def on_select(_event: object) -> None:
            number_id = selected_number_id()
            if not number_id:
                return
            data = warmup.get_number(number_id)
            if not data:
                return
            selected_id.set(int(data["id"]))
            display_name.set(str(data["display_name"]))
            phone.set(str(data["phone"]))
            phone_number_id.set(str(data.get("phone_number_id") or ""))
            provider.set(str(data.get("provider") or "oficial"))
            status.set(str(data.get("status") or "testing"))
            quality.set(str(data.get("quality_rating") or "unknown"))
            messaging_limit.set(str(data.get("messaging_limit") or "250"))
            daily_target.set(str(data.get("daily_target") or "10"))
            max_daily_target.set(str(data.get("max_daily_target") or "100"))
            rest_start.set(str(data.get("rest_start") or "22:00"))
            rest_end.set(str(data.get("rest_end") or "08:00"))
            notes.set(str(data.get("notes") or ""))
            active.set(bool(data.get("active")))
            ready.set(bool(data.get("ready_for_campaigns")))

        def save() -> None:
            try:
                if selected_id.get():
                    warmup.update_number(
                        selected_id.get(),
                        display_name=display_name.get(),
                        phone=phone.get(),
                        phone_number_id=phone_number_id.get(),
                        provider=provider.get(),
                        status=status.get(),
                        quality_rating=quality.get(),
                        messaging_limit=messaging_limit.get(),
                        daily_target=daily_target.get(),
                        max_daily_target=max_daily_target.get(),
                        active=active.get(),
                        ready_for_campaigns=ready.get(),
                        rest_start=rest_start.get(),
                        rest_end=rest_end.get(),
                        notes=notes.get(),
                    )
                else:
                    selected_id.set(
                        warmup.add_number(
                            display_name.get(),
                            phone.get(),
                            phone_number_id.get(),
                            provider.get(),
                            status.get(),
                            quality.get(),
                            int(float(messaging_limit.get().replace(",", "."))),
                            int(float(daily_target.get().replace(",", "."))),
                            int(float(max_daily_target.get().replace(",", "."))),
                            active.get(),
                            rest_start.get(),
                            rest_end.get(),
                            notes.get(),
                        )
                    )
            except (ValueError, warmup.WarmupError) as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            refresh()
            self._set_status("Número salvo.")

        def delete() -> None:
            number_id = selected_number_id()
            if not number_id:
                return
            if messagebox.askyesno(APP_TITLE, "Excluir este número e o histórico dele?"):
                warmup.delete_number(number_id)
                clear_form()
                refresh()

        def start() -> None:
            number_id = selected_number_id()
            if number_id:
                self._start_number_warmup_thread(number_id, group_name.get(), progress)

        def stop() -> None:
            number_id = selected_number_id()
            if not number_id:
                return
            event = self.running_warmups.get(number_id)
            if event:
                event.set()
                progress.set("Pausa solicitada.")

        tree.bind("<<TreeviewSelect>>", on_select)
        actions = ttk.Frame(form, style="Panel.TFrame")
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Novo", command=clear_form).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(actions, text="Salvar", style="Accent.TButton", command=save).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        ttk.Button(actions, text="Iniciar aquecimento", style="Accent.TButton", command=start).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(actions, text="Pausar", command=stop).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        ttk.Button(actions, text="Excluir", command=delete).grid(row=2, column=0, sticky="ew")
        ttk.Button(actions, text="Atualizar", command=refresh).grid(row=2, column=1, sticky="ew", padx=(8, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        refresh()

    def show_settings(self) -> None:
        frame = self._screen("Configurações")
        frame = self._scrollable_frame(frame)
        config = whatsapp.load_config()

        left = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        frame.columnconfigure(0, weight=1, uniform="settings")
        frame.columnconfigure(1, weight=1, uniform="settings")

        token = tk.StringVar()
        phone_number_id = tk.StringVar(value=config.phone_number_id)
        business_account_id = tk.StringVar(value=config.business_account_id)
        webhook_url = tk.StringVar(value=config.webhook_url)
        api_version = tk.StringVar(value=config.api_version)
        default_template = tk.StringVar(value=config.default_template)
        default_language = tk.StringVar(value=config.default_language)
        delivery_modes = {
            "Envio oficial pela Meta": "official_api",
            "Modo manual com link": "manual_assisted",
        }
        delivery_mode_labels = {value: label for label, value in delivery_modes.items()}
        delivery_mode = tk.StringVar(value=delivery_mode_labels.get(config.delivery_mode, "Envio oficial pela Meta"))
        dry_run = tk.BooleanVar(value=config.dry_run)
        block_high_risk = tk.BooleanVar(value=get_setting("block_high_risk_campaigns", "1") == "1")
        smart_send = tk.BooleanVar(value=get_setting("smart_send_enabled", "0") == "1")
        start_with_windows = tk.BooleanVar(value=startup.is_startup_enabled())
        interval = tk.StringVar(value=str(config.send_interval_seconds))
        daily_limit = tk.StringVar(value=str(config.daily_send_limit))
        smart_min_interval = tk.StringVar(value=get_setting("smart_min_interval_seconds", "30"))
        smart_max_interval = tk.StringVar(value=get_setting("smart_max_interval_seconds", "45"))
        smart_pause_every = tk.StringVar(value=get_setting("smart_pause_every", "10"))
        smart_pause_min = tk.StringVar(value=get_setting("smart_pause_min_seconds", "120"))
        smart_pause_max = tk.StringVar(value=get_setting("smart_pause_max_seconds", "300"))
        smart_daily_limit = tk.StringVar(value=get_setting("smart_daily_limit", "100"))
        smart_max_session = tk.StringVar(value=get_setting("smart_max_session_minutes", "90"))
        rampup_min_interval = tk.StringVar(value=get_setting("rampup_min_interval_seconds", "45"))
        rampup_max_interval = tk.StringVar(value=get_setting("rampup_max_interval_seconds", "180"))
        rampup_daily_floor = tk.StringVar(value=get_setting("rampup_daily_floor", "5"))
        company_name = tk.StringVar(value=get_setting("company_name", "Mezzold"))
        internet_status = tk.StringVar(value="Internet: ainda não testada.")

        ttk.Label(left, text="Envio pelo WhatsApp oficial", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        internet_panel = ttk.Frame(left, style="Panel.TFrame")
        internet_panel.pack(fill="x", pady=(8, 0))
        ttk.Label(
            internet_panel,
            text="Para enviar mensagens, abrir WhatsApp manual ou usar a API oficial, este computador precisa estar online.",
            style="Muted.TLabel",
            wraplength=520,
        ).pack(anchor="w")
        ttk.Label(internet_panel, textvariable=internet_status, style="Panel.TLabel").pack(side="left", pady=(8, 0))
        ttk.Button(internet_panel, text="Testar internet", command=lambda: self._update_internet_status(internet_status)).pack(side="right", pady=(8, 0))
        mode_frame = ttk.Frame(left, style="Panel.TFrame")
        mode_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(mode_frame, text="Como o app deve enviar", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(
            mode_frame,
            textvariable=delivery_mode,
            values=tuple(delivery_modes.keys()),
            state="readonly",
        ).pack(fill="x")
        warning = (
            "Modo manual abre um link do WhatsApp para você concluir o envio. "
            "Envio automático real deve usar a API oficial para reduzir risco de bloqueio."
        )
        ttk.Label(left, text=warning, style="Muted.TLabel", wraplength=430).pack(anchor="w", pady=(8, 0))
        for label, variable in [
            ("Token da Meta (deixe em branco para manter o atual)", token),
            ("ID do número no WhatsApp Business", phone_number_id),
            ("ID da conta empresarial da Meta", business_account_id),
            ("Webhook", webhook_url),
            ("Versão da API da Meta", api_version),
            ("Modelo aprovado padrão", default_template),
            ("Idioma padrão do modelo", default_language),
        ]:
            self._entry(left, label, variable, show="*" if label.startswith("Token") else None).pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(left, text="Modo teste: registrar sem enviar de verdade", variable=dry_run).pack(anchor="w", pady=(14, 0))
        ttk.Checkbutton(left, text="Impedir envio quando o risco estiver muito alto", variable=block_high_risk).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            left,
            text="Começar sozinho quando ligar o computador",
            variable=start_with_windows,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            left,
            text="Usar pausas automáticas entre mensagens",
            variable=smart_send,
        ).pack(anchor="w", pady=(8, 0))
        smart_note = (
            "Use pelo menos 3 versões de mensagem. Isso deixa o envio mais natural, mas não garante que a conta nunca será bloqueada."
        )
        ttk.Label(left, text=smart_note, style="Muted.TLabel", wraplength=430).pack(anchor="w", pady=(6, 0))

        ttk.Label(right, text="Dados gerais e limites", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        for label, variable in [
            ("Nome da empresa", company_name),
            ("Intervalo entre envios (segundos)", interval),
            ("Máximo de envios por dia", daily_limit),
        ]:
            self._entry(right, label, variable).pack(fill="x", pady=(10, 0))

        ttk.Label(right, text="Pausas automáticas", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(18, 0))
        smart_grid = ttk.Frame(right, style="Panel.TFrame")
        smart_grid.pack(fill="x")
        smart_fields = [
            ("Espera mínima (s)", smart_min_interval),
            ("Espera máxima (s)", smart_max_interval),
            ("Pausa a cada X envios", smart_pause_every),
            ("Pausa curta mínima (s)", smart_pause_min),
            ("Pausa curta máxima (s)", smart_pause_max),
            ("Máximo diário neste modo", smart_daily_limit),
            ("Tempo máximo seguido (min)", smart_max_session),
        ]
        for index, (label, variable) in enumerate(smart_fields):
            holder = ttk.Frame(smart_grid, style="Panel.TFrame")
            holder.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 0), pady=(10, 0))
            smart_grid.columnconfigure(index % 2, weight=1)
            self._entry(holder, label, variable).pack(fill="x")

        ttk.Label(right, text="Aquecimento dos números", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(18, 0))
        rampup_grid = ttk.Frame(right, style="Panel.TFrame")
        rampup_grid.pack(fill="x")
        for index, (label, variable) in enumerate([
            ("Espera mínima entre testes (s)", rampup_min_interval),
            ("Espera máxima entre testes (s)", rampup_max_interval),
            ("Envios bons para liberar número", rampup_daily_floor),
        ]):
            holder = ttk.Frame(rampup_grid, style="Panel.TFrame")
            holder.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 0), pady=(10, 0))
            rampup_grid.columnconfigure(index % 2, weight=1)
            self._entry(holder, label, variable).pack(fill="x")

        license_data = self._load_license()
        license_key = tk.StringVar(value=str(license_data.get("license_key", "")))
        license_plan = tk.StringVar(value=str(license_data.get("plan_name", "")))
        license_until = tk.StringVar(value=str(license_data.get("valid_until", "")))
        ttk.Label(right, text="Licença", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(20, 0))
        for label, variable in [
            ("Código da licença", license_key),
            ("Plano", license_plan),
            ("Validade", license_until),
        ]:
            self._entry(right, label, variable).pack(fill="x", pady=(10, 0))

        def save() -> None:
            try:
                config_to_save = whatsapp.WhatsAppConfig(
                    api_version=api_version.get(),
                    phone_number_id=phone_number_id.get(),
                    business_account_id=business_account_id.get(),
                    webhook_url=webhook_url.get(),
                    default_template=default_template.get(),
                    default_language=default_language.get(),
                    delivery_mode=delivery_modes.get(delivery_mode.get(), "official_api"),
                    dry_run=dry_run.get(),
                    send_interval_seconds=float(interval.get().replace(",", ".")),
                    daily_send_limit=int(float(daily_limit.get().replace(",", "."))),
                )
                if not self._confirm_settings_save():
                    return
                whatsapp.save_config(config_to_save, token.get().strip() or None)
                set_setting("company_name", company_name.get())
                set_setting("block_high_risk_campaigns", "1" if block_high_risk.get() else "0")
                if startup.is_supported():
                    startup.set_startup_enabled(start_with_windows.get())
                elif start_with_windows.get():
                    raise RuntimeError("Inicialização automática está disponível apenas no Windows.")
                self._save_smart_send_settings(
                    smart_send.get(),
                    smart_min_interval.get(),
                    smart_max_interval.get(),
                    smart_pause_every.get(),
                    smart_pause_min.get(),
                    smart_pause_max.get(),
                    smart_daily_limit.get(),
                    smart_max_session.get(),
                )
                self._save_rampup_settings(
                    rampup_min_interval.get(),
                    rampup_max_interval.get(),
                    rampup_daily_floor.get(),
                )
                self._save_license(license_key.get(), license_plan.get(), license_until.get())
            except (ValueError, RuntimeError, whatsapp.WhatsAppAPIError) as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            messagebox.showinfo(APP_TITLE, "Configurações salvas.")

        def backup() -> None:
            destination = filedialog.asksaveasfilename(
                defaultextension=".sqlite3",
                filetypes=[("Backup SQLite", "*.sqlite3"), ("Todos", "*.*")],
                initialfile=f"mezzold-connect-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.sqlite3",
            )
            if not destination:
                return
            shutil.copy2(DB_PATH, destination)
            messagebox.showinfo(APP_TITLE, "Backup criado com sucesso.")

        actions = ttk.Frame(right, style="Panel.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        action_buttons = [
            ("Salvar configurações", save, "Accent.TButton"),
            ("Criar backup", backup, "TButton"),
            ("Política oficial do WhatsApp", lambda: self._open_external_link(WHATSAPP_POLICY_URL), "TButton"),
            ("Documentação Cloud API", lambda: self._open_external_link(META_CLOUD_API_URL), "TButton"),
        ]
        for index, (label, command, style_name) in enumerate(action_buttons):
            button = ttk.Button(actions, text=label, command=command, style=style_name)
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 0), pady=(0, 8))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        about = (
            f"{APP_TITLE} {APP_VERSION}\n"
            "Aplicativo local para cuidar de clientes, campanhas, aquecimento de números, histórico e segurança dos envios."
        )
        ttk.Label(right, text=about, style="Muted.TLabel", wraplength=430).pack(anchor="w", pady=(20, 0))

    def _save_smart_send_settings(
        self,
        enabled: bool,
        min_interval: str,
        max_interval: str,
        pause_every: str,
        pause_min: str,
        pause_max: str,
        daily_limit: str,
        max_session: str,
    ) -> None:
        values = {
            "smart_min_interval_seconds": self._positive_int(min_interval, "Espera mínima", 1),
            "smart_max_interval_seconds": self._positive_int(max_interval, "Espera máxima", 1),
            "smart_pause_every": self._positive_int(pause_every, "Pausa a cada X envios", 1),
            "smart_pause_min_seconds": self._positive_int(pause_min, "Pausa mínima", 0),
            "smart_pause_max_seconds": self._positive_int(pause_max, "Pausa máxima", 0),
            "smart_daily_limit": self._positive_int(daily_limit, "Máximo diário", 1),
            "smart_max_session_minutes": self._positive_int(max_session, "Tempo máximo seguido", 5),
        }
        if values["smart_max_interval_seconds"] < values["smart_min_interval_seconds"]:
            raise ValueError("A espera máxima precisa ser igual ou maior que a espera mínima.")
        if values["smart_pause_max_seconds"] < values["smart_pause_min_seconds"]:
            raise ValueError("A pausa máxima precisa ser igual ou maior que a pausa mínima.")
        set_setting("smart_send_enabled", "1" if enabled else "0")
        for key, value in values.items():
            set_setting(key, str(value))

    def _save_rampup_settings(self, min_interval: str, max_interval: str, daily_floor: str) -> None:
        values = {
            "rampup_min_interval_seconds": self._positive_int(min_interval, "Espera mínima do aquecimento", 1),
            "rampup_max_interval_seconds": self._positive_int(max_interval, "Espera máxima do aquecimento", 1),
            "rampup_daily_floor": self._positive_int(daily_floor, "Envios bons para liberar número", 1),
        }
        if values["rampup_max_interval_seconds"] < values["rampup_min_interval_seconds"]:
            raise ValueError("A espera máxima do aquecimento precisa ser igual ou maior que a mínima.")
        for key, value in values.items():
            set_setting(key, str(value))

    def _positive_int(self, value: str, label: str, minimum: int) -> int:
        try:
            parsed = int(float(value.replace(",", ".")))
        except ValueError as exc:
            raise ValueError(f"{label}: informe apenas números.") from exc
        if parsed < minimum:
            raise ValueError(f"{label}: use um valor igual ou maior que {minimum}.")
        return parsed

    def _update_internet_status(self, status_var: tk.StringVar) -> None:
        status_var.set("Testando internet...")
        self.update_idletasks()
        if network.has_internet():
            status_var.set("Internet: funcionando.")
        else:
            status_var.set("Internet: sem conexão no momento.")

    def _require_internet(self) -> bool:
        if network.has_internet():
            return True
        messagebox.showerror(
            APP_TITLE,
            "Este computador precisa estar conectado à internet para enviar mensagens ou abrir links do WhatsApp.",
        )
        return False

    def _open_external_link(self, url: str) -> None:
        if self._require_internet():
            webbrowser.open(url)

    def _confirm_settings_save(self) -> bool:
        if not self.current_user:
            messagebox.showerror(APP_TITLE, "Entre de novo para salvar as configurações.")
            return False

        code = f"{secrets.randbelow(900000) + 100000}"
        dialog = tk.Toplevel(self)
        dialog.title("Confirmar salvamento")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = {"ok": False}
        password = tk.StringVar()
        typed_code = tk.StringVar()

        panel = ttk.Frame(dialog, padding=18)
        panel.pack(fill="both", expand=True)
        ttk.Label(
            panel,
            text="Confirme antes de salvar",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        ttk.Label(
            panel,
            text="Para proteger a conta, digite sua senha e copie o código mostrado abaixo.",
            wraplength=360,
        ).pack(anchor="w", pady=(8, 10))
        ttk.Label(panel, text=f"Código: {code}", font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(0, 10))
        self._entry(panel, "Sua senha", password, show="*").pack(fill="x", pady=(0, 10))
        self._entry(panel, "Código de confirmação", typed_code).pack(fill="x", pady=(0, 14))

        def confirm() -> None:
            user = auth.authenticate(self.current_user.username, password.get())
            if not user:
                messagebox.showerror(APP_TITLE, "Senha não confere.", parent=dialog)
                return
            if typed_code.get().strip() != code:
                messagebox.showerror(APP_TITLE, "Código não confere.", parent=dialog)
                return
            result["ok"] = True
            dialog.destroy()

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Salvar agora", style="Accent.TButton", command=confirm).pack(side="right", padx=(0, 8))

        dialog.bind("<Return>", lambda _event: confirm())
        dialog.wait_window()
        return bool(result["ok"])

    def _save_license(self, license_key: str, plan: str, valid_until: str) -> None:
        from database import now_text

        status = "ativa" if license_key.strip() else "pendente"
        with connect() as conn:
            conn.execute(
                """
                UPDATE license
                SET license_key = ?, plan_name = ?, valid_until = ?, status = ?, updated_at = ?
                WHERE id = 1
                """,
                (license_key.strip(), plan.strip(), valid_until.strip(), status, now_text()),
            )

    def _load_license(self) -> dict[str, object]:
        with connect() as conn:
            row = conn.execute("SELECT * FROM license WHERE id = 1").fetchone()
        return row_to_dict(row) or {}

    def _campaign_tree(self, parent: tk.Widget) -> ttk.Treeview:
        columns = ("id", "name", "status", "risk", "scheduled", "contacts", "sent", "failed")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in [
            ("id", "ID", 55),
            ("name", "Nome", 230),
            ("status", "Status", 110),
            ("risk", "Risco", 80),
            ("scheduled", "Agendamento", 160),
            ("contacts", "Contatos", 80),
            ("sent", "Enviados", 80),
            ("failed", "Falhas", 80),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        return tree

    def _fill_campaign_tree(self, tree: ttk.Treeview) -> None:
        tree.delete(*tree.get_children())
        for item in campaigns.list_campaigns():
            try:
                risk = compliance.refresh_campaign_risk(int(item["id"]))
                item["risk_score"] = risk["score"]
            except ValueError:
                item["risk_score"] = item.get("risk_score") or 0
            tree.insert(
                "",
                "end",
                values=(
                    item["id"],
                    item["name"],
                    friendly_status(item["status"]),
                    f"{item.get('risk_score') or 0}%",
                    item["scheduled_at"] or "",
                    item["total_contacts"] or 0,
                    item["sent_contacts"] or 0,
                    item["failed_contacts"] or 0,
                ),
            )

    def _start_campaign_thread(
        self,
        campaign_id: int,
        progress_var: tk.StringVar | None = None,
        interactive: bool = True,
        internet_alert: bool = True,
        source: str = "ui",
        allow_resume: bool = False,
    ) -> None:
        if campaign_id in self.running_events:
            messagebox.showinfo(APP_TITLE, "Esta campanha já está sendo enviada.")
            return
        can_start, reason = campaigns.can_start_campaign(campaign_id, allow_resume=allow_resume)
        if not can_start:
            if interactive:
                messagebox.showinfo(APP_TITLE, reason)
            else:
                self._set_status(reason)
            return
        if not network.has_internet():
            if internet_alert:
                self._require_internet()
            else:
                self._set_status("Envios pausados: sem internet no momento.")
            return

        risk = compliance.refresh_campaign_risk(campaign_id)
        if interactive and int(risk["score"]) >= 50:
            notes = "\n".join(f"- {note}" for note in risk["notes"][:4])
            proceed = messagebox.askyesno(
                APP_TITLE,
                f"Esta campanha precisa de atenção: {risk['score']}% de risco ({risk['level']}).\n\n{notes}\n\nDeseja enviar mesmo assim?",
            )
            if not proceed:
                return

        event = threading.Event()
        self.running_events[campaign_id] = event

        def progress(current: int, total: int, message: str) -> None:
            text = f"{current}/{total} - {message}"
            self.after(0, lambda: self._set_status(text))
            if progress_var:
                self.after(0, lambda: progress_var.set(text))

        def worker() -> None:
            try:
                totals = campaigns.send_campaign(
                    campaign_id,
                    progress_callback=progress,
                    stop_event=event,
                    runner=source,
                    allow_resume=allow_resume,
                )
                done = (
                    f"Campanha #{campaign_id}: enviados {totals['enviado']}, "
                    f"simulados {totals['simulado']}, manuais {totals['pendente_manual']}, "
                    f"falhas {totals['falhou']}."
                )
                self.after(0, lambda: self._set_status(done))
            except campaigns.CampaignError as exc:
                if interactive:
                    self.after(0, lambda: messagebox.showerror(APP_TITLE, str(exc)))
                else:
                    self.after(0, lambda: self._set_status(str(exc)))
            finally:
                self.running_events.pop(campaign_id, None)
                self.after(0, self._refresh_current_screen)

        threading.Thread(target=worker, daemon=True).start()
        self._set_status(f"Enviando campanha #{campaign_id}.")

    def _start_number_warmup_thread(
        self,
        number_id: int,
        group_name: str = "",
        progress_var: tk.StringVar | None = None,
    ) -> None:
        if number_id in self.running_warmups:
            messagebox.showinfo(APP_TITLE, "Este número já está em aquecimento.")
            return
        if not whatsapp.load_config().dry_run and not network.has_internet():
            self._require_internet()
            return

        event = threading.Event()
        self.running_warmups[number_id] = event

        def progress(current: int, total: int, message: str) -> None:
            text = f"{current}/{total} - {message}"
            self.after(0, lambda: self._set_status(text))
            if progress_var:
                self.after(0, lambda: progress_var.set(text))

        def worker() -> None:
            try:
                totals = warmup.run_number_rampup(
                    number_id,
                    group_name=group_name,
                    progress_callback=progress,
                    stop_event=event,
                )
                done = (
                    f"Número #{number_id}: enviados {totals['sent']}, "
                    f"simulados {totals['simulated']}, manuais {totals['manual']}, "
                    f"falhas {totals['failed']}."
                )
                self.after(0, lambda: self._set_status(done))
                if progress_var:
                    self.after(0, lambda: progress_var.set(done))
            except warmup.WarmupError as exc:
                self.after(0, lambda: messagebox.showerror(APP_TITLE, str(exc)))
            finally:
                self.running_warmups.pop(number_id, None)
                self.after(0, self._refresh_current_screen)

        threading.Thread(target=worker, daemon=True).start()
        self._set_status(f"Aquecendo número #{number_id}.")

    def _send_due_campaigns(self, quiet: bool = False) -> None:
        due = campaigns.get_due_campaigns()
        if not due:
            if not quiet:
                self._set_status("Não há campanha para enviar agora.")
            return
        for campaign in due:
            self._start_campaign_thread(
                int(campaign["id"]),
                interactive=False,
                internet_alert=not quiet,
                source="ui_scheduler" if quiet else "ui_due_button",
            )

    def _resume_interrupted_campaigns(self) -> None:
        resumable = [item for item in campaigns.get_resumable_campaigns() if campaigns.has_pending_contacts(int(item["id"]))]
        if not resumable:
            return
        if not network.has_internet():
            self._set_status("Há campanhas pausadas aguardando internet.")
            return
        for campaign in resumable:
            self._start_campaign_thread(
                int(campaign["id"]),
                interactive=False,
                internet_alert=False,
                source="ui_resume",
                allow_resume=True,
            )
        self._set_status(f"Retomando {len(resumable)} campanha(s) que estavam paradas.")

    def _scheduler_tick(self) -> None:
        if self.current_user:
            self._send_due_campaigns(quiet=True)
            self.after(60000, self._scheduler_tick)

    def _refresh_current_screen(self) -> None:
        if self.current_screen == "Início":
            self.show_dashboard()
        elif self.current_screen == "Agenda de envios":
            self.show_schedule()
        elif self.current_screen == "Aquecimento dos números":
            self.show_number_health()
        elif self.current_screen == "Conferir risco":
            self.show_risk()
        elif self.current_screen == "Histórico de envios":
            self.show_history()


def parse_datetime(value: str) -> str:
    value = value.strip()
    formats = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    raise campaigns.CampaignError("Use data no formato AAAA-MM-DD HH:MM ou DD/MM/AAAA HH:MM.")


def parse_variants(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    blocks = [block.strip() for block in text.split("\n---\n") if block.strip()]
    if len(blocks) > 1:
        return blocks
    return [line.strip() for line in text.splitlines() if line.strip()]


def run_app() -> None:
    app = MezzoldApp()
    app.mainloop()
