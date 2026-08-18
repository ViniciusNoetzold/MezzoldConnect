# -*- coding: utf-8 -*-
"""
Instalador Oficial do Mezzold Connect V2
Cria estrutura no disco C:\MezzoldConnect, banco de dados, atalhos e ferramentas de manutenção/Firebird.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME = "Mezzold Connect"
APP_VERSION = "2.0.0"
INSTALL_ROOT = Path("C:/MezzoldConnect")
APP_DIR = INSTALL_ROOT / "app"
DATA_DIR = INSTALL_ROOT / "data"
SCRIPTS_DIR = INSTALL_ROOT / "scripts"
TARGET_EXE = APP_DIR / "MezzoldConnect.exe"

def bundled_exe_path() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / "MezzoldConnect.exe"
            if cand.exists():
                return cand
    # Fallback to local dist
    return Path(__file__).resolve().parents[1] / "dist" / "MezzoldConnect.exe"

def ensure_structure():
    """Cria a estrutura completa de pastas no C:\MezzoldConnect"""
    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    (DATA_DIR / "media").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "imports").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "exports").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "backups").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)

def initialize_database_file():
    """Garante a criacao e tabelas iniciais do banco SQLite"""
    db_file = DATA_DIR / "mezzold_connect.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Criar schema inicial
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'cliente',
        must_change_password INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        last_login_at TEXT
    );

    CREATE TABLE IF NOT EXISTS contact_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        is_default INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        group_name TEXT,
        opt_in INTEGER NOT NULL DEFAULT 1,
        opt_in_source TEXT,
        opt_in_category TEXT,
        opt_in_at TEXT,
        consent_notes TEXT,
        notes TEXT,
        blacklisted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        message TEXT NOT NULL,
        message_category TEXT DEFAULT 'marketing',
        template_name TEXT,
        template_language TEXT DEFAULT 'pt_BR',
        folder_name TEXT,
        media_path TEXT,
        scheduled_at TEXT,
        delay_min_seconds INTEGER DEFAULT 60,
        delay_max_seconds INTEGER DEFAULT 120,
        delivery_mode TEXT DEFAULT 'official_api',
        status TEXT NOT NULL DEFAULT 'rascunho',
        risk_score INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS campaign_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        contact_id INTEGER NOT NULL,
        phone TEXT NOT NULL,
        recipient_name TEXT,
        status TEXT NOT NULL DEFAULT 'pendente',
        attempts INTEGER DEFAULT 0,
        last_error TEXT,
        sent_at TEXT,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS campaign_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        campaign_name TEXT,
        recipient_name TEXT,
        phone TEXT NOT NULL,
        status TEXT NOT NULL,
        delivery_mode TEXT,
        action_url TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS warmup_numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        phone TEXT NOT NULL UNIQUE,
        phone_number_id TEXT,
        provider TEXT DEFAULT 'oficial',
        status TEXT DEFAULT 'testing',
        quality_rating TEXT DEFAULT 'unknown',
        health_score INTEGER DEFAULT 85,
        messaging_limit TEXT DEFAULT '250',
        daily_target INTEGER DEFAULT 20,
        max_daily_target INTEGER DEFAULT 500,
        current_daily_target INTEGER DEFAULT 20,
        sent_today INTEGER DEFAULT 0,
        rest_start TEXT DEFAULT '00:00',
        rest_end TEXT DEFAULT '07:00',
        active INTEGER DEFAULT 1,
        ready_for_campaigns INTEGER DEFAULT 0,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS warmup_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number_id INTEGER,
        number_name TEXT,
        recipient_name TEXT,
        phone TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """
    conn.executescript(schema)
    
    # Criar pasta padrao Importados
    conn.execute("INSERT OR IGNORE INTO contact_folders (name, is_default) VALUES ('Importados', 1);")
    conn.commit()
    conn.close()

