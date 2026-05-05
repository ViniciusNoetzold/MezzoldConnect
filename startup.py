from __future__ import annotations

import os
import sys
from pathlib import Path


APP_RUN_KEY = "Mezzold Connect"


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    main_path = Path(__file__).resolve().parent / "main.py"
    return f'"{sys.executable}" "{main_path}" --background'


def is_supported() -> bool:
    return os.name == "nt"


def is_startup_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _ = winreg.QueryValueEx(key, APP_RUN_KEY)
        return str(value) == startup_command()
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    if not is_supported():
        raise RuntimeError("Iniciar junto com o computador só funciona no Windows.")

    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_RUN_KEY, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_RUN_KEY)
            except FileNotFoundError:
                pass
