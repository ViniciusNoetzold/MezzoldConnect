from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

import network
from database import APP_TITLE


class ConnectionScreenMixin:
    def show_whatsapp_connection(self) -> None:
        import webbrowser

        frame = self._screen("Conexão WhatsApp")

        internet_var = tk.StringVar(value="Verificando internet...")
        status_var = tk.StringVar(value="Mantenha o WhatsApp aberto no computador durante os envios.")

        info_panel = ttk.Frame(frame, style="Panel.TFrame", padding=20)
        info_panel.pack(fill="x", pady=(0, 12))
        ttk.Label(
            info_panel,
            text="Status da conexão",
            style="Panel.TLabel",
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")
        ttk.Label(info_panel, textvariable=internet_var, style="Panel.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Label(info_panel, textvariable=status_var, style="Muted.TLabel", wraplength=760).pack(
            anchor="w", pady=(4, 0)
        )

        steps_panel = ttk.Frame(frame, style="Panel.TFrame", padding=20)
        steps_panel.pack(fill="x", pady=(0, 12))
        ttk.Label(
            steps_panel,
            text="Como conectar o WhatsApp:",
            style="Panel.TLabel",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        for step in [
            "1. Clique em 'Abrir WhatsApp Web' abaixo.",
            "2. Na página que abrir, escaneie o QR Code com o celular (se necessário).",
            "3. Mantenha o WhatsApp Web ou Desktop aberto durante todo o envio.",
            "4. Clique em 'Verificar internet' para confirmar a conexão antes de iniciar uma campanha.",
        ]:
            ttk.Label(steps_panel, text=step, style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(4, 0))

        def open_web() -> None:
            webbrowser.open("https://web.whatsapp.com")
            status_var.set("WhatsApp Web aberto no navegador. Escaneie o QR Code se necessário.")

        def check_internet() -> None:
            internet_var.set("Verificando internet...")

            def worker() -> None:
                ok = network.has_internet()
                self.after(
                    0,
                    lambda: internet_var.set(
                        "Internet: conectada."
                        if ok
                        else "Internet: SEM CONEXAO. Verifique o Wi-Fi ou cabo de rede."
                    ),
                )

            threading.Thread(target=worker, daemon=True).start()

        ttk.Button(actions, text="Abrir WhatsApp Web", style="Accent.TButton", command=open_web).pack(side="left")
        ttk.Button(actions, text="Verificar internet", command=check_internet).pack(side="left", padx=(8, 0))

        check_internet()
