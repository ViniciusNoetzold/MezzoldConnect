"""System tray icon integration for Mezzold Connect on Windows (Etapa 1).

Requires: pip install pystray pillow
Falls back gracefully when these packages are not available.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ui import MezzoldApp

_TRAY_AVAILABLE = False
try:
    import pystray  # type: ignore[import]
    from PIL import Image, ImageDraw  # type: ignore[import]
    _TRAY_AVAILABLE = True
except ImportError:
    pass


def is_available() -> bool:
    """Return True only when pystray and Pillow are installed."""
    return _TRAY_AVAILABLE


def _create_icon_image() -> Any:
    """Create a simple 64x64 RGBA icon without external image files."""
    if not _TRAY_AVAILABLE:
        return None
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Blue circle
    draw.ellipse([2, 2, size - 2, size - 2], fill=(37, 99, 235, 255))
    # Letter M — two peaks
    m = size // 4
    mid = size // 2
    bot = size - m
    pts = [(m, bot), (m, m + 4), (mid, mid), (size - m, m + 4), (size - m, bot)]
    draw.line(pts, fill=(255, 255, 255, 255), width=6)
    return img


class TrayIconManager:
    """Manages the Windows system-tray icon and its menu."""

    def __init__(self, app: MezzoldApp) -> None:
        self.app = app
        self._icon: Any = None

    def start(self) -> None:
        """Start the tray icon in a daemon thread."""
        if not _TRAY_AVAILABLE:
            return
        img = _create_icon_image()
        if img is None:
            return

        def on_open(_icon: Any, _item: Any) -> None:
            self.app.after(0, self.app.show_from_tray)

        def on_pause(_icon: Any, _item: Any) -> None:
            self.app.after(0, self.app.tray_pause_all)

        def on_resume(_icon: Any, _item: Any) -> None:
            self.app.after(0, self.app.tray_resume_all)

        def on_status(_icon: Any, _item: Any) -> None:
            def _open_and_navigate() -> None:
                self.app.show_from_tray()
                self.app.show_schedule()

            self.app.after(0, _open_and_navigate)

        def on_quit(_icon: Any, _item: Any) -> None:
            _icon.stop()
            self.app.after(0, self.app._quit_confirmed)

        menu = pystray.Menu(
            pystray.MenuItem("Abrir Mezzold Connect", on_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pausar envios", on_pause),
            pystray.MenuItem("Continuar envios", on_resume),
            pystray.MenuItem("Ver status", on_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar aplicativo", on_quit),
        )

        self._icon = pystray.Icon(
            "MezzoldConnect",
            img,
            "Mezzold Connect",
            menu,
        )

        t = threading.Thread(target=self._icon.run, daemon=True, name="tray-icon")
        t.start()

    def stop(self) -> None:
        """Stop the tray icon cleanly."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def update_tooltip(self, text: str) -> None:
        """Update the tray icon tooltip text."""
        if self._icon is not None:
            try:
                self._icon.title = text
            except Exception:
                pass
