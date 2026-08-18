# -*- coding: utf-8 -*-
import flet as ft
from screens.login import LoginScreen
from screens.dashboard import DashboardScreen
import database
import threading
import background_worker

def main(page: ft.Page):
    page.title = database.APP_TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 800
    page.window.min_height = 600
    
    def route_change(e: ft.RouteChangeEvent):
        page.views.clear()
        page.overlay.clear()
        
        if page.route == "/dashboard":
            page.views.append(DashboardScreen(page))
        elif page.route == "/contacts":
            from screens.contacts import ContactsScreen
            page.views.append(ContactsScreen(page))
        elif page.route == "/campaigns":
            from screens.campaigns import CampaignsScreen
            page.views.append(CampaignsScreen(page))
        elif page.route == "/import_contacts":
            from screens.import_contacts import ImportContactsScreen
            page.views.append(ImportContactsScreen(page))
        elif page.route == "/history":
            from screens.history import HistoryScreen
            page.views.append(HistoryScreen(page))
        elif page.route == "/health":
            from screens.health import HealthScreen
            page.views.append(HealthScreen(page))
        elif page.route == "/schedule":
            from screens.schedule import ScheduleScreen
            page.views.append(ScheduleScreen(page))
        elif page.route == "/risk":
            from screens.risk import RiskScreen
            page.views.append(RiskScreen(page))
        elif page.route == "/settings":
            from screens.settings import SettingsScreen
            page.views.append(SettingsScreen(page))
        else:
            page.views.append(LoginScreen(page))
            
        page.update()

    def view_pop(e: ft.ViewPopEvent):
        page.views.pop()
        top_view = page.views[-1]
        page.go(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    
    database.initialize_database()

    page.views.clear()
    page.overlay.clear()
    page.views.append(LoginScreen(page))
    page.update()

if __name__ == "__main__":
    # Start the background worker thread for sending messages and warmup
    worker_thread = threading.Thread(target=background_worker.run_background_worker, daemon=True)
    worker_thread.start()
    
    ft.app(target=main)