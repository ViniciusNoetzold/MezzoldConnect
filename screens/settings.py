from __future__ import annotations

import secrets
import shutil
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import app_update
import auth
import network
import startup
import whatsapp
from database import APP_TITLE, APP_VERSION, DB_PATH, connect, get_setting, row_to_dict, set_setting


WHATSAPP_POLICY_URL = "https://www.whatsapp.com/legal/business-policy/"
META_CLOUD_API_URL = "https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview"
APP_UPDATES_URL = app_update.DEFAULT_DOWNLOAD_URL


class SettingsScreenMixin:
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def show_settings(self) -> None:
        return self._show_settings_center()

    def _show_settings_center(self) -> None:
        frame = self._screen("Configurações")
        frame = self._scrollable_frame(frame)
        config = whatsapp.load_config()

        header = ttk.Frame(frame, style="Panel.TFrame", padding=16)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text=f"{APP_TITLE} {APP_VERSION}", style="Panel.TLabel", font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(
            header,
            text=f"Banco local: {DB_PATH}\nAtualizações: verifique pelo manifesto configurado ou abra a página oficial de releases.",
            style="Muted.TLabel",
            wraplength=920,
        ).pack(anchor="w", pady=(6, 0))

        columns = ttk.Frame(frame)
        columns.pack(fill="both", expand=True)
        left = ttk.Frame(columns, style="Panel.TFrame", padding=16)
        right = ttk.Frame(columns, style="Panel.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        columns.columnconfigure(0, weight=1, uniform="settings")
        columns.columnconfigure(1, weight=1, uniform="settings")

        def section(parent: ttk.Frame, title: str, note: str = "") -> None:
            ttk.Label(parent, text=title, style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(18, 0))
            if note:
                ttk.Label(parent, text=note, style="Muted.TLabel", wraplength=500).pack(anchor="w", pady=(4, 0))

        token = tk.StringVar()
        phone_number_id = tk.StringVar(value=config.phone_number_id)
        business_account_id = tk.StringVar(value=config.business_account_id)
        webhook_url = tk.StringVar(value=config.webhook_url)
        api_version = tk.StringVar(value=config.api_version)
        default_template = tk.StringVar(value=config.default_template)
        default_language = tk.StringVar(value=config.default_language)
        company_name = tk.StringVar(value=get_setting("company_name", "Mezzold"))
        interval = tk.StringVar(value=str(config.send_interval_seconds))
        daily_limit = tk.StringVar(value=str(config.daily_send_limit))
        delivery_modes = {
            "Envio oficial pela Meta": "official_api",
            "Modo manual com link": "manual_assisted",
        }
        delivery_mode_labels = {value: label for label, value in delivery_modes.items()}
        delivery_mode = tk.StringVar(value=delivery_mode_labels.get(config.delivery_mode, "Envio oficial pela Meta"))
        dry_run = tk.BooleanVar(value=config.dry_run)
        block_high_risk = tk.BooleanVar(value=get_setting("block_high_risk_campaigns", "1") == "1")
        smart_send = tk.BooleanVar(value=get_setting("smart_send_enabled", "0") == "1")
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
        internet_status = tk.StringVar(value="Internet: ainda não testada.")
        start_with_windows = tk.BooleanVar(value=startup.is_startup_enabled())
        startup_status = "Disponível neste Windows." if startup.is_supported() else "Disponível apenas no Windows."

        theme_options = {"Claro": "light", "Escuro": "dark"}
        theme_labels = {value: label for label, value in theme_options.items()}
        theme = tk.StringVar(value=theme_labels.get(get_setting("app_theme", "light"), "Claro"))
        density_options = {"Compacta": "compact", "Normal": "normal", "Confortável": "comfortable"}
        density_labels = {value: label for label, value in density_options.items()}
        density = tk.StringVar(value=density_labels.get(get_setting("ui_density", "normal"), "Normal"))
        font_size = tk.StringVar(value=get_setting("ui_font_size", "10"))
        update_manifest_url = tk.StringVar(value=get_setting("app_update_manifest_url", ""))
        update_download_url = tk.StringVar(value=get_setting("app_update_download_url", APP_UPDATES_URL))
        update_channel = tk.StringVar(value=get_setting("app_update_channel", app_update.DEFAULT_CHANNEL))
        update_status = tk.StringVar(value="Pronto para verificar atualizações.")

        section(left, "Geral")
        self._entry(left, "Nome da empresa", company_name).pack(fill="x", pady=(10, 0))
        visual_grid = ttk.Frame(left, style="Panel.TFrame")
        visual_grid.pack(fill="x", pady=(10, 0))
        theme_holder = ttk.Frame(visual_grid, style="Panel.TFrame")
        theme_holder.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(theme_holder, text="Tema", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(theme_holder, textvariable=theme, values=tuple(theme_options.keys()), state="readonly").pack(fill="x")
        density_holder = ttk.Frame(visual_grid, style="Panel.TFrame")
        density_holder.grid(row=0, column=1, sticky="ew")
        ttk.Label(density_holder, text="Densidade", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(density_holder, textvariable=density, values=tuple(density_options.keys()), state="readonly").pack(fill="x")
        visual_grid.columnconfigure(0, weight=1)
        visual_grid.columnconfigure(1, weight=1)
        self._entry(left, "Tamanho da fonte (9 a 14)", font_size).pack(fill="x", pady=(10, 0))

        section(left, "Atualizações", "O app nunca substitui arquivos de dados. Sem manifesto configurado, o botão usa a página oficial de download.")
        ttk.Label(left, text=f"Versão atual: {APP_VERSION}", style="Panel.TLabel").pack(anchor="w", pady=(8, 0))
        self._entry(left, "URL do manifesto de atualização (opcional)", update_manifest_url).pack(fill="x", pady=(10, 0))
        self._entry(left, "Página de download", update_download_url).pack(fill="x", pady=(10, 0))
        self._entry(left, "Canal de atualização", update_channel).pack(fill="x", pady=(10, 0))
        ttk.Label(left, textvariable=update_status, style="Muted.TLabel", wraplength=500).pack(anchor="w", pady=(8, 0))

        license_data = self._load_license()
        license_key = tk.StringVar(value=str(license_data.get("license_key", "")))
        license_plan = tk.StringVar(value=str(license_data.get("plan_name", "")))
        license_until = tk.StringVar(value=str(license_data.get("valid_until", "")))
        section(left, "Licença")
        for label, variable in [
            ("Código da licença", license_key),
            ("Plano", license_plan),
            ("Validade", license_until),
        ]:
            self._entry(left, label, variable).pack(fill="x", pady=(10, 0))

        section(left, "Envio", "Configurações gerais usadas por campanhas e limites de segurança.")
        for label, variable in [
            ("Intervalo global de fallback (segundos)", interval),
            ("Máximo de envios por dia", daily_limit),
        ]:
            self._entry(left, label, variable).pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(left, text="Impedir envio quando o risco estiver muito alto", variable=block_high_risk).pack(anchor="w", pady=(12, 0))
        ttk.Checkbutton(left, text="Usar pausas automáticas entre mensagens", variable=smart_send).pack(anchor="w", pady=(8, 0))

        smart_grid = ttk.Frame(left, style="Panel.TFrame")
        smart_grid.pack(fill="x")
        for index, (label, variable) in enumerate([
            ("Espera mínima (s)", smart_min_interval),
            ("Espera máxima (s)", smart_max_interval),
            ("Pausa a cada X envios", smart_pause_every),
            ("Pausa curta mínima (s)", smart_pause_min),
            ("Pausa curta máxima (s)", smart_pause_max),
            ("Máximo diário neste modo", smart_daily_limit),
            ("Tempo máximo seguido (min)", smart_max_session),
        ]):
            holder = ttk.Frame(smart_grid, style="Panel.TFrame")
            holder.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 0), pady=(10, 0))
            smart_grid.columnconfigure(index % 2, weight=1)
            self._entry(holder, label, variable).pack(fill="x")

        section(right, "WhatsApp / Meta / Manual")
        ttk.Label(
            right,
            text="O token é protegido pela DPAPI no Windows e nunca é exibido aqui. Deixe em branco para manter o token atual.",
            style="Muted.TLabel",
            wraplength=500,
        ).pack(anchor="w", pady=(4, 0))
        token_state = "Token: configurado e oculto." if config.token or get_setting("whatsapp_token_protected", "") else "Token: ainda não configurado."
        ttk.Label(right, text=token_state, style="Panel.TLabel").pack(anchor="w", pady=(8, 0))
        internet_panel = ttk.Frame(right, style="Panel.TFrame")
        internet_panel.pack(fill="x", pady=(10, 0))
        ttk.Label(internet_panel, textvariable=internet_status, style="Panel.TLabel").pack(side="left")
        ttk.Button(internet_panel, text="Testar internet", command=lambda: self._update_internet_status(internet_status)).pack(side="right")
        ttk.Label(right, text="Como o app deve enviar", style="Panel.TLabel").pack(anchor="w", pady=(10, 4))
        ttk.Combobox(right, textvariable=delivery_mode, values=tuple(delivery_modes.keys()), state="readonly").pack(fill="x")
        for label, variable in [
            ("Token da Meta (opcional)", token),
            ("ID do número no WhatsApp Business", phone_number_id),
            ("ID da conta empresarial da Meta", business_account_id),
            ("Webhook", webhook_url),
            ("Versão da API da Meta", api_version),
            ("Modelo aprovado padrão", default_template),
            ("Idioma padrão do modelo", default_language),
        ]:
            self._entry(right, label, variable, show="*" if label.startswith("Token") else None).pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(right, text="Modo teste: registrar sem enviar de verdade", variable=dry_run).pack(anchor="w", pady=(12, 0))

        section(right, "Inicialização com Windows")
        ttk.Label(right, text=startup_status, style="Muted.TLabel", wraplength=500).pack(anchor="w", pady=(4, 0))
        startup_check = ttk.Checkbutton(right, text="Começar sozinho quando ligar o computador", variable=start_with_windows)
        startup_check.pack(anchor="w", pady=(10, 0))
        if not startup.is_supported():
            startup_check.configure(state="disabled")

        section(right, "Aquecimento dos números")
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

        def save() -> None:
            try:
                parsed_font_size = min(max(self._positive_int(font_size.get(), "Tamanho da fonte", 9), 9), 14)
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
                set_setting("app_theme", theme_options.get(theme.get(), "light"))
                set_setting("ui_font_size", str(parsed_font_size))
                set_setting("ui_density", density_options.get(density.get(), "normal"))
                set_setting("app_update_manifest_url", update_manifest_url.get().strip())
                set_setting("app_update_download_url", update_download_url.get().strip() or APP_UPDATES_URL)
                set_setting("app_update_channel", update_channel.get().strip() or app_update.DEFAULT_CHANNEL)
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
                self._save_rampup_settings(rampup_min_interval.get(), rampup_max_interval.get(), rampup_daily_floor.get())
                self._save_license(license_key.get(), license_plan.get(), license_until.get())
            except (ValueError, RuntimeError, whatsapp.WhatsAppAPIError) as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
            self._configure_style()
            messagebox.showinfo(APP_TITLE, "Configurações salvas.")
            self.show_settings()

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

        def check_updates() -> None:
            update_status.set("Verificando atualizações...")
            if update_button is not None:
                update_button.configure(state="disabled")
            manifest_url = update_manifest_url.get().strip()
            download_url = update_download_url.get().strip() or APP_UPDATES_URL
            channel = update_channel.get().strip() or app_update.DEFAULT_CHANNEL

            def worker() -> None:
                result = app_update.check_for_updates(
                    APP_VERSION,
                    manifest_url,
                    download_url=download_url,
                    channel=channel,
                )
                self.after(0, lambda: finish_update_check(result))

            threading.Thread(target=worker, daemon=True).start()

        def finish_update_check(result: app_update.UpdateCheckResult) -> None:
            try:
                if update_button is not None:
                    update_button.configure(state="normal")
            except tk.TclError:
                return

            if result.status == "no_manifest":
                update_status.set("Nenhum manifesto remoto configurado.")
                if messagebox.askyesno(
                    APP_TITLE,
                    "Ainda não há uma fonte remota de versão configurada.\n\nAbrir a página oficial de download?",
                ):
                    self._open_external_link(result.download_url)
                return

            if result.status == "error":
                update_status.set("Não consegui verificar atualizações.")
                if messagebox.askyesno(
                    APP_TITLE,
                    f"Não consegui consultar o manifesto de atualização.\n\nDetalhe: {result.error}\n\nAbrir a página de download?",
                ):
                    self._open_external_link(result.download_url)
                return

            if not result.has_update:
                update_status.set(f"Você já está na versão mais recente ({APP_VERSION}).")
                messagebox.showinfo(APP_TITLE, f"Você já está na versão mais recente ({APP_VERSION}).")
                return

            update_status.set(f"Nova versão disponível: {result.latest_version}.")
            notes = f"\n\nNotas:\n{result.release_notes[:700]}" if result.release_notes else ""
            if messagebox.askyesno(
                APP_TITLE,
                (
                    f"Há uma nova versão do {APP_TITLE}.\n\n"
                    f"Versão atual: {result.current_version}\n"
                    f"Nova versão: {result.latest_version}"
                    f"{notes}\n\n"
                    "A atualização automática segura ainda não está habilitada nesta versão. "
                    "Vou abrir a página ou instalador correto para você atualizar sem alterar seus dados locais.\n\n"
                    "Abrir agora?"
                ),
            ):
                self._open_external_link(result.download_url)

        actions = ttk.Frame(right, style="Panel.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        update_button: ttk.Button | None = None
        for index, (label, command, style_name) in enumerate([
            ("Salvar configurações", save, "Accent.TButton"),
            ("Criar backup", backup, "TButton"),
            ("Verificar atualizações", check_updates, "TButton"),
            ("Política oficial do WhatsApp", lambda: self._open_external_link(WHATSAPP_POLICY_URL), "TButton"),
            ("Documentação Cloud API", lambda: self._open_external_link(META_CLOUD_API_URL), "TButton"),
        ]):
            button = ttk.Button(actions, text=label, command=command, style=style_name)
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 0), pady=(0, 8))
            if label == "Verificar atualizações":
                update_button = button
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

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

