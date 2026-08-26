"""Windows system-tray integration for the Flet desktop window."""
from __future__ import annotations

import threading
from typing import Any

import app_log
from runtime import app_runtime


_TRAY_AVAILABLE = False
try:
    import pystray  # type: ignore[import-not-found]
    from PIL import Image, ImageDraw  # type: ignore[import-not-found]

    _TRAY_AVAILABLE = True
except ImportError:
    pass


def is_available() -> bool:
    return _TRAY_AVAILABLE


def _create_icon_image() -> Any:
    if not _TRAY_AVAILABLE:
        return None
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(37, 99, 235, 255))
    margin = size // 4
    midpoint = size // 2
    bottom = size - margin
    draw.line(
        [
            (margin, bottom),
            (margin, margin + 4),
            (midpoint, midpoint),
            (size - margin, margin + 4),
            (size - margin, bottom),
        ],
        fill=(255, 255, 255, 255),
        width=6,
    )
    return image


class TrayIconManager:
    def __init__(self, page: Any) -> None:
        self.page = page
        self._icon: Any = None

    def _dispatch(self, handler: Any) -> None:
        try:
            self.page.run_thread(handler)
        except Exception:
            handler()

    def start(self) -> bool:
        if not _TRAY_AVAILABLE or bool(getattr(self.page, "web", False)):
            return False
        if self._icon is not None:
            return True
        image = _create_icon_image()
        if image is None:
            return False

        def on_open(_icon: Any, _item: Any) -> None:
            self._dispatch(self.show_window)

        def on_pause(_icon: Any, _item: Any) -> None:
            self._dispatch(self.pause_all)

        def on_resume(_icon: Any, _item: Any) -> None:
            self._dispatch(self.resume_all)

        def on_status(_icon: Any, _item: Any) -> None:
            self._dispatch(self.show_status)

        def on_quit(icon: Any, _item: Any) -> None:
            icon.stop()
            self._dispatch(self.quit_app)

        menu = pystray.Menu(
            pystray.MenuItem("Abrir Mezzold Connect", on_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pausar envios", on_pause),
            pystray.MenuItem("Continuar envios", on_resume),
            pystray.MenuItem("Ver status", on_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar aplicativo", on_quit),
        )
        self._icon = pystray.Icon("MezzoldConnect", image, "Mezzold Connect", menu)
        threading.Thread(
            target=self._icon.run,
            daemon=True,
            name="tray-icon",
        ).start()
        return True

    def minimize_to_tray(self) -> None:
        self.page.window.visible = False
        self.page.window.skip_task_bar = True
        self.page.update()
        self.update_tooltip("Mezzold Connect — rodando em segundo plano")
        app_log.app_minimized_to_tray()

    def show_window(self) -> None:
        self.page.window.skip_task_bar = False
        self.page.window.visible = True
        self.page.window.minimized = False
        self.page.window.focused = True
        self.page.update()
        self.update_tooltip("Mezzold Connect")
        app_log.app_restored_from_tray()

    def pause_all(self) -> None:
        total = app_runtime.pause_all_campaigns()
        self.update_tooltip(f"Mezzold Connect — {total} envio(s) pausado(s)")

    def resume_all(self) -> None:
        total = app_runtime.resume_pending_campaigns()
        self.update_tooltip(f"Mezzold Connect — {total} envio(s) retomado(s)")

    def show_status(self) -> None:
        self.show_window()
        self.page.go("/schedule")

    def quit_app(self) -> None:
        app_log.app_closed()
        self.stop()
        try:
            self.page.run_task(self.page.window.destroy)
        except Exception:
            # A web/test page has no native window to destroy.
            pass

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def update_tooltip(self, text: str) -> None:
        if self._icon is not None:
            try:
                self._icon.title = text
            except Exception:
                pass