def write_maintenance_scripts():
    """Gera scripts utilitarios no C:\MezzoldConnect\scripts"""
    # 1. Backup script
    backup_bat = r'''@echo off
set "TIMESTAMP=%DATE:/=-%_%TIME::=-%"
set "TIMESTAMP=%TIMESTAMP: =0%"
copy "C:\MezzoldConnect\data\mezzold_connect.sqlite3" "C:\MezzoldConnect\data\backups\backup_%TIMESTAMP%.db"
echo Backup realizado em C:\MezzoldConnect\data\backups\
pause
'''
    (SCRIPTS_DIR / "backup_banco.bat").write_text(backup_bat, encoding="latin1")

    # 2. Export Firebird / SQL script
    export_bat = r'''@echo off
echo Exportando banco de dados para SQL / Firebird...
python "C:\MezzoldConnect\scripts\export_firebird.py" "C:\MezzoldConnect\data\mezzold_connect.sqlite3" "C:\MezzoldConnect\data\mezzold_connect_firebird.sql"
echo Arquivo gerado em C:\MezzoldConnect\data\mezzold_connect_firebird.sql
pause
'''
    (SCRIPTS_DIR / "exportar_dados_firebird_sql.bat").write_text(export_bat, encoding="latin1")

    # 3. Open data folder
    open_data_bat = r'''@echo off
explorer "C:\MezzoldConnect\data"
'''
    (SCRIPTS_DIR / "abrir_pasta_dados.bat").write_text(open_data_bat, encoding="latin1")

    # Copy export_firebird.py to scripts
    cur_dir = Path(__file__).resolve().parent
    local_exp = cur_dir / "export_firebird.py"
    if local_exp.exists():
        shutil.copy2(local_exp, SCRIPTS_DIR / "export_firebird.py")

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def replace_executable_safely(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f"{target.name}.new")
    backup_target = target.with_name(f"{target.name}.bak")

    try:
        temp_target.unlink(missing_ok=True)
        shutil.copy2(source, temp_target)
        if file_sha256(source) != file_sha256(temp_target):
            raise RuntimeError("A copia do executavel falhou na verificacao de integridade.")

        if not target.exists():
            os.replace(temp_target, target)
            return

        backup_target.unlink(missing_ok=True)
        os.replace(target, backup_target)
        try:
            os.replace(temp_target, target)
        except Exception:
            if backup_target.exists() and not target.exists():
                os.replace(backup_target, target)
            raise
    except PermissionError as exc:
        raise RuntimeError(
            "Nao foi possivel substituir o aplicativo. Feche o Mezzold Connect e tente novamente."
        ) from exc
    finally:
        temp_target.unlink(missing_ok=True)

