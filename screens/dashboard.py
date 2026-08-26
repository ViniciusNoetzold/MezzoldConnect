"""Dashboard e acionamento seguro das campanhas vencidas."""
from __future__ import annotations

import flet as ft

import campaigns
from runtime import app_runtime, requires_real_web_confirmation
from screens import common


STATUS_LABELS = {
    "rascunho": "Rascunho",
    "agendada": "Agendada",
    "enviando": "Em andamento",
    "concluída": "Concluída",
    "concluida": "Concluída",
    "pausada": "Pausada",
    "cancelada": "Cancelada",
    "enviado": "Enviado",
    "erro": "Erro",
}


def friendly_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return STATUS_LABELS.get(normalized, str(value or ""))


class Dashboard(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(route="/dashboard", padding=0)
        self.app_page = page

        self.stat_contacts = self._stat_text()
        self.stat_opt_in = self._stat_text(ft.Colors.GREEN)
        self.stat_blocked = self._stat_text(ft.Colors.RED)
        self.stat_campaigns = self._stat_text(ft.Colors.BLUE)
        self.stat_scheduled = self._stat_text(ft.Colors.AMBER)
        self.stat_sent = self._stat_text(ft.Colors.GREEN)
        self.stat_failed = self._stat_text(ft.Colors.RED)

        self.campaigns_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome da campanha")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Agendamento")),
                ft.DataColumn(ft.Text("Total"), numeric=True),
                ft.DataColumn(ft.Text("Enviados"), numeric=True),
                ft.DataColumn(ft.Text("Falhas"), numeric=True),
                ft.DataColumn(ft.Text("Ação")),
            ],
            rows=[],
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            key="dashboard-campaigns-table",
        )
        self.table_container = ft.Container(
            content=ft.Text(
                "Nenhuma campanha criada ainda.",
                italic=True,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

        cards = ft.Column(
            [
                ft.Row(
                    [
                        self._stat_card("Total contatos", self.stat_contacts, ft.Icons.PEOPLE, ft.Colors.BLUE_GREY),
                        self._stat_card("Com opt-in", self.stat_opt_in, ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN),
                        self._stat_card("Blacklist", self.stat_blocked, ft.Icons.BLOCK, ft.Colors.RED),
                        self._stat_card("Campanhas", self.stat_campaigns, ft.Icons.CAMPAIGN, ft.Colors.BLUE),
                    ],
                    spacing=12,
                    wrap=True,
                ),
                ft.Row(
                    [
                        self._stat_card("Agendadas", self.stat_scheduled, ft.Icons.SCHEDULE, ft.Colors.AMBER),
                        self._stat_card("Enviados", self.stat_sent, ft.Icons.DONE_ALL, ft.Colors.GREEN),
                        self._stat_card("Falhas", self.stat_failed, ft.Icons.ERROR_OUTLINE, ft.Colors.RED),
                    ],
                    spacing=12,
                    wrap=True,
                ),
            ],
            spacing=12,
        )
        body = ft.Column(
            [
                cards,
                ft.Divider(height=18),
                ft.Text("Últimas campanhas", size=20, weight=ft.FontWeight.BOLD),
                ft.ListView([self.table_container], expand=True),
            ],
            expand=True,
            spacing=12,
        )
        self.controls = [
            common.screen_layout(
                page,
                "/dashboard",
                "Dashboard",
                body,
                subtitle="Visão geral dos contatos e disparos.",
                actions=[
                    ft.OutlinedButton(
                        "Atualizar",
                        icon=ft.Icons.REFRESH,
                        key="dashboard-refresh",
                        on_click=self.refresh_stats,
                    ),
                    ft.ElevatedButton(
                        "Enviar atrasados",
                        icon=ft.Icons.SEND_TIME_EXTENSION,
                        key="dashboard-send-due",
                        on_click=self.send_due,
                    ),
                ],
            )
        ]

    @staticmethod
    def _stat_text(color: str | None = None) -> ft.Text:
        return ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=color)

    @staticmethod
    def _stat_card(title: str, value: ft.Text, icon: str, color: str) -> ft.Container:
        return ft.Container(
            width=200,
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            content=ft.Row(
                [
                    ft.Icon(icon, size=32, color=color),
                    ft.Column(
                        [ft.Text(title, size=12, color=ft.Colors.ON_SURFACE_VARIANT), value],
                        spacing=2,
                    ),
                ],
                spacing=12,
            ),
        )

    def refresh_stats(self, _event: object | None = None) -> None:
        try:
            stats = campaigns.dashboard_stats()
            self.stat_contacts.value = str(stats.get("contacts", 0))
            self.stat_opt_in.value = str(stats.get("opt_in", 0))
            self.stat_blocked.value = str(stats.get("blocked", 0))
            self.stat_campaigns.value = str(stats.get("campaigns", 0))
            self.stat_scheduled.value = str(stats.get("scheduled", 0))
            self.stat_sent.value = str(stats.get("sent", 0))
            self.stat_failed.value = str(stats.get("failed", 0))
            self.load_campaigns_table()
        except Exception as exc:
            common.show_snack(self.app_page, f"Erro ao atualizar o dashboard: {exc}", error=True)
        common.safe_update(self.app_page)

    def load_campaigns_table(self) -> None:
        items = campaigns.list_campaigns()
        self.campaigns_table.rows.clear()
        if not items:
            self.table_container.content = ft.Text(
                "Nenhuma campanha criada ainda.",
                italic=True,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
            return
        for campaign in items[:10]:
            self.campaigns_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(campaign.get("id") or ""))),
                        ft.DataCell(ft.Text(str(campaign.get("name") or ""))),
                        ft.DataCell(ft.Text(friendly_status(campaign.get("status")))),
                        ft.DataCell(ft.Text(str(campaign.get("scheduled_at") or "—"))),
                        ft.DataCell(ft.Text(str(campaign.get("total_contacts") or 0))),
                        ft.DataCell(ft.Text(str(campaign.get("sent_contacts") or 0))),
                        ft.DataCell(ft.Text(str(campaign.get("failed_contacts") or 0))),
                        ft.DataCell(
                            ft.TextButton(
                                "Gerenciar",
                                on_click=lambda _event: self.app_page.go("/schedule"),
                            )
                        ),
                    ]
                )
            )
        self.table_container.content = self.campaigns_table

    def send_due(self, _event: object | None = None) -> None:
        try:
            due = campaigns.get_due_campaigns()
            if not due:
                common.show_snack(self.app_page, "Nenhuma campanha atrasada para enviar.")
                return
            started = 0
            confirmation_required = 0
            for campaign in due:
                if requires_real_web_confirmation(campaign):
                    confirmation_required += 1
                    continue
                campaign_id = int(campaign["id"])
                if app_runtime.start_campaign(
                    campaign_id,
                    runner="ui_due_button",
                    completion_callback=lambda _totals, _error: self.refresh_stats(),
                ):
                    started += 1
            common.show_snack(
                self.app_page,
                f"{started} campanha(s) iniciada(s)."
                + (
                    f" {confirmation_required} campanha(s) Web real aguardam confirmação na Agenda."
                    if confirmation_required
                    else ""
                ),
            )
        except Exception as exc:
            common.show_snack(self.app_page, f"Erro ao processar atrasadas: {exc}", error=True)

    def did_mount(self) -> None:
        self.refresh_stats()


DashboardScreen = Dashboard


__all__ = ["Dashboard", "DashboardScreen", "friendly_status"]
