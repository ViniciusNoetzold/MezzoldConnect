from __future__ import annotations

import asyncio
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import flet as ft

import auth
import database


ROUTE_LOGIN = "/"
ROUTE_DASHBOARD = "/dashboard"
ROUTE_CONTACTS = "/contacts"
ROUTE_IMPORT_CONTACTS = "/import_contacts"
ROUTE_LEAD_SEARCH = "/lead_search"
ROUTE_CAMPAIGNS = "/campaigns"
ROUTE_SCHEDULE = "/schedule"
ROUTE_RISK = "/risk"
ROUTE_HISTORY = "/history"
ROUTE_HEALTH = "/health"
ROUTE_CONNECTION = "/connection"
ROUTE_UPDATES = "/updates"
ROUTE_HELP = "/help"
ROUTE_SETTINGS = "/settings"

PRIVILEGED_ROLES = frozenset({"equipe", "admin", "master", "mezzold_master"})
ROLE_LABELS = {
    "cliente": "Cliente",
    "operador": "Operador",
    "equipe": "Equipe",
    "admin": "Administrador",
    "master": "Mezzold Master",
    "mezzold_master": "Mezzold Master",
}

SIDEBAR_COLLAPSED_WIDTH = 76
SIDEBAR_EXPANDED_WIDTH = 260
SIDEBAR_ANIMATION_MS = 180
_SIDEBAR_EXPANDED_ATTR = "_mezzold_sidebar_expanded"
_SIDEBAR_ACTIVE_TOKEN_ATTR = "_mezzold_sidebar_active_token"
_SIDEBAR_NAVIGATION_TOKEN = object()


@dataclass(frozen=True)
class SidebarItem:
    label: str
    icon: Any
    route: str
    roles: frozenset[str] | None = None


SIDEBAR_ITEMS: tuple[SidebarItem, ...] = (
    SidebarItem("Início", ft.Icons.HOME, ROUTE_DASHBOARD),
    SidebarItem("Clientes", ft.Icons.PEOPLE, ROUTE_CONTACTS),
    SidebarItem("Importar clientes", ft.Icons.UPLOAD_FILE, ROUTE_IMPORT_CONTACTS),
    SidebarItem("Buscar leads", ft.Icons.PERSON_SEARCH, ROUTE_LEAD_SEARCH),
    SidebarItem("Nova Campanha", ft.Icons.SEND, ROUTE_CAMPAIGNS),
    SidebarItem("Agenda de Envios", ft.Icons.SCHEDULE, ROUTE_SCHEDULE),
    SidebarItem("Conferir Risco", ft.Icons.WARNING_AMBER, ROUTE_RISK),
    SidebarItem("Histórico", ft.Icons.HISTORY, ROUTE_HISTORY),
    SidebarItem("Saúde do Número", ft.Icons.HEALTH_AND_SAFETY, ROUTE_HEALTH, PRIVILEGED_ROLES),
    SidebarItem("Conexão WhatsApp", ft.Icons.LINK, ROUTE_CONNECTION),
    SidebarItem("Atualizações", ft.Icons.SYSTEM_UPDATE, ROUTE_UPDATES),
    SidebarItem("Ajuda", ft.Icons.HELP_OUTLINE, ROUTE_HELP),
    SidebarItem("Configurações", ft.Icons.SETTINGS, ROUTE_SETTINGS),
)


def normalized_role(role: object | None = None) -> str:
    value = auth.get_current_role() if role is None else role
    return str(value or "cliente").strip().lower()


def sidebar_items_for_role(role: object | None = None) -> list[SidebarItem]:
    current = normalized_role(role)
    return [item for item in SIDEBAR_ITEMS if item.roles is None or current in item.roles]


def disabled_page_transitions() -> ft.PageTransitionsTheme:
    """Disable route animations on every target to avoid the zoom/jump effect."""

    none = ft.PageTransitionTheme.NONE
    return ft.PageTransitionsTheme(
        android=none,
        ios=none,
        linux=none,
        macos=none,
        windows=none,
    )


def sidebar_is_expanded(page: ft.Page) -> bool:
    """Return the sidebar state kept for the lifetime of a Flet page.

    Every application screen owns a newly constructed layout.  Keeping this
    small piece of UI state on the page lets the replacement sidebar start at
    the same width and opacity as the one it replaces, instead of briefly
    rendering collapsed while the pointer is still over it.
    """

    return bool(getattr(page, _SIDEBAR_EXPANDED_ATTR, False))


