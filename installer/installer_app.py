"""Instalador Windows do Mezzold Connect v2.

O instalador não mantém uma segunda cópia do schema. O próprio executável cria
ou migra o banco, exatamente com o mesmo código usado em produção.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "Mezzold Connect"
APP_VERSION = "2.1.1"
INSTALL_ROOT = Path("C:/MezzoldConnect")
APP_DIR = INSTALL_ROOT / "app"
DATA_DIR = INSTALL_ROOT / "data"
SCRIPTS_DIR = INSTALL_ROOT / "scripts"
TARGET_EXE = APP_DIR / "MezzoldConnect.exe"


def bundled_exe_path() -> Path:
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidate = Path(bundle_dir) / "MezzoldConnect.exe"
            if candidate.is_file():
                return candidate
    return Path(__file__).resolve().parents[1] / "dist" / "MezzoldConnect.exe"


def ensure_structure() -> None:
    for directory in (
        APP_DIR,
        DATA_DIR,
        SCRIPTS_DIR,
        DATA_DIR / "media",
        DATA_DIR / "imports",
        DATA_DIR / "exports",
        DATA_DIR / "backups",
        DATA_DIR / "logs",
    ):
        directory.mkdir(parents=True, exist_ok=True)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_executable_safely(source: Path, target: Path) -> None:
    """Install/update the binary atomically and retain one rollback copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".new")
    rollback = target.with_suffix(target.suffix + ".bak")
    temporary.unlink(missing_ok=True)
    shutil.copy2(source, temporary)
    if file_sha256(source) != file_sha256(temporary):
        temporary.unlink(missing_ok=True)
        raise RuntimeError("A cópia do executável falhou na verificação SHA-256.")
    if target.exists():
        rollback.unlink(missing_ok=True)
        os.replace(target, rollback)
    try:
        os.replace(temporary, target)
    except Exception:
        if rollback.exists() and not target.exists():
            os.replace(rollback, target)
        raise


def stop_running_application() -> None:
    """Close installed app processes before replacing the Windows executable."""
    if os.name != "nt" or not TARGET_EXE.exists():
        return
    options: dict[str, object] = {
        "capture_output": True,
        "text": True,
    }
    options["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        ["taskkill.exe", "/IM", TARGET_EXE.name, "/T", "/F"],
        **options,
    )
    if result.returncode not in {0, 1, 128}:
        detail = (result.stderr or result.stdout or "erro desconhecido").strip()
        raise RuntimeError(f"Não foi possível encerrar a versão em execução: {detail}")
    # Windows can retain the image mapping briefly after taskkill returns.
    time.sleep(0.4)


def _app_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["MEZZOLD_DATA_DIR"] = str(DATA_DIR)
    environment["MEZZOLD_DB_PATH"] = str(DATA_DIR / "mezzold_connect.sqlite3")
    return environment


def run_app_cli(*arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    options: dict[str, object] = {
        "cwd": str(APP_DIR),
        "env": _app_environment(),
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run([str(TARGET_EXE), *arguments], **options)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "erro desconhecido").strip()
        raise RuntimeError(f"Falha ao executar {' '.join(arguments)}: {detail}")
    return result


def initialize_database_file() -> None:
    """Initialize or migrate using the application schema and migration engine."""
    run_app_cli("--initialize-database")


def write_maintenance_scripts() -> None:
    backup_script = r'''@echo off
"C:\MezzoldConnect\app\MezzoldConnect.exe" --backup-database "C:\MezzoldConnect\data\backups"
if errorlevel 1 exit /b %errorlevel%
echo Backup concluido em C:\MezzoldConnect\data\backups
'''
    export_script = r'''@echo off
"C:\MezzoldConnect\app\MezzoldConnect.exe" --export-firebird "C:\MezzoldConnect\data\mezzold_connect_firebird.sql"
if errorlevel 1 exit /b %errorlevel%
echo Exportacao concluida em C:\MezzoldConnect\data\mezzold_connect_firebird.sql
'''
    open_data_script = r'''@echo off
explorer "C:\MezzoldConnect\data"
'''
    (SCRIPTS_DIR / "backup_banco.bat").write_text(backup_script, encoding="utf-8")
    (SCRIPTS_DIR / "exportar_dados_firebird_sql.bat").write_text(export_script, encoding="utf-8")
    (SCRIPTS_DIR / "abrir_pasta_dados.bat").write_text(open_data_script, encoding="utf-8")


def create_shortcuts() -> None:
    script = r'''
$appName = "Mezzold Connect"
$targetExe = "C:\MezzoldConnect\app\MezzoldConnect.exe"
$targetDir = "C:\MezzoldConnect\app"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($desktopShortcut)
$shortcut.TargetPath = $targetExe
$shortcut.WorkingDirectory = $targetDir
$shortcut.IconLocation = $targetExe
$shortcut.Save()
$menuShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "$appName.lnk"))
$menuShortcut.TargetPath = $targetExe
$menuShortcut.WorkingDirectory = $targetDir
$menuShortcut.IconLocation = $targetExe
$menuShortcut.Save()
$dataShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "Pasta de Dados e Banco.lnk"))
$dataShortcut.TargetPath = "explorer.exe"
$dataShortcut.Arguments = '"C:\MezzoldConnect\data"'
$dataShortcut.Save()
$uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "Desinstalar Mezzold Connect.lnk"))
$uninstallShortcut.TargetPath = "powershell.exe"
$uninstallShortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "C:\MezzoldConnect\uninstall.ps1"'
$uninstallShortcut.Save()
'''
    options: dict[str, object] = {"check": True}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        **options,
    )


