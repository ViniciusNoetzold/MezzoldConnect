from __future__ import annotations

import tkinter as tk
from tkinter import ttk


FAQ: list[tuple[str, str]] = [
    (
        "O que é uma campanha?",
        "Uma campanha é um conjunto de mensagens enviadas para uma lista de contatos. "
        "Você escolhe a pasta de contatos, escreve a mensagem e o app envia com intervalos seguros entre cada envio.",
    ),
    (
        "Como importar contatos?",
        "Vá em 'Importar clientes' no menu lateral. Escolha uma planilha CSV, TXT ou Excel (.xlsx) "
        "com colunas 'nome' e 'numero' (ou 'telefone'). O app formata os telefones automaticamente.",
    ),
    (
        "Como conectar o WhatsApp?",
        "1. Abra o WhatsApp no seu computador (app desktop ou web.whatsapp.com).\n"
        "2. Se pedido, escaneie o QR Code com o celular.\n"
        "3. Mantenha o WhatsApp aberto durante todo o envio.\n"
        "4. Use a tela 'Conexão WhatsApp' para verificar se há internet.",
    ),
    (
        "O que é modo simulação?",
        "No modo simulação, o app registra os envios no histórico mas NÃO envia mensagem de verdade. "
        "Use para testar antes de um disparo real. O modo simulação fica ativo por padrão — "
        "isso protege contra envios acidentais.",
    ),
    (
        "O que é 'permitiu contato' (opt-in)?",
        "Opt-in significa que o contato autorizou receber suas mensagens. "
        "Envie apenas para quem deu permissão — isso protege sua conta WhatsApp e respeita a lei (LGPD).",
    ),
    (
        "O que é blacklist / 'bloqueado'?",
        "Contatos na blacklist nunca recebem mensagens, mesmo que estejam em uma campanha ativa. "
        "Use para quem pediu para não receber mais mensagens ou para números inválidos.",
    ),
    (
        "Como evitar bloqueios?",
        "• Use o preset 'Seguro' com intervalos maiores entre mensagens.\n"
        "• Envie apenas para quem autorizou (opt-in ativo).\n"
        "• Não envie para listas muito grandes de uma só vez.\n"
        "• Varie o texto das mensagens entre campanhas.\n"
        "• Respeite horários comerciais.",
    ),
    (
        "WhatsApp está desconectado, o que fazer?",
        "1. Abra o WhatsApp no computador ou acesse web.whatsapp.com.\n"
        "2. Se pedir QR Code, escaneie com o celular.\n"
        "3. Verifique sua conexão com a internet.\n"
        "4. Na tela 'Conexão WhatsApp', clique em 'Verificar internet'.\n"
        "5. Campanhas pausadas por falta de internet podem ser retomadas normalmente.",
    ),
    (
        "Como exportar contatos?",
        "Na tela 'Clientes', selecione uma pasta e clique em 'Exportar CSV'. "
        "O arquivo gerado tem colunas: nome, telefone, email, pasta, opt_in, blacklist, origem e observações.",
    ),
    (
        "Como ver o histórico de envios?",
        "Vá em 'Histórico' no menu lateral. Você vê cada mensagem enviada com: "
        "data/hora, campanha, contato, status (enviado, simulação, erro) e modo usado. "
        "Também é possível exportar o histórico em CSV.",
    ),
    (
        "O que são presets de velocidade (Seguro/Moderado/Rápido)?",
        "São configurações de intervalo entre mensagens:\n"
        "• Seguro: 60-120 segundos. Menor risco de bloqueio. Recomendado para listas grandes.\n"
        "• Moderado: 30-45 segundos. Equilíbrio entre velocidade e segurança.\n"
        "• Rápido: 10-20 segundos. Maior risco de bloqueio. Use com cuidado em listas pequenas.",
    ),
    (
        "O que é busca de leads?",
        "A tela 'Buscar leads' abre o Google Maps no navegador e permite colar resultados de busca. "
        "O app extrai os telefones automaticamente do texto colado e importa para uma pasta de contatos.",
    ),
]


class HelpScreenMixin:
    def show_help(self) -> None:
        frame = self._screen("Ajuda e perguntas frequentes")

        search_var = tk.StringVar()
        search_row = ttk.Frame(frame)
        search_row.pack(fill="x", pady=(0, 12))
        ttk.Label(search_row, text="Buscar:").pack(side="left")
        ttk.Entry(search_row, textvariable=search_var, width=40).pack(side="left", padx=(8, 0))

        canvas = tk.Canvas(frame, background=getattr(self, "_ui_background", "#f6f7fb"), highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def configure_inner(_e: object = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def configure_canvas(e: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=e.width)

        def on_scroll(event: tk.Event) -> None:
            if event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")

        inner.bind("<Configure>", configure_inner)
        canvas.bind("<Configure>", configure_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind(
            "<Enter>",
            lambda _e: (
                canvas.bind_all("<MouseWheel>", on_scroll),
                canvas.bind_all("<Button-4>", on_scroll),
                canvas.bind_all("<Button-5>", on_scroll),
            ),
        )
        canvas.bind(
            "<Leave>",
            lambda _e: (
                canvas.unbind_all("<MouseWheel>"),
                canvas.unbind_all("<Button-4>"),
                canvas.unbind_all("<Button-5>"),
            ),
        )
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        faq_widgets: list[tuple[str, str, ttk.Frame]] = []

        for question, answer in FAQ:
            block = ttk.Frame(inner, style="Panel.TFrame", padding=14)
            block.pack(fill="x", pady=(0, 8), padx=2)
            ttk.Label(block, text=question, style="Panel.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w")
            ttk.Label(block, text=answer, style="Muted.TLabel", wraplength=840, justify="left").pack(
                anchor="w", pady=(6, 0)
            )
            faq_widgets.append((question.lower(), answer.lower(), block))

        def do_search(*_args: object) -> None:
            term = search_var.get().lower().strip()
            for q, a, block in faq_widgets:
                if not term or term in q or term in a:
                    block.pack(fill="x", pady=(0, 8), padx=2)
                else:
                    block.pack_forget()
            canvas.after(50, configure_inner)

        search_var.trace_add("write", do_search)