def set_sidebar_expanded(page: ft.Page, expanded: bool) -> None:
    """Persist the current sidebar state across route view reconstruction."""

    try:
        setattr(page, _SIDEBAR_EXPANDED_ATTR, bool(expanded))
    except (AttributeError, TypeError):
        # Lightweight/foreign Page implementations may disallow custom
        # attributes.  The sidebar still works for the currently mounted view.
        pass


def _set_active_sidebar_token(page: ft.Page, token: object) -> bool:
    """Mark which sidebar may handle hover events for this page."""

    try:
        setattr(page, _SIDEBAR_ACTIVE_TOKEN_ATTR, token)
        return True
    except (AttributeError, TypeError):
        return False


def _sidebar_token_is_active(page: ft.Page, token: object) -> bool:
    try:
        return getattr(page, _SIDEBAR_ACTIVE_TOKEN_ATTR) is token
    except (AttributeError, TypeError):
        # Keep hover functional for page-like objects that cannot store a token.
        return True


def navigate(page: ft.Page, route: str) -> None:
    target = str(route or "").strip()
    if not target:
        return
    current = str(getattr(page, "route", "") or "").split("?", 1)[0]
    if current == target.split("?", 1)[0]:
        return
    previous_token = getattr(page, _SIDEBAR_ACTIVE_TOKEN_ATTR, None)
    token_was_set = _set_active_sidebar_token(page, _SIDEBAR_NAVIGATION_TOKEN)
    try:
        page.go(target)
    except Exception:
        if token_was_set:
            _set_active_sidebar_token(page, previous_token)
        raise


def clear_session(page: ft.Page | None = None) -> None:
    """Clear both the legacy in-process auth state and Flet session storage."""

    auth_clear = getattr(auth, "clear_session", None)
    if callable(auth_clear):
        auth_clear()
    else:
        auth.set_current_user(None, None)
    storage = getattr(page, "session", None) if page is not None else None
    clear = getattr(storage, "clear", None)
    if callable(clear):
        try:
            clear()
        except (AttributeError, RuntimeError):
            # The global auth state is the source of truth in this application.
            pass


def logout(page: ft.Page, _event: object | None = None) -> None:
    clear_session(page)
    page.go(ROUTE_LOGIN)


def safe_update(page: ft.Page) -> None:
    try:
        page.update()
    except (AttributeError, RuntimeError):
        # A detached/fake page is useful for construction tests.
        pass


def close_dialog(page: ft.Page, _event: object | None = None) -> None:
    pop_dialog = getattr(page, "pop_dialog", None)
    if callable(pop_dialog):
        pop_dialog()
        return
    # Compatibility for a lightweight fake page used by tests.
    dialog = getattr(page, "dialog", None)
    if dialog is not None:
        dialog.open = False
        safe_update(page)


def show_snack(
    page: ft.Page,
    message: str,
    *,
    error: bool = False,
    bgcolor: str | ft.Colors | None = None,
    action: str | None = None,
    on_action: Callable[..., Any] | None = None,
) -> ft.SnackBar:
    # Flet keeps dialogs (including SnackBars) in a managed overlay stack.  A
    # fast background job can finish before its "started" notification has
    # closed; opening a second SnackBar in that interval used to produce a
    # client-side RangeError.  Reuse the mounted notification when its action
    # contract is unchanged, so the latest state wins without stacking
    # transient controls.
    active = getattr(page, "_mezzold_active_snackbar", None)
    if (
        isinstance(active, ft.SnackBar)
        and bool(getattr(active, "open", False))
        and getattr(active, "action", None) == action
        and getattr(active, "on_action", None) == on_action
    ):
        if isinstance(active.content, ft.Text):
            active.content.value = message
        else:
            active.content = ft.Text(message)
        active.bgcolor = bgcolor or (ft.Colors.ERROR_CONTAINER if error else ft.Colors.GREEN_800)
        active.tooltip = message
        try:
            active.update()
        except (AttributeError, RuntimeError):
            safe_update(page)
        return active

    def clear_active(_event: object | None = None) -> None:
        if getattr(page, "_mezzold_active_snackbar", None) is snack:
            try:
                setattr(page, "_mezzold_active_snackbar", None)
            except (AttributeError, TypeError):
                pass

    snack = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=bgcolor or (ft.Colors.ERROR_CONTAINER if error else ft.Colors.GREEN_800),
        show_close_icon=True,
        action=action,
        on_action=on_action,
        on_dismiss=clear_active,
        tooltip=message,
    )
    try:
        setattr(page, "_mezzold_active_snackbar", snack)
    except (AttributeError, TypeError):
        pass
    show_dialog = getattr(page, "show_dialog", None)
    if callable(show_dialog):
        show_dialog(snack)
    else:
        page.snack_bar = snack
        snack.open = True
        safe_update(page)
    return snack


