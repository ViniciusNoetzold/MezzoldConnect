from __future__ import annotations

import os
import sys
from pathlib import Path


APP_RUN_KEY = "Mezzold Connect"
_FLAG_BACKGROUND = "--background"
_FLAG_MINIMIZED = "--minimized"


def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_path = Path(__file__).resolve().parent / "main.py"
    return f'"{sys.executable}" "{main_path}"'


def startup_command() -> str:
    return f"{_exe_path()} {_FLAG_BACKGROUND}"


def startup_command_minimized() -> str:
    return f"{_exe_path()} {_FLAG_MINIMIZED}"


def is_supported() -> bool:
    return os.name == "nt"


def _current_startup_value() -> str:
    if not is_supported():
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _ = winreg.QueryValueEx(key, APP_RUN_KEY)
        return str(value)
    except (FileNotFoundError, OSError):
        return ""


def is_startup_enabled() -> bool:
    return _current_startup_value() in (startup_command(), startup_command_minimized())


def is_startup_minimized() -> bool:
    return _current_startup_value() == startup_command_minimized()


def set_startup_enabled(enabled: bool, minimized: bool = False) -> None:
    if not is_supported():
        raise RuntimeError("Iniciar junto com o computador só funciona no Windows.")

    import winreg
    command = startup_command_minimized() if enabled and minimized else startup_command()

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_RUN_KEY, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_RUN_KEY)
            except FileNotFoundError:
                pass


def enable_startup(minimized: bool = False) -> None:
    set_startup_enabled(True, minimized=minimized)


def disable_startup() -> None:
    set_startup_enabled(False)
