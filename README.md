# Manual de uso - Mezzold Connect

O Mezzold Connect é um aplicativo desktop para organizar contatos, campanhas, agendamentos, histórico e envios pelo WhatsApp.

## Requisitos

- Windows com internet ativa.
- Python instalado para rodar em desenvolvimento.
- WhatsApp Business Cloud API para envio oficial automático, ou modo manual assistido para clientes sem API.

Sem internet, o app ainda abre e permite consultar dados locais, mas não consegue enviar campanhas, abrir links `wa.me`, validar páginas oficiais ou usar a API.

## Como abrir

```powershell
python main.py
```

Na primeira abertura, crie o usuário administrador. Depois faça login normalmente.

## Telas principais

### Dashboard

Mostra resumo de contatos, campanhas, agendamentos, envios e falhas.

### Contatos

Use para cadastrar, editar e excluir contatos.

Campos importantes:

- **Nome**: nome do cliente.
- **Número**: pode ser digitado com espaços, parênteses, hífen ou `+55`; o app normaliza automaticamente.
- **Grupo/lista**: ajuda a segmentar campanhas.
- **Contato autorizou mensagens**: deve estar marcado para envio.
- **Blacklist**: bloqueia contatos que pediram descadastro ou não devem receber mensagens.
- **Origem/data do opt-in**: registre de onde veio a autorização.

Exemplo aceito:

```text
(55) 54 99150-9999
```

O app salva no formato:

```text
5554991509999
```

### Importar contatos

Importa CSV ou Excel `.xlsx`.

Colunas recomendadas:

- `nome`
- `telefone`
- `email`
- `grupo`
- `opt_in`
- `origem`
- `categoria`
- `data_opt_in`
- `prova`

O app remove duplicados, valida números e ignora linhas inválidas.

### Criar campanha

Crie o nome, categoria, template, mensagem e lista de contatos.

Se o **Disparo inteligente** estiver ativo, a campanha precisa ter pelo menos 3 mensagens diferentes. Coloque uma mensagem principal e as outras no campo **Variações adicionais de mensagem**.

Para separar textos longos, use uma linha com:

```text
---
```

### Agendar envio

Permite agendar, enviar agora, pausar ou cancelar campanhas.

Se o app for fechado durante uma campanha, os contatos já enviados ficam registrados no banco. Ao abrir novamente, campanhas que estavam com status `enviando` são retomadas a partir dos contatos pendentes, desde que haja internet.

### Risco

Mostra o risco por campanha em porcentagem.

O cálculo considera:

- contatos sem opt-in;
- blacklist;
- opt-out;
- ausência de prova de consentimento;
- template ausente;
- janela de 24h;
- volume diário;
- intervalo de envio;
- modo sem API oficial;
- histórico de falhas.

Esse score não garante ausência de bloqueio. Ele é uma camada preventiva.

### Histórico

Mostra envios, falhas, pendências manuais e erros.

Use **Números já enviados** para ver quais números já receberam ou entraram na fila manual.

No modo manual assistido, use **Abrir link manual** para abrir o WhatsApp com a mensagem preparada.

## Configurações

### Modo de envio

- `official_api`: usa WhatsApp Business Cloud API ou provedor oficial.
- `manual_assisted`: gera links `wa.me` e registra pendência manual. Não automatiza WhatsApp Web, QR Code ou disparos em massa.

### Internet

Use **Testar conexão** para verificar se o computador está conectado. O envio e os links oficiais dependem de internet.

### Inicializar com Windows

Marque **Iniciar automaticamente com o Windows** para abrir o Mezzold Connect ao ligar o computador.

### Disparo inteligente

Quando ativado:

- usa intervalos variáveis;
- cria pausas maiores a cada X envios;
- aplica limite diário inteligente;
- evita sessões contínuas por muitas horas;
- exige pelo menos 3 mensagens diferentes;
- registra qual texto e mídia foram usados.

Ele não embaralha letras, não camufla texto e não garante ausência de banimento.

### Salvar alterações

O botão **Salvar alterações** usa confirmação em duas etapas:

- senha do usuário logado;
- código numérico temporário mostrado na confirmação.

As configurações só são aplicadas depois dessa confirmação.

## Políticas oficiais

Leia antes de vender ou operar campanhas:

- Política oficial do WhatsApp: https://www.whatsapp.com/legal/business-policy/
- Documentação da Cloud API: https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview

## Backup

Na tela de configurações, clique em **Criar backup** para salvar uma cópia do banco SQLite.

## Gerar executável

Instale o PyInstaller:

```powershell
python -m pip install pyinstaller
```

Gere o executável:

```powershell
.\build.ps1
```

Depois teste em uma máquina limpa, sem Python instalado.
