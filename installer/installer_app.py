from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "Mezzold Connect"


def bundled_exe_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "Mezzold Connect.exe"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1] / "dist" / "Mezzold Connect.exe"


def target_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / APP_NAME


def target_exe_path() -> Path:
    return target_dir() / "Mezzold Connect.exe"


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
            "Nao foi possivel substituir o aplicativo. Feche o Mezzold Connect e o envio em segundo plano, "
            "depois execute o instalador novamente."
        ) from exc
    finally:
        temp_target.unlink(missing_ok=True)


def run_powershell(script: str, env: dict[str, str] | None = None) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        env=merged_env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def create_shortcuts(target_exe: Path) -> None:
    script = r"""
$appName = "Mezzold Connect"
$targetExe = $env:MEZZOLD_TARGET_EXE
$targetDir = Split-Path $targetExe
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
$startMenuShortcut = Join-Path $startMenuDir "$appName.lnk"
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @($desktopShortcut, $startMenuShortcut)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetExe
    $shortcut.WorkingDirectory = $targetDir
    $shortcut.IconLocation = $targetExe
    $shortcut.Save()
}
$uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenuDir "Desinstalar Mezzold Connect.lnk"))
$uninstallShortcut.TargetPath = "powershell.exe"
$uninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$targetDir\uninstall.ps1`""
$uninstallShortcut.WorkingDirectory = $targetDir
$uninstallShortcut.Save()
"""
    run_powershell(script, {"MEZZOLD_TARGET_EXE": str(target_exe)})


def write_uninstaller(app_dir: Path) -> None:
    uninstall_script = r'''
$ErrorActionPreference = "Stop"
$appName = "Mezzold Connect"
$targetDir = Join-Path $env:LOCALAPPDATA $appName
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
Get-Process "Mezzold Connect" -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-ItemProperty -Path $runKey -Name $appName -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $startMenuDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $targetDir -Recurse -Force -ErrorAction SilentlyContinue
'''
    (app_dir / "uninstall.ps1").write_text(uninstall_script, encoding="utf-8")


def set_startup(enabled: bool, target_exe: Path) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{target_exe}" --background')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def install(enable_startup: bool, open_after_install: bool) -> Path:
    source = bundled_exe_path()
    if not source.exists():
        raise FileNotFoundError(f"Executavel nao encontrado: {source}")

    app_dir = target_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    target_exe = target_exe_path()
    replace_executable_safely(source, target_exe)
    write_uninstaller(app_dir)
    create_shortcuts(target_exe)
    set_startup(enable_startup, target_exe)

    if open_after_install:
        subprocess.Popen([str(target_exe)], cwd=str(app_dir))

    return target_exe


class InstallerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} Setup")
        self.geometry("460x300")
        self.resizable(False, False)
        self.configure(background="#f6f7fb")
        self.startup = tk.BooleanVar(value=True)
        self.open_after = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Pronto para instalar ou atualizar.")

        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        ttk.Label(
            frame,
            text="Instala ou atualiza o aplicativo, cria atalhos e preserva os dados locais do usuario.",
            wraplength=400,
        ).pack(anchor="w", pady=(8, 18))
        ttk.Label(frame, text=f"Pasta: {target_dir()}", wraplength=400).pack(anchor="w", pady=(0, 14))
        ttk.Checkbutton(
            frame,
            text="Iniciar envios em segundo plano com o Windows",
            variable=self.startup,
        ).pack(anchor="w")
        ttk.Checkbutton(
            frame,
            text="Abrir Mezzold Connect apos instalar",
            variable=self.open_after,
        ).pack(anchor="w", pady=(4, 18))
        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="Instalar/Atualizar", command=self.install_clicked).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left", padx=(8, 0))

    def install_clicked(self) -> None:
        try:
            self.status.set("Instalando...")
            self.update_idletasks()
            target = install(self.startup.get(), self.open_after.get())
            self.status.set(f"Instalado em {target}")
            messagebox.showinfo(APP_NAME, "Mezzold Connect instalado ou atualizado com sucesso.")
        except Exception as exc:
            self.status.set("Falha na instalacao.")
            messagebox.showerror(APP_NAME, str(exc))


if __name__ == "__main__":
    InstallerApp().mainloop()