def show_alert(
    page: ft.Page,
    title: str,
    content: str | ft.Control,
    *,
    actions: Iterable[ft.Control] | None = None,
    modal: bool = True,
    key: str | None = None,
    on_dismiss: Callable[..., Any] | None = None,
) -> ft.AlertDialog:
    body = ft.Text(content, selectable=True) if isinstance(content, str) else content
    dialog_actions = list(actions or ())
    if not dialog_actions:
        dialog_actions.append(
            ft.TextButton(
                "Fechar",
                key=f"{key}-close" if key else None,
                tooltip="Fechar janela",
                on_click=lambda e: close_dialog(page, e),
            )
        )
    dialog = ft.AlertDialog(
        modal=modal,
        title=ft.Text(title),
        content=body,
        actions=dialog_actions,
        scrollable=True,
        semantics_label=title,
        key=key,
        on_dismiss=on_dismiss,
    )
    show_dialog = getattr(page, "show_dialog", None)
    if callable(show_dialog):
        show_dialog(dialog)
    else:
        page.dialog = dialog
        dialog.open = True
        safe_update(page)
    return dialog


def _launchable_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Endereço vazio.")
    path = Path(raw).expanduser()
    if path.exists():
        return path.resolve().as_uri()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https", "file"}:
        raise ValueError("Use uma URL http(s), file:// ou um caminho local existente.")
    return raw


def open_url(page: ft.Page, value: str, *, notify_error: bool = True) -> bool:
    """Open a trusted web/local URL through Flet's current launcher API."""

    try:
        target = _launchable_url(value)
        launcher = getattr(page, "launch_url", None)
        if callable(launcher):
            launcher(target)
        elif not webbrowser.open(target):
            raise RuntimeError("O sistema não confirmou a abertura do endereço.")
        return True
    except Exception as exc:
        if notify_error:
            show_snack(page, f"Não foi possível abrir o link: {exc}", error=True)
        return False