def create_shortcuts(target_exe: Path) -> None:
    script = r"""
$appName = "Mezzold Connect"
$targetExe = "C:\MezzoldConnect\app\MezzoldConnect.exe"
$targetDir = "C:\MezzoldConnect\app"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
$shell = New-Object -ComObject WScript.Shell

# Desktop shortcut
$shortcut = $shell.CreateShortcut($desktopShortcut)
$shortcut.TargetPath = $targetExe
$shortcut.WorkingDirectory = $targetDir
$shortcut.IconLocation = $targetExe
$shortcut.Save()

# Start menu shortcut
$smShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "$appName.lnk"))
$smShortcut.TargetPath = $targetExe
$smShortcut.WorkingDirectory = $targetDir
$smShortcut.IconLocation = $targetExe
$smShortcut.Save()

# Data Folder Shortcut
$dataShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "Pasta de Dados e Banco.lnk"))
$dataShortcut.TargetPath = "explorer.exe"
$dataShortcut.Arguments = "C:\MezzoldConnect\data"
$dataShortcut.Save()

# Uninstaller Shortcut
$uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "Desinstalar Mezzold Connect.lnk"))
$uninstallShortcut.TargetPath = "powershell.exe"
$uninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"C:\MezzoldConnect\uninstall.ps1`""
$uninstallShortcut.Save()
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

def write_uninstaller():
    uninstall_script = r'''
$ErrorActionPreference = "Stop"
$appName = "Mezzold Connect"
$installRoot = "C:\MezzoldConnect"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

Get-Process "MezzoldConnect" -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-ItemProperty -Path $runKey -Name $appName -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $startMenuDir -Recurse -Force -ErrorAction SilentlyContinue

# Preserva a pasta data se o usuario quiser manter dados
Remove-Item -LiteralPath "$installRoot\app" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$installRoot\scripts" -Recurse -Force -ErrorAction SilentlyContinue
'''
    (INSTALL_ROOT / "uninstall.ps1").write_text(uninstall_script, encoding="utf-8")

def set_startup(enabled: bool):
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{TARGET_EXE}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass

def run_installation(enable_startup: bool, open_after: bool) -> Path:
    source = bundled_exe_path()
    if not source.exists():
        raise FileNotFoundError(f"Executavel principal nao encontrado: {source}")

    ensure_structure()
    replace_executable_safely(source, TARGET_EXE)
    initialize_database_file()
    write_maintenance_scripts()
    write_uninstaller()
    create_shortcuts(TARGET_EXE)
    set_startup(enable_startup)

    # Executar script de compatibilidade Firebird para gerar schema inicial
    try:
        cur_dir = Path(__file__).resolve().parent
        exp_script = cur_dir / "export_firebird.py"
        if exp_script.exists():
            subprocess.run([sys.executable, str(exp_script), str(DATA_DIR / "mezzold_connect.sqlite3"), str(DATA_DIR / "mezzold_connect_firebird.sql")], creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass

    if open_after:
        subprocess.Popen([str(TARGET_EXE)], cwd=str(APP_DIR))

    return TARGET_EXE

class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION} - Instalador")
        self.geometry("500x360")
        self.resizable(False, False)
        self.configure(background="#181824")

        # Custom Styling
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TLabel", background="#181824", foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#181824", foreground="#38bdf8", font=("Segoe UI Semibold", 16))
        style.configure("TCheckbutton", background="#181824", foreground="#e2e8f0", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"))

        self.startup = tk.BooleanVar(value=True)
        self.open_after = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Pronto para instalar em C:\\MezzoldConnect.")

        frame = tk.Frame(self, background="#181824", padx=24, pady=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"{APP_NAME} v{APP_VERSION}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Instala a aplicacao no disco C:\\MezzoldConnect, estrutura o banco de dados com compatibilidade Firebird/SQL e cria todos os atalhos.",
            wraplength=450,
        ).pack(anchor="w", pady=(8, 14))

        info_box = tk.Label(
            frame,
            text="Local: C:\\MezzoldConnect\nBanco: C:\\MezzoldConnect\\data\\mezzold_connect.sqlite3\nExport Firebird: C:\\MezzoldConnect\\data\\mezzold_connect_firebird.sql",
            justify="left",
            background="#232336",
            foreground="#94a3b8",
            padx=12,
            pady=8,
            font=("Consolas", 9)
        )
        info_box.pack(fill="x", pady=(0, 14))

        ttk.Checkbutton(
            frame,
            text="Iniciar automaticamente com o Windows",
            variable=self.startup,
        ).pack(anchor="w", pady=(0, 4))
        
        ttk.Checkbutton(
            frame,
            text="Abrir Mezzold Connect ao finalizar a instalacao",
            variable=self.open_after,
        ).pack(anchor="w", pady=(0, 14))

        ttk.Label(frame, textvariable=self.status, foreground="#38bdf8").pack(anchor="w", pady=(0, 12))

        actions = tk.Frame(frame, background="#181824")
        actions.pack(fill="x")
        
        btn_install = tk.Button(
            actions,
            text="Instalar Agora",
            command=self.install_clicked,
            bg="#0284c7",
            fg="white",
            activebackground="#0369a1",
            activeforeground="white",
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=6,
            relief="flat",
            cursor="hand2"
        )
        btn_install.pack(side="left")

        btn_cancel = tk.Button(
            actions,
            text="Cancelar",
            command=self.destroy,
            bg="#334155",
            fg="#e2e8f0",
            activebackground="#475569",
            activeforeground="white",
            font=("Segoe UI", 10),
            padx=16,
            pady=6,
            relief="flat",
            cursor="hand2"
        )
        btn_cancel.pack(side="left", padx=(10, 0))

    def install_clicked(self):
        try:
            self.status.set("Instalando e estruturando C:\\MezzoldConnect...")
            self.update_idletasks()
            target = run_installation(self.startup.get(), self.open_after.get())
            self.status.set("Instalado com sucesso!")
            messagebox.showinfo(
                APP_NAME,
                f"Mezzold Connect v{APP_VERSION} instalado com sucesso!\n\n"
                f"Pasta: C:\\MezzoldConnect\n"
                f"Banco: C:\\MezzoldConnect\\data\\mezzold_connect.sqlite3\n\n"
                "Atalhos criados na Área de Trabalho e no Menu Iniciar."
            )
            self.destroy()
        except Exception as exc:
            self.status.set("Falha na instalacao.")
            messagebox.showerror(APP_NAME, f"Erro: {str(exc)}")

if __name__ == "__main__":
    InstallerApp().mainloop()