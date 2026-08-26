"""Ponto de entrada do Mezzold Connect v2."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

import flet as ft

import app_log
import auth
import background_worker
import database
from flet_compat import install_dialog_dismiss_guard
from screens.common import disabled_page_transitions
from tray_icon import TrayIconManager


install_dialog_dismiss_guard()


_worker_lock = threading.Lock()
_worker_started = False
_start_minimized = False
_KNOWN_ROUTES = {
    "/",
    "/dashboard",
    "/contacts",
    "/lead_search",
    "/campaigns",
    "/import_contacts",
    "/schedule",
    "/risk",
    "/history",
    "/health",
    "/connection",
    "/updates",
    "/help",
    "/settings",
}


def _cli_output(message: object, *, error: bool = False) -> None:
    """Write only when the process owns a console (PyInstaller --windowed does not)."""
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream)


def _start_embedded_worker() -> None:
    """Start the scheduler once for the desktop process."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        threading.Thread(
            target=background_worker.run_background_worker,
            daemon=True,
            name="mezzold-background-worker",
        ).start()


def _screen_for_route(route: str, page: ft.Page) -> ft.View:
    if route == "/dashboard":
        from screens.dashboard import DashboardScreen

        return DashboardScreen(page)
    if route == "/contacts":
        from screens.contacts import ContactsScreen

        return ContactsScreen(page)
    if route == "/lead_search":
        from screens.lead_search import LeadSearchScreen

        return LeadSearchScreen(page)
    if route == "/campaigns":
        from screens.campaigns import CampaignsScreen

        return CampaignsScreen(page)
    if route == "/import_contacts":
        from screens.import_contacts import ImportContactsScreen

        return ImportContactsScreen(page)
    if route == "/schedule":
        from screens.schedule import ScheduleScreen

        return ScheduleScreen(page)
    if route == "/risk":
        from screens.risk import RiskScreen

        return RiskScreen(page)
    if route == "/history":
        from screens.history import HistoryScreen

        return HistoryScreen(page)
    if route == "/health":
        from screens.health import HealthScreen

        return HealthScreen(page)
    if route == "/connection":
        from screens.connection import ConnectionScreen

        return ConnectionScreen(page)
    if route == "/updates":
        from screens.updates import UpdatesScreen

        return UpdatesScreen(page)
    if route == "/help":
        from screens.help import HelpScreen

        return HelpScreen(page)
    if route == "/settings":
        from screens.settings import SettingsScreen

        return SettingsScreen(page)

    from screens.login import LoginScreen

    return LoginScreen(page)


def _is_authenticated() -> bool:
    return bool(auth.get_current_user())


def _can_open_health() -> bool:
    role = str(auth.get_current_role() or "").strip().lower().replace("-", "_")
    return role in {"equipe", "admin", "mezzold_master", "master", "mezzold master"}


def main(page: ft.Page) -> None:
    """Create one Flet desktop/web session."""
    database.initialize_database()
    _start_embedded_worker()
    app_log.app_started()

    page.title = f"{database.APP_TITLE} v{database.APP_VERSION}"
    theme_name = database.get_setting("app_theme", "light").strip().lower()
    page.theme_mode = ft.ThemeMode.DARK if theme_name == "dark" else ft.ThemeMode.LIGHT
    density_name = database.get_setting("ui_density", "normal").strip().lower()
    density = {
        "compact": ft.VisualDensity.COMPACT,
        "comfortable": ft.VisualDensity.COMFORTABLE,
        "normal": ft.VisualDensity.STANDARD,
    }.get(density_name, ft.VisualDensity.STANDARD)
    try:
        font_size = max(9, min(14, int(database.get_setting("ui_font_size", "10"))))
    except (TypeError, ValueError):
        font_size = 10
    page.theme = ft.Theme(
        visual_density=density,
        text_theme=ft.TextTheme(body_medium=ft.TextStyle(size=font_size)),
        page_transitions=disabled_page_transitions(),
    )
    page.padding = 0
    page.window.width = 1240
    page.window.height = 820
    page.window.min_width = 900
    page.window.min_height = 640

    tray = TrayIconManager(page)
    tray_started = tray.start()
    if tray_started:
        page.window.prevent_close = True

        def on_window_event(event: ft.WindowEvent) -> None:
            if event.type == ft.WindowEventType.CLOSE:
                tray.minimize_to_tray()

        page.window.on_event = on_window_event

    def route_change(_event: ft.RouteChangeEvent | None = None) -> None:
        route = (page.route or "/").split("?", 1)[0]
        if route not in _KNOWN_ROUTES:
            page.go("/dashboard" if _is_authenticated() else "/")
            return
        if route != "/" and not _is_authenticated():
            page.go("/")
            return
        if route == "/" and _is_authenticated():
            page.go("/dashboard")
            return
        if route == "/health" and not _can_open_health():
            page.go("/dashboard")
            return

        # Some screens register Flet services (for example FilePicker) through
        # Page.services. That property belongs to the current root view, so the
        # next view must be constructed before removing the previous one.
        next_view = _screen_for_route(route, page)
        page.views.clear()
        page.views.append(next_view)
        page.update()

    def view_pop(_event: ft.ViewPopEvent) -> None:
        if len(page.views) > 1:
            page.views.pop()
            page.go(page.views[-1].route)
        elif _is_authenticated():
            page.go("/dashboard")
        else:
            page.go("/")

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    # A new Flet page already starts at "/". Calling go("/") is a no-op in
    # current Flet releases, so the route callback would never mount LoginScreen.
    # Mount the initial route explicitly; authenticated sessions still navigate
    # to the dashboard normally.
    initial_route = "/dashboard" if _is_authenticated() else "/"
    if (page.route or "/").split("?", 1)[0] == initial_route:
        route_change()
    else:
        page.go(initial_route)

    if _start_minimized and tray_started:
        tray.minimize_to_tray()


def _export_firebird(output: str | None) -> Path:
    from data_export import export_sqlite_to_firebird_sql

    destination = Path(output) if output else database.DATA_DIR / "mezzold_connect_firebird.sql"
    export_sqlite_to_firebird_sql(database.DB_PATH, destination)
    return destination


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mezzold Connect v2")
    parser.add_argument("--background", action="store_true", help="Executa somente o agente de envios.")
    parser.add_argument("--minimized", action="store_true", help="Abre minimizado na bandeja do Windows.")
    parser.add_argument("--initialize-database", action="store_true", help="Inicializa/migra o banco e encerra.")
    parser.add_argument("--backup-database", nargs="?", const="", metavar="DESTINO", help="Cria backup SQLite consistente.")
    parser.add_argument("--export-firebird", nargs="?", const="", metavar="DESTINO", help="Exporta os dados em SQL ANSI/Firebird.")
    return parser.parse_args(argv)


def cli(argv: list[str] | None = None) -> int:
    global _start_minimized
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        database.initialize_database()
        if args.initialize_database:
            _cli_output(f"Banco inicializado: {database.DB_PATH}")
            return 0
        if args.backup_database is not None:
            destination = args.backup_database or None
            _cli_output(database.create_backup(destination))
            return 0
        if args.export_firebird is not None:
            _cli_output(_export_firebird(args.export_firebird or None))
            return 0
        if args.background:
            app_log.agent_started()
            background_worker.run_background_worker()
            return 0

        _start_minimized = bool(args.minimized)
        ft.run(main)
        return 0
    except Exception as exc:
        app_log.log("APP_STARTUP_ERROR", repr(exc))
        _cli_output(f"Erro ao iniciar o Mezzold Connect: {exc}", error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
