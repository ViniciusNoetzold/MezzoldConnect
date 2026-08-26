from __future__ import annotations

import re
import unicodedata

import flet as ft

from screens import common


ROUTE = common.ROUTE_HELP

FAQ: list[tuple[str, str]] = [
    (
        "O que é uma campanha?",
        "Uma campanha é um conjunto de mensagens enviadas para uma lista de contatos. "
        "Você escolhe a pasta, escreve a mensagem e o app envia com os intervalos configurados.",
    ),
    (
        "Como importar contatos?",
        "Vá em 'Importar clientes'. Escolha uma planilha CSV, TXT ou Excel (.xlsx) com colunas "
        "'nome' e 'numero' (ou 'telefone'). O app formata os telefones automaticamente.",
    ),
    (
        "Como conectar o WhatsApp?",
        "Abra 'Conexão WhatsApp', teste a internet e inicie a sessão local. Se solicitado, "
        "escaneie o QR Code com o celular e mantenha a janela aberta durante os envios.",
    ),
    (
        "O que é modo simulação?",
        "No modo simulação o app registra o fluxo no histórico, mas não envia uma mensagem real. "
        "Ele fica ativo por padrão para proteger contra disparos acidentais.",
    ),
    (
        "O que é 'permitiu contato' (opt-in)?",
        "Opt-in significa que o contato autorizou receber suas mensagens. Envie apenas para quem deu "
        "permissão; isso protege a conta e ajuda a respeitar a LGPD.",
    ),
    (
        "O que é blacklist / 'bloqueado'?",
        "Contatos na blacklist não recebem mensagens, mesmo que estejam em uma campanha ativa. "
        "Use-a para quem pediu para não receber mensagens ou para números inválidos.",
    ),
    (
        "Como evitar bloqueios?",
        "Use intervalos maiores, envie somente para contatos com opt-in, evite listas grandes de uma "
        "vez, varie mensagens e respeite horários comerciais. Confira o risco antes de enviar.",
    ),
    (
        "WhatsApp está desconectado, o que fazer?",
        "Abra 'Conexão WhatsApp', verifique a internet, inicie novamente a sessão e escaneie o QR "
        "Code se ele aparecer. Campanhas pausadas podem ser retomadas após a reconexão.",
    ),
    (
        "Como exportar contatos?",
        "Na tela 'Clientes', selecione uma pasta ou filtro e use 'Exportar CSV'. O arquivo inclui os "
        "dados cadastrais, consentimento, blacklist, origem e observações.",
    ),
    (
        "Como ver o histórico de envios?",
        "Vá em 'Histórico'. A tela mostra data e hora, campanha, contato, status, modo usado, erro e "
        "o link de envio manual quando aplicável.",
    ),
    (
        "O que são presets de velocidade (Seguro/Moderado/Rápido)?",
        "São configurações de intervalo entre mensagens. Seguro usa pausas maiores e reduz risco; "
        "Moderado equilibra velocidade e risco; Rápido deve ser usado com cautela em listas pequenas.",
    ),
    (
        "O que é busca de leads?",
        "A tela 'Buscar leads' abre o Google Maps e recebe texto copiado dos resultados. O app extrai "
        "telefones localmente, mescla rodadas sem duplicar e importa os selecionados para uma pasta.",
    ),
]


def _searchable(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in normalized if not unicodedata.combining(char)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def filter_faq(term: str, items: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    source = FAQ if items is None else items
    needle = _searchable(term).strip()
    if not needle:
        return list(source)
    return [(question, answer) for question, answer in source if needle in _searchable(f"{question} {answer}")]


class HelpScreen(ft.View):
    ROUTE = ROUTE

    def __init__(self, page: ft.Page):
        super().__init__(route=ROUTE, padding=0, key="help-view")
        self.app_page = page
        self.search_field = ft.TextField(
            label="Buscar nas perguntas frequentes",
            hint_text="Ex.: importar, opt-in, conexão...",
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            key="faq-search-input",
            tooltip="Pesquisar perguntas e respostas",
            on_change=self.search,
        )
        self.counter = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT, key="faq-result-count")
        self.faq_list = ft.ListView(
            controls=[],
            expand=True,
            spacing=10,
            padding=ft.Padding.only(right=8),
            key="faq-results-list",
        )
        body = ft.Column(
            [
                ft.Container(
                    padding=16,
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    border_radius=10,
                    content=ft.Row([self.search_field, self.counter]),
                    key="faq-search-panel",
                ),
                self.faq_list,
            ],
            expand=True,
            spacing=12,
        )
        self.controls = [
            common.screen_layout(
                page,
                ROUTE,
                "Ajuda e perguntas frequentes",
                body,
                subtitle="Encontre orientações sobre contatos, campanhas, conexão e segurança.",
            )
        ]
        self.refresh_faq(FAQ)

    @staticmethod
    def _faq_card(index: int, question: str, answer: str) -> ft.Control:
        stable_key = _searchable(question).replace(" ", "-")[:60] or str(index)
        return ft.Container(
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            key=f"faq-item-{stable_key}",
            tooltip=question,
            content=ft.Column(
                [
                    ft.Text(question, size=17, weight=ft.FontWeight.BOLD, selectable=True),
                    ft.Text(
                        answer,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        selectable=True,
                    ),
                ],
                spacing=7,
            ),
        )

    def refresh_faq(self, items: list[tuple[str, str]]) -> None:
        self.faq_list.controls = [
            self._faq_card(index, question, answer)
            for index, (question, answer) in enumerate(items, start=1)
        ]
        if not items:
            self.faq_list.controls = [
                ft.Container(
                    padding=30,
                    alignment=ft.Alignment.CENTER,
                    key="faq-empty-result",
                    content=ft.Text(
                        "Nenhuma pergunta corresponde à busca.",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        italic=True,
                    ),
                )
            ]
        self.faq_list.semantic_child_count = len(items)
        self.counter.value = f"{len(items)} de {len(FAQ)}"

    def search(self, _event: object | None = None) -> None:
        self.refresh_faq(filter_faq(str(self.search_field.value or "")))
        common.safe_update(self.app_page)
