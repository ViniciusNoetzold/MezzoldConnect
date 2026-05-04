from __future__ import annotations

import shutil
import secrets
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import auth
import campaigns
import compliance
import contacts
import network
import startup
import whatsapp
from database import APP_TITLE, APP_VERSION, DB_PATH, connect, get_setting, row_to_dict, set_setting


WHATSAPP_POLICY_URL = "https://www.whatsapp.com/legal/business-policy/"
META_CLOUD_API_URL = "https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview"


class MezzoldApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        self.current_user: auth.User | None = None
        self.content: ttk.Frame | None = None
        self.status_var = tk.StringVar(value="Pronto")
        self.running_events: dict[int, threading.Event] = {}
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
        subtitle = "Crie o primeiro usuário administrador." if initial else "Entre para gerenciar contatos e campanhas."
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
                messagebox.showerror(APP_TITLE, "Usuário ou senha inválidos.")
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
            messagebox.showinfo(APP_TITLE, "Usuário criado com sucesso.")
            self.show_main()

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Entrar", style="Accent.TButton", command=do_login).pack(side="left")
        ttk.Button(actions, text="Criar usuário", command=do_create).pack(side="left", padx=(8, 0))

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
            ("Dashboard", self.show_dashboard),
            ("Contatos", self.show_contacts),
            ("Importar contatos", self.show_import_contacts),
            ("Criar campanha", self.show_create_campaign),
            ("Agendar envio", self.show_schedule),
            ("Risco", self.show_risk),
            ("Histórico", self.show_history),
            ("Configurações", self.show_settings),
        ]
        for label, command in buttons:
            ttk.Button(sidebar, text=label, style="Sidebar.TButton", command=command).pack(fill="x", pady=3)

        ttk.Button(sidebar, text="Sair", command=self.show_login).pack(fill="x", side="bottom")

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
        frame = self._screen("Dashboard")
        metrics = ttk.Frame(frame)
        metrics.pack(fill="x")

        stats = campaigns.dashboard_stats()
        labels = [
            ("Contatos", stats["contacts"]),
            ("Com opt-in", stats["opt_in"]),
            ("Blacklist", stats["blocked"]),
            ("Campanhas", stats["campaigns"]),
            ("Agendadas", stats["scheduled"]),
            ("Enviadas", stats["sent"]),
            ("Falhas", stats["failed"]),
        ]
        for label, value in labels:
            card = ttk.Frame(metrics, style="Panel.TFrame", padding=16)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, text=str(value), style="Metric.TLabel").pack(anchor="w")
            ttk.Label(card, text=label, style="Muted.TLabel").pack(anchor="w")

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=18)
        ttk.Button(actions, text="Atualizar", command=self.show_dashboard).pack(side="left")
        ttk.Button(actions, text="Enviar agendadas agora", command=self._send_due_campaigns).pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="Campanhas recentes", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(12, 8))
        tree = self._campaign_tree(frame)
        tree.pack(fill="both", expand=True)
        self._fill_campaign_tree(tree)

    def show_contacts(self) -> None:
        frame = self._screen("Contatos")
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 10))
        search = tk.StringVar()
        ttk.Label(top, text="Buscar").pack(side="left")
        ttk.Entry(top, textvariable=search, width=34).pack(side="left", padx=(8, 8))
        ttk.Button(top, text="Filtrar", command=lambda: refresh()).pack(side="left")
        ttk.Button(top, text="Importar", command=self.show_import_contacts).pack(side="left", padx=(8, 0))

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        tree_frame = ttk.Frame(body)
        tree_frame.pack(side="left", fill="both", expand=True)
        columns = ("id", "name", "phone", "group", "opt_in", "source", "blacklisted")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "ID",
            "name": "Nome",
            "phone": "Número",
            "group": "Grupo",
            "opt_in": "Opt-in",
            "source": "Origem",
            "blacklisted": "Blacklist",
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
            ("Nome", name),
            ("Número", phone),
            ("E-mail", email),
            ("Grupo/lista", group_name),
            ("Origem do opt-in", opt_in_source),
            ("Categoria autorizada", opt_in_category),
            ("Data do opt-in", opt_in_at),
            ("Última mensagem recebida", last_inbound_at),
            ("Prova/observação do consentimento", consent_notes),
            ("Observações", notes),
        ]:
            self._entry(form, label, variable).pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(form, text="Contato autorizou mensagens", variable=opt_in).pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(form, text="Está na blacklist", variable=blacklisted).pack(anchor="w", pady=(0, 12))

        def clear_form() -> None:
            selected_id.set(0)
            for variable in (name, phone, email, group_name, notes, consent_notes, opt_in_at, last_inbound_at):
                variable.set("")
            opt_in_source.set("manual")
            opt_in_category.set("marketing")
            opt_in.set(True)
            blacklisted.set(False)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for item in contacts.list_contacts(search.get()):
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
            self._set_status("Contatos atualizados.")

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
            self._set_status("Contato salvo.")

        def delete() -> None:
            if not selected_id.get():
                return
            if not messagebox.askyesno(APP_TITLE, "Excluir este contato?"):
                return
            contacts.delete_contact(selected_id.get())
            clear_form()
            refresh()

        tree.bind("<<TreeviewSelect>>", on_select)

        ttk.Button(form, text="Novo", command=clear_form).pack(fill="x", pady=(4, 6))
        ttk.Button(form, text="Salvar", style="Accent.TButton", command=save).pack(fill="x", pady=6)
        ttk.Button(form, text="Opt-out / blacklist", command=lambda: mark_opt_out()).pack(fill="x", pady=6)
        ttk.Button(form, text="Excluir", command=delete).pack(fill="x", pady=6)

        def mark_opt_out() -> None:
            if not selected_id.get():
                return
            contacts.mark_opt_out(selected_id.get(), "Marcado manualmente na interface.")
            refresh()
            clear_form()
        refresh()

    def show_import_contacts(self) -> None:
        frame = self._screen("Importar contatos")
        panel = ttk.Frame(frame, style="Panel.TFrame", padding=18)
        panel.pack(fill="x")
        path = tk.StringVar()
        result = tk.StringVar(
            value="Use CSV ou Excel (.xlsx) com nome, telefone, grupo, opt_in, origem, categoria e data_opt_in."
        )

        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 12))
        ttk.Entry(row, textvariable=path).pack(side="left", fill="x", expand=True)
        ttk.Button(
            row,
            text="Escolher arquivo",
            command=lambda: path.set(filedialog.askopenfilename(filetypes=[("Planilhas", "*.csv *.txt *.xlsx"), ("Todos", "*.*")])),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(panel, textvariable=result, style="Panel.TLabel", wraplength=760).pack(anchor="w", pady=(0, 12))

        def do_import() -> None:
            try:
                summary = contacts.import_contacts(path.get())
            except contacts.ContactError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            errors = "\n".join(summary.errors[:5])
            text = (
                f"Importados: {summary.imported} | Atualizados: {summary.updated} | "
                f"Duplicados no arquivo: {summary.duplicates} | Ignorados: {summary.skipped}"
            )
            if errors:
                text += f"\nPrimeiros avisos:\n{errors}"
            result.set(text)
            self._set_status("Importação concluída.")

        ttk.Button(panel, text="Importar contatos", style="Accent.TButton", command=do_import).pack(anchor="w")

    def show_create_campaign(self) -> None:
        frame = self._screen("Criar campanha")
        form = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        form.pack(side="left", fill="both", expand=True)
        name = tk.StringVar()
        template_name = tk.StringVar(value=whatsapp.load_config().default_template)
        template_language = tk.StringVar(value=whatsapp.load_config().default_language)
        message_category = tk.StringVar(value="marketing")
        media_path = tk.StringVar()

        self._entry(form, "Nome da campanha", name).pack(fill="x", pady=(0, 10))
        category_frame = ttk.Frame(form, style="Panel.TFrame")
        category_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(category_frame, text="Categoria da mensagem", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(
            category_frame,
            textvariable=message_category,
            values=("marketing", "utility", "authentication", "service"),
            state="readonly",
        ).pack(fill="x")
        template_row = ttk.Frame(form, style="Panel.TFrame")
        template_row.pack(fill="x", pady=(0, 10))
        self._entry(template_row, "Template aprovado", template_name).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry(template_row, "Idioma", template_language).pack(side="left", fill="x")

        ttk.Label(form, text="Mensagem/variável do template", style="Panel.TLabel").pack(anchor="w")
        message = tk.Text(form, height=8, wrap="word")
        message.pack(fill="both", expand=True, pady=(4, 10))

        ttk.Label(form, text="Variações adicionais de mensagem", style="Panel.TLabel").pack(anchor="w")
        message_variants = tk.Text(form, height=5, wrap="word")
        message_variants.pack(fill="both", expand=True, pady=(4, 10))

        media_row = ttk.Frame(form, style="Panel.TFrame")
        media_row.pack(fill="x", pady=(0, 12))
        ttk.Entry(media_row, textvariable=media_path).pack(side="left", fill="x", expand=True)
        ttk.Button(
            media_row,
            text="Mídia/URL",
            command=lambda: media_path.set(filedialog.askopenfilename() or media_path.get()),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(form, text="Mídias/URLs alternativas", style="Panel.TLabel").pack(anchor="w")
        media_variants = tk.Text(form, height=3, wrap="word")
        media_variants.pack(fill="x", pady=(4, 10))

        contact_panel = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        contact_panel.pack(side="right", fill="both", expand=True, padx=(16, 0))
        ttk.Label(contact_panel, text="Contatos com opt-in", style="Panel.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w")
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
            ("name", "Nome", 190),
            ("phone", "Número", 130),
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
                    message_category=message_category.get(),
                    message_variants=parse_variants(message_variants.get("1.0", "end")),
                    media_variants=parse_variants(media_variants.get("1.0", "end")),
                )
            except campaigns.CampaignError as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            messagebox.showinfo(APP_TITLE, f"Campanha #{campaign_id} criada como rascunho.")
            self.show_schedule()

        actions = ttk.Frame(contact_panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Selecionar todos", command=select_all).pack(side="left")
        ttk.Button(actions, text="Criar campanha", style="Accent.TButton", command=create).pack(side="right")
        refresh_contacts()

    def show_schedule(self) -> None:
        frame = self._screen("Agendar envio")
        tree = self._campaign_tree(frame)
        tree.pack(fill="both", expand=True)

        controls = ttk.Frame(frame, style="Panel.TFrame", padding=14)
        controls.pack(fill="x", pady=(12, 0))
        scheduled_at = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        ttk.Label(controls, text="Data e horário").pack(side="left")
        ttk.Entry(controls, textvariable=scheduled_at, width=22).pack(side="left", padx=(8, 10))
        progress = tk.StringVar(value="Selecione uma campanha.")
        ttk.Label(controls, textvariable=progress).pack(side="left", padx=(8, 0))

        def selected_campaign_id() -> int | None:
            if not tree.selection():
                messagebox.showwarning(APP_TITLE, "Selecione uma campanha.")
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
            self._set_status("Campanha agendada.")

        def send_now() -> None:
            campaign_id = selected_campaign_id()
            if campaign_id:
                self._start_campaign_thread(campaign_id, progress)

        def pause() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            event = self.running_events.get(campaign_id)
            if event:
                event.set()
            campaigns.pause_campaign(campaign_id)
            refresh()

        def cancel() -> None:
            campaign_id = selected_campaign_id()
            if not campaign_id:
                return
            if messagebox.askyesno(APP_TITLE, "Cancelar esta campanha?"):
                campaigns.cancel_campaign(campaign_id)
                refresh()

        ttk.Button(controls, text="Agendar", command=schedule).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Enviar agora", style="Accent.TButton", command=send_now).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Pausar", command=pause).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Cancelar", command=cancel).pack(side="left", padx=(8, 0))
        refresh()

    def show_risk(self) -> None:
        frame = self._screen("Risco de banimento")
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
            ("level", "Nível", 100),
            ("summary", "Principal motivo", 420),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        tree.pack(side="left", fill="both", expand=True)

        detail = ttk.Frame(body, style="Panel.TFrame", padding=16)
        detail.pack(side="right", fill="both", expand=True, padx=(16, 0))
        score_var = tk.StringVar(value="Selecione uma campanha.")
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
                    risk["level"],
                    notes[0] if notes else "",
                ),
            )

        def show_detail(_event: object | None = None) -> None:
            if not tree.selection():
                return
            campaign_id = int(tree.item(tree.selection()[0], "values")[0])
            risk = risk_by_id[campaign_id]
            score_var.set(f"{risk['score']}% - {risk['level'].upper()}")
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
                canvas.create_text(20, 90, text="Nenhuma campanha criada.", anchor="w", fill="#6b7280")
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
        frame = self._screen("Histórico")
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="Atualizar", command=self.show_history).pack(side="left")
        ttk.Button(top, text="Abrir link manual", command=lambda: open_action()).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Números já enviados", command=self.show_sent_numbers).pack(side="left", padx=(8, 0))
        columns = ("created_at", "campaign", "recipient", "phone", "status", "action", "error")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, heading, width in [
            ("created_at", "Data/hora", 150),
            ("campaign", "Campanha", 180),
            ("recipient", "Contato", 160),
            ("phone", "Número", 130),
            ("status", "Status", 110),
            ("action", "Ação manual", 160),
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
                    item["status"],
                    "Abrir WhatsApp" if item.get("action_url") else "",
                    item["error_message"],
                ),
            )
            if item.get("action_url"):
                action_urls[node] = str(item["action_url"])

        def open_action() -> None:
            if not tree.selection():
                messagebox.showwarning(APP_TITLE, "Selecione um registro com ação manual.")
                return
            url = action_urls.get(tree.selection()[0])
            if not url:
                messagebox.showinfo(APP_TITLE, "Este registro não possui link manual.")
                return
            self._open_external_link(url)

    def show_sent_numbers(self) -> None:
        window = tk.Toplevel(self)
        window.title("Números já enviados")
        window.geometry("780x460")
        window.transient(self)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        columns = ("phone", "name", "campaign", "status", "attempts", "last")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, heading, width in [
            ("phone", "Número", 130),
            ("name", "Contato", 160),
            ("campaign", "Campanha", 180),
            ("status", "Status", 120),
            ("attempts", "Tentativas", 80),
            ("last", "Último registro", 150),
        ]:
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        for item in campaigns.list_sent_numbers():
            tree.insert(
                "",
                "end",
                values=(
                    item["phone"],
                    item["recipient_name"],
                    item.get("campaign_name") or "",
                    item["status"],
                    item["attempts"],
                    item["last_sent_at"],
                ),
            )

    def show_settings(self) -> None:
        frame = self._screen("Configurações da conta/API")
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
        delivery_mode = tk.StringVar(value=config.delivery_mode)
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
        company_name = tk.StringVar(value=get_setting("company_name", "Mezzold"))
        internet_status = tk.StringVar(value="Conexão com internet: ainda não verificada.")

        ttk.Label(left, text="WhatsApp Business Cloud API", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        internet_panel = ttk.Frame(left, style="Panel.TFrame")
        internet_panel.pack(fill="x", pady=(8, 0))
        ttk.Label(
            internet_panel,
            text="É obrigatório estar conectado à internet para enviar, abrir links wa.me e usar a API.",
            style="Muted.TLabel",
            wraplength=520,
        ).pack(anchor="w")
        ttk.Label(internet_panel, textvariable=internet_status, style="Panel.TLabel").pack(side="left", pady=(8, 0))
        ttk.Button(internet_panel, text="Testar conexão", command=lambda: self._update_internet_status(internet_status)).pack(side="right", pady=(8, 0))
        mode_frame = ttk.Frame(left, style="Panel.TFrame")
        mode_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(mode_frame, text="Modo de envio", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(
            mode_frame,
            textvariable=delivery_mode,
            values=("official_api", "manual_assisted"),
            state="readonly",
        ).pack(fill="x")
        warning = (
            "manual_assisted não automatiza disparos: gera link wa.me e registra pendência manual. "
            "Qualquer automação fora da API oficial pode violar políticas e bloquear números."
        )
        ttk.Label(left, text=warning, style="Muted.TLabel", wraplength=430).pack(anchor="w", pady=(8, 0))
        for label, variable in [
            ("Token novo (em branco mantém o atual)", token),
            ("ID do número WhatsApp Business", phone_number_id),
            ("ID da conta/WABA", business_account_id),
            ("Webhook", webhook_url),
            ("Versão da Graph API", api_version),
            ("Template padrão aprovado", default_template),
            ("Idioma padrão", default_language),
        ]:
            self._entry(left, label, variable, show="*" if label.startswith("Token") else None).pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(left, text="Modo seguro: simular envio sem chamar a API", variable=dry_run).pack(anchor="w", pady=(14, 0))
        ttk.Checkbutton(left, text="Bloquear campanhas com risco crítico", variable=block_high_risk).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            left,
            text="Iniciar automaticamente com o Windows",
            variable=start_with_windows,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            left,
            text="Disparo inteligente: cadência variável e pausas conservadoras",
            variable=smart_send,
        ).pack(anchor="w", pady=(8, 0))
        smart_note = (
            "Exige pelo menos 3 mensagens diferentes por campanha. "
            "Não embaralha letras/palavras e não garante ausência de bloqueio."
        )
        ttk.Label(left, text=smart_note, style="Muted.TLabel", wraplength=430).pack(anchor="w", pady=(6, 0))

        ttk.Label(right, text="Conta, limites e produto", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        for label, variable in [
            ("Empresa", company_name),
            ("Intervalo entre envios (segundos)", interval),
            ("Limite diário de envios", daily_limit),
        ]:
            self._entry(right, label, variable).pack(fill="x", pady=(10, 0))

        ttk.Label(right, text="Disparo inteligente", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(18, 0))
        smart_grid = ttk.Frame(right, style="Panel.TFrame")
        smart_grid.pack(fill="x")
        smart_fields = [
            ("Intervalo mínimo (s)", smart_min_interval),
            ("Intervalo máximo (s)", smart_max_interval),
            ("Pausa a cada X envios", smart_pause_every),
            ("Pausa mínima (s)", smart_pause_min),
            ("Pausa máxima (s)", smart_pause_max),
            ("Limite diário inteligente", smart_daily_limit),
            ("Janela máxima (min)", smart_max_session),
        ]
        for index, (label, variable) in enumerate(smart_fields):
            holder = ttk.Frame(smart_grid, style="Panel.TFrame")
            holder.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 0), pady=(10, 0))
            smart_grid.columnconfigure(index % 2, weight=1)
            self._entry(holder, label, variable).pack(fill="x")

        license_data = self._load_license()
        license_key = tk.StringVar(value=str(license_data.get("license_key", "")))
        license_plan = tk.StringVar(value=str(license_data.get("plan_name", "")))
        license_until = tk.StringVar(value=str(license_data.get("valid_until", "")))
        ttk.Label(right, text="Licença", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(20, 0))
        for label, variable in [
            ("Chave de licença", license_key),
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
                    delivery_mode=delivery_mode.get(),
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
                self._save_license(license_key.get(), license_plan.get(), license_until.get())
            except (ValueError, RuntimeError, whatsapp.WhatsAppAPIError) as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            messagebox.showinfo(APP_TITLE, "Configurações salvas com confirmação em duas etapas.")

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
            ("Salvar alterações", save, "Accent.TButton"),
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
            "Produto desktop local com SQLite, opt-in, blacklist, templates aprovados, logs e bloqueio de risco."
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
            "smart_min_interval_seconds": self._positive_int(min_interval, "Intervalo mínimo", 1),
            "smart_max_interval_seconds": self._positive_int(max_interval, "Intervalo máximo", 1),
            "smart_pause_every": self._positive_int(pause_every, "Pausa a cada X envios", 1),
            "smart_pause_min_seconds": self._positive_int(pause_min, "Pausa mínima", 0),
            "smart_pause_max_seconds": self._positive_int(pause_max, "Pausa máxima", 0),
            "smart_daily_limit": self._positive_int(daily_limit, "Limite diário inteligente", 1),
            "smart_max_session_minutes": self._positive_int(max_session, "Janela máxima", 5),
        }
        if values["smart_max_interval_seconds"] < values["smart_min_interval_seconds"]:
            raise ValueError("O intervalo máximo precisa ser maior ou igual ao mínimo.")
        if values["smart_pause_max_seconds"] < values["smart_pause_min_seconds"]:
            raise ValueError("A pausa máxima precisa ser maior ou igual à mínima.")
        set_setting("smart_send_enabled", "1" if enabled else "0")
        for key, value in values.items():
            set_setting(key, str(value))

    def _positive_int(self, value: str, label: str, minimum: int) -> int:
        try:
            parsed = int(float(value.replace(",", ".")))
        except ValueError as exc:
            raise ValueError(f"{label} precisa ser um número.") from exc
        if parsed < minimum:
            raise ValueError(f"{label} precisa ser maior ou igual a {minimum}.")
        return parsed

    def _update_internet_status(self, status_var: tk.StringVar) -> None:
        status_var.set("Verificando conexão...")
        self.update_idletasks()
        if network.has_internet():
            status_var.set("Conexão com internet: OK.")
        else:
            status_var.set("Conexão com internet: indisponível.")

    def _require_internet(self) -> bool:
        if network.has_internet():
            return True
        messagebox.showerror(
            APP_TITLE,
            "É necessário estar conectado à internet para enviar campanhas ou abrir links do WhatsApp.",
        )
        return False

    def _open_external_link(self, url: str) -> None:
        if self._require_internet():
            webbrowser.open(url)

    def _confirm_settings_save(self) -> bool:
        if not self.current_user:
            messagebox.showerror(APP_TITLE, "Faça login novamente para salvar configurações.")
            return False

        code = f"{secrets.randbelow(900000) + 100000}"
        dialog = tk.Toplevel(self)
        dialog.title("Confirmar alterações")
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
            text="Confirmação em duas etapas",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        ttk.Label(
            panel,
            text="Para salvar configurações sensíveis, informe sua senha e digite o código abaixo.",
            wraplength=360,
        ).pack(anchor="w", pady=(8, 10))
        ttk.Label(panel, text=f"Código: {code}", font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(0, 10))
        self._entry(panel, "Senha atual", password, show="*").pack(fill="x", pady=(0, 10))
        self._entry(panel, "Digite o código", typed_code).pack(fill="x", pady=(0, 14))

        def confirm() -> None:
            user = auth.authenticate(self.current_user.username, password.get())
            if not user:
                messagebox.showerror(APP_TITLE, "Senha inválida.", parent=dialog)
                return
            if typed_code.get().strip() != code:
                messagebox.showerror(APP_TITLE, "Código inválido.", parent=dialog)
                return
            result["ok"] = True
            dialog.destroy()

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Confirmar e salvar", style="Accent.TButton", command=confirm).pack(side="right", padx=(0, 8))

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
                    item["status"],
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
    ) -> None:
        if campaign_id in self.running_events:
            messagebox.showinfo(APP_TITLE, "Esta campanha já está em envio.")
            return
        if not network.has_internet():
            if internet_alert:
                self._require_internet()
            else:
                self._set_status("Campanhas aguardando conexão com a internet.")
            return

        risk = compliance.refresh_campaign_risk(campaign_id)
        if interactive and int(risk["score"]) >= 50:
            notes = "\n".join(f"- {note}" for note in risk["notes"][:4])
            proceed = messagebox.askyesno(
                APP_TITLE,
                f"Risco desta campanha: {risk['score']}% ({risk['level']}).\n\n{notes}\n\nContinuar mesmo assim?",
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
                totals = campaigns.send_campaign(campaign_id, progress_callback=progress, stop_event=event)
                done = (
                    f"Campanha #{campaign_id}: enviados {totals['enviado']}, "
                    f"simulados {totals['simulado']}, manuais {totals['pendente_manual']}, "
                    f"falhas {totals['falhou']}."
                )
                self.after(0, lambda: self._set_status(done))
            except campaigns.CampaignError as exc:
                self.after(0, lambda: messagebox.showerror(APP_TITLE, str(exc)))
            finally:
                self.running_events.pop(campaign_id, None)
                self.after(0, self._refresh_current_screen)

        threading.Thread(target=worker, daemon=True).start()
        self._set_status(f"Campanha #{campaign_id} em envio.")

    def _send_due_campaigns(self, quiet: bool = False) -> None:
        due = campaigns.get_due_campaigns()
        if not due:
            if not quiet:
                self._set_status("Nenhuma campanha agendada para agora.")
            return
        for campaign in due:
            self._start_campaign_thread(int(campaign["id"]), interactive=False, internet_alert=not quiet)

    def _resume_interrupted_campaigns(self) -> None:
        resumable = [item for item in campaigns.get_resumable_campaigns() if campaigns.has_pending_contacts(int(item["id"]))]
        if not resumable:
            return
        if not network.has_internet():
            self._set_status("Há campanhas interrompidas aguardando conexão com a internet.")
            return
        for campaign in resumable:
            self._start_campaign_thread(int(campaign["id"]), interactive=False, internet_alert=False)
        self._set_status(f"Retomando {len(resumable)} campanha(s) em andamento.")

    def _scheduler_tick(self) -> None:
        if self.current_user:
            self._send_due_campaigns(quiet=True)
            self.after(60000, self._scheduler_tick)

    def _refresh_current_screen(self) -> None:
        if self.current_screen == "Dashboard":
            self.show_dashboard()
        elif self.current_screen == "Agendar envio":
            self.show_schedule()
        elif self.current_screen == "Risco de banimento":
            self.show_risk()
        elif self.current_screen == "Histórico":
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