def write_uninstaller() -> None:
    # Data is deliberately preserved. Only application files and shortcuts are removed.
    script = r'''
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
Remove-Item -LiteralPath "$installRoot\app" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$installRoot\scripts" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Aplicativo removido. Seus dados foram preservados em C:\MezzoldConnect\data."
'''
    (INSTALL_ROOT / "uninstall.ps1").write_text(script, encoding="utf-8")


def set_startup(enabled: bool) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{TARGET_EXE}" --minimized')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def run_installation(enable_startup: bool, open_after: bool) -> Path:
    source = bundled_exe_path()
    if not source.is_file():
        raise FileNotFoundError(f"Executável principal não encontrado: {source}")
    ensure_structure()
    previous_install = TARGET_EXE.exists()
    rollback = TARGET_EXE.with_suffix(TARGET_EXE.suffix + ".bak")
    failed_binary = TARGET_EXE.with_suffix(TARGET_EXE.suffix + ".failed")
    stop_running_application()
    replace_executable_safely(source, TARGET_EXE)
    try:
        # This performs the one-time v1 copy (when applicable), a pre-migration
        # backup, schema migration, integrity check and default settings insertion.
        initialize_database_file()
        run_app_cli("--export-firebird", str(DATA_DIR / "mezzold_connect_firebird.sql"))
    except Exception:
        failed_binary.unlink(missing_ok=True)
        if TARGET_EXE.exists():
            os.replace(TARGET_EXE, failed_binary)
        if previous_install and rollback.exists():
            os.replace(rollback, TARGET_EXE)
        raise
    write_maintenance_scripts()
    write_uninstaller()
    create_shortcuts()
    set_startup(enable_startup)
    if open_after:
        subprocess.Popen([str(TARGET_EXE)], cwd=str(APP_DIR), env=_app_environment())
    return TARGET_EXE


class InstallerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION} — Instalador")
        self.geometry("520x390")
        self.resizable(False, False)
        self.configure(background="#181824")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background="#181824", foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#181824", foreground="#38bdf8", font=("Segoe UI Semibold", 16))
        style.configure("TCheckbutton", background="#181824", foreground="#e2e8f0", font=("Segoe UI", 10))

        self.startup = tk.BooleanVar(value=True)
        self.open_after = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Pronto para instalar ou atualizar.")
        frame = tk.Frame(self, background="#181824", padx=24, pady=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{APP_NAME} v{APP_VERSION}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Instala o aplicativo e migra automaticamente um banco da v1 quando a v2 ainda "
                "não possui dados. Bancos existentes recebem backup e migração segura."
            ),
            wraplength=465,
        ).pack(anchor="w", pady=(8, 14))
        tk.Label(
            frame,
            text=(
                "Aplicativo: C:\\MezzoldConnect\\app\\MezzoldConnect.exe\n"
                "Dados preservados: C:\\MezzoldConnect\\data\n"
                "Backup pré-migração: C:\\MezzoldConnect\\data\\backups"
            ),
            justify="left",
            background="#232336",
            foreground="#94a3b8",
            padx=12,
            pady=10,
            font=("Consolas", 9),
        ).pack(fill="x", pady=(0, 14))
        ttk.Checkbutton(
            frame,
            text="Iniciar minimizado na bandeja com o Windows",
            variable=self.startup,
        ).pack(anchor="w", pady=(0, 4))
        ttk.Checkbutton(
            frame,
            text="Abrir Mezzold Connect ao finalizar",
            variable=self.open_after,
        ).pack(anchor="w", pady=(0, 14))
        ttk.Label(frame, textvariable=self.status, foreground="#38bdf8").pack(anchor="w", pady=(0, 12))
        actions = tk.Frame(frame, background="#181824")
        actions.pack(fill="x")
        tk.Button(
            actions,
            text="Instalar / Atualizar",
            command=self.install_clicked,
            bg="#0284c7",
            fg="white",
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=7,
            relief="flat",
        ).pack(side="left")
        tk.Button(
            actions,
            text="Cancelar",
            command=self.destroy,
            bg="#334155",
            fg="#e2e8f0",
            font=("Segoe UI", 10),
            padx=16,
            pady=7,
            relief="flat",
        ).pack(side="left", padx=(10, 0))

    def install_clicked(self) -> None:
        try:
            self.status.set("Copiando, migrando e validando os dados…")
            self.update_idletasks()
            run_installation(self.startup.get(), self.open_after.get())
            self.status.set("Instalação concluída com sucesso.")
            messagebox.showinfo(
                APP_NAME,
                "Mezzold Connect instalado e banco validado. Os dados ficam em "
                "C:\\MezzoldConnect\\data.",
            )
            self.destroy()
        except Exception as exc:
            self.status.set("Falha na instalação; os dados existentes foram preservados.")
            messagebox.showerror(APP_NAME, f"Erro: {exc}")


if __name__ == "__main__":
    InstallerApp().mainloop()