def run_in_background(page: ft.Page, handler: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Use Flet's app-aware executor, with a small fallback for fake pages."""

    runner = getattr(page, "run_thread", None)
    if callable(runner):
        runner(handler, *args, **kwargs)
        return
    threading.Thread(target=handler, args=args, kwargs=kwargs, daemon=True).start()


def run_after_dialog(
    page: ft.Page,
    handler: Callable[..., Any],
    *args: Any,
    delay_seconds: float = 0.5,
    **kwargs: Any,
) -> None:
    """Run work after Flet has finished reconciling a dismissed overlay.

    Launching a worker (and its progress updates) from inside an AlertDialog's
    dismiss event can race the Flutter overlay removal.  Real Flet pages get a
    short asynchronous deferral; lightweight test pages stay synchronous.
    """

    runner = getattr(page, "run_task", None)
    if callable(runner) and page.__class__.__module__.startswith("flet."):
        async def deferred() -> None:
            await asyncio.sleep(max(float(delay_seconds), 0.0))
            handler(*args, **kwargs)

        runner(deferred)
        return
    handler(*args, **kwargs)


def build_sidebar(page: ft.Page, selected_route: str) -> ft.Container:
    user = auth.get_current_user() or "Usuário"
    role = normalized_role()
    company_name = database.get_setting("company_name", "Mezzold").strip() or "Mezzold"
    animation = ft.Animation(SIDEBAR_ANIMATION_MS, ft.AnimationCurve.EASE_IN_OUT)
    initially_expanded = sidebar_is_expanded(page)
    initial_label_opacity = 1 if initially_expanded else 0
    sidebar_token = object()
    _set_active_sidebar_token(page, sidebar_token)
    animated_labels: list[ft.Text] = []

    def animated_label(
        value: str,
        *,
        size: int | None = None,
        weight: ft.FontWeight | None = None,
        color: object | None = None,
        key: str | None = None,
    ) -> ft.Text:
        label = ft.Text(
            value,
            size=size,
            weight=weight,
            color=color,
            key=key,
            opacity=initial_label_opacity,
            animate_opacity=animation,
            no_wrap=True,
        )
        animated_labels.append(label)
        return label

    nav_controls: list[ft.Control] = []
    for item in sidebar_items_for_role(role):
        selected = item.route == selected_route
        nav_controls.append(
            ft.ListTile(
                leading=ft.Icon(item.icon),
                title=animated_label(
                    item.label,
                    weight=ft.FontWeight.BOLD if selected else ft.FontWeight.NORMAL,
                ),
                selected=selected,
                dense=True,
                content_padding=ft.Padding.symmetric(horizontal=12, vertical=2),
                tooltip=f"Ir para {item.label}",
                key=f"nav-{item.route.strip('/').replace('_', '-') or 'login'}",
                on_click=lambda _e, route=item.route: navigate(page, route),
            )
        )

    brand_label = animated_label(company_name, size=20, weight=ft.FontWeight.BOLD, key="sidebar-brand-label")
    session_label = animated_label(
        f"{user}\nPerfil: {ROLE_LABELS.get(role, role.title())}",
        size=12,
        color=ft.Colors.PRIMARY,
        key="sidebar-session",
    )
    logout_label = animated_label("Sair", color=ft.Colors.ERROR, key="sidebar-logout-label")

    sidebar = ft.Container(
        width=SIDEBAR_EXPANDED_WIDTH if initially_expanded else SIDEBAR_COLLAPSED_WIDTH,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        padding=12,
        key="app-sidebar",
        animate_size=animation,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CONNECT_WITHOUT_CONTACT, color=ft.Colors.BLUE_ACCENT),
                        brand_label,
                    ],
                    spacing=12,
                    key="sidebar-brand",
                ),
                ft.Divider(height=12),
                ft.ListView(
                    controls=nav_controls,
                    spacing=2,
                    expand=True,
                    key="sidebar-navigation",
                    semantic_child_count=len(nav_controls),
                ),
                ft.Divider(height=12),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    border_radius=8,
                    tooltip=f"{user} • {ROLE_LABELS.get(role, role.title())}",
                    content=ft.Row(
                        [ft.Icon(ft.Icons.ACCOUNT_CIRCLE, color=ft.Colors.PRIMARY), session_label],
                        spacing=10,
                    ),
                    key="sidebar-account",
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=8,
                    tooltip="Encerrar sessão",
                    ink=True,
                    on_click=lambda e: logout(page, e),
                    content=ft.Row(
                        [ft.Icon(ft.Icons.LOGOUT, color=ft.Colors.ERROR), logout_label],
                        spacing=10,
                    ),
                    key="logout-button",
                ),
            ],
            expand=True,
            spacing=8,
        ),
    )

    def toggle_sidebar(event: ft.HoverEvent) -> None:
        # Flet can dispatch hover=False for the old control while replacing a
        # route View.  Only the sidebar belonging to the current generation may
        # change the persisted state; the replacement still handles a genuine
        # pointer leave normally.
        if not _sidebar_token_is_active(page, sidebar_token):
            return
        expanded = str(getattr(event, "data", event)).strip().lower() == "true"
        target_width = SIDEBAR_EXPANDED_WIDTH if expanded else SIDEBAR_COLLAPSED_WIDTH
        target_opacity = 1 if expanded else 0
        set_sidebar_expanded(page, expanded)
        labels_already_set = all(label.opacity == target_opacity for label in animated_labels)
        if sidebar.width == target_width and labels_already_set:
            return
        sidebar.width = target_width
        for label in animated_labels:
            label.opacity = target_opacity
        safe_update(page)

    sidebar.on_hover = toggle_sidebar
    return sidebar


def screen_layout(
    page: ft.Page,
    selected_route: str,
    title: str,
    body: ft.Control,
    *,
    subtitle: str = "",
    actions: Iterable[ft.Control] | None = None,
) -> ft.Row:
    heading: list[ft.Control] = [ft.Text(title, size=28, weight=ft.FontWeight.BOLD, key="screen-title")]
    if subtitle:
        heading.append(ft.Text(subtitle, color=ft.Colors.ON_SURFACE_VARIANT, key="screen-subtitle"))
    header = ft.Row(
        controls=[ft.Column(heading, spacing=2, expand=True), *list(actions or ())],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        key="screen-header",
    )
    content = ft.Container(
        expand=True,
        padding=24,
        content=ft.Column(
            controls=[header, ft.Divider(height=12), body],
            expand=True,
            spacing=10,
        ),
        key="screen-content",
    )
    return ft.Row(
        controls=[build_sidebar(page, selected_route), content],
        expand=True,
        spacing=0,
        key="screen-layout",
    )
