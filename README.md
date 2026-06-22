# Mezzold Connect

Aplicação para Windows voltada à organização de contatos, campanhas e operações de mensageria, com controles de consentimento, modo de simulação, histórico e acompanhamento da saúde de números.

O repositório reúne dois componentes:

1. um aplicativo desktop em Python, Tkinter e SQLite;
2. um serviço local em Node.js e TypeScript para filas, cotas, horários de silêncio e score de saúde.

> O projeto é uma solução técnica em evolução. Envios reais dependem de configuração externa e devem respeitar consentimento, LGPD e as políticas do provedor utilizado.

## Objetivo

Centralizar tarefas operacionais que normalmente exigem conferências manuais: importar e organizar contatos, registrar autorização, preparar campanhas, simular envios, acompanhar falhas, controlar limites e manter um histórico para investigação e suporte.

## Contexto do desenvolvimento

O projeto foi desenvolvido para explorar problemas recorrentes de operação e suporte: organização de dados, reprodução de falhas, rastreabilidade de envios, validação de consentimento, execução de tarefas em segundo plano e integração entre interface, API, banco e fila.

Para processos seletivos, o projeto demonstra experiência com:

- análise de requisitos e regras operacionais;
- interfaces desktop;
- APIs REST;
- bancos SQLite e PostgreSQL;
- filas com Redis e BullMQ;
- validação e tratamento de erros;
- testes automatizados;
- segurança de credenciais e dados locais;
- empacotamento e instalação no Windows.

## Funcionalidades do aplicativo desktop

- autenticação local e perfis de acesso;
- cadastro, edição, exclusão e organização de contatos em pastas;
- importação de contatos em CSV, TXT e XLSX;
- exportação de contatos e histórico em CSV;
- normalização de telefones e prevenção de duplicidades;
- registro de opt-in, opt-out, origem do consentimento e blacklist;
- criação, agendamento, pausa, retomada e cancelamento de campanhas;
- mensagens alternativas e intervalos configuráveis;
- modo de simulação ativo por padrão;
- envio pela API oficial da Meta, quando configurada;
- modo manual assistido por link `wa.me`;
- integração experimental com uma sessão local do WhatsApp Web;
- histórico de envios, falhas e simulações;
- análise de risco antes da campanha;
- aquecimento e score de saúde de números;
- pausa automática em situações previstas pelas regras do sistema;
- execução em segundo plano e integração com a bandeja do Windows;
- backup do banco SQLite;
- tela de ajuda, status de conexão e verificação de atualizações.

## Serviço Node.js

O serviço TypeScript implementa uma API local para registrar números, iniciar ou pausar aquecimento, controlar cotas, respeitar horários de silêncio, enfileirar envios e calcular um score de saúde.

Principais comportamentos:

- cota inicial de 20 envios por dia;
- crescimento diário padrão de 20%, limitado pela cota máxima;
- agendamento com Redis e BullMQ;
- persistência em PostgreSQL;
- variação de mensagens com variáveis e spintax;
- postergação de jobs durante horários de silêncio;
- registro de eventos de envio;
- score baseado em entrega, falha, resposta e opt-out;
- pausa automática quando o score fica abaixo de 40;
- provedor de desenvolvimento baseado em webhook;
- dashboard local em `http://localhost:3000`.

## Tecnologias

### Desktop

- Python 3.10+;
- Tkinter;
- SQLite;
- Selenium, para o modo experimental de WhatsApp Web;
- Pystray e Pillow, para o ícone da bandeja;
- PyInstaller, para geração do executável.

### Serviço local

- Node.js 20.19+;
- TypeScript;
- Fastify;
- PostgreSQL 16;
- Redis 7;
- BullMQ;
- Zod;
- Luxon;
- Vitest;
- Docker Compose.

## Estrutura

```text
MezzoldConnect/
├── main.py                    # entrada do aplicativo desktop
├── ui.py                      # interface principal
├── auth.py                    # autenticação e perfis
├── database.py                # banco SQLite e configurações
├── contacts.py                # contatos, pastas e importação
├── campaigns.py               # campanhas, agenda e histórico
├── compliance.py              # análise de risco
├── warmup.py                  # aquecimento no desktop
├── whatsapp.py                # provedores de envio
├── screens/                   # telas complementares
├── tests/                     # testes do aplicativo desktop
├── installer/                 # scripts de instalação
├── src/                       # serviço Node.js/TypeScript
├── migrations/               # banco PostgreSQL
├── test/                      # testes do serviço Node.js
├── scripts/smoke-test.ts      # teste ponta a ponta local
├── compose.yaml               # PostgreSQL e Redis
└── Mezzold Connect.spec       # configuração do PyInstaller
```

## Executar o aplicativo desktop

### Pré-requisitos

- Windows 10 ou 11;
- Python 3.10 ou superior;
- Tkinter disponível na instalação do Python.

Clone o repositório:

```powershell
git clone https://github.com/ViniciusNoetzold/MezzoldConnect.git
cd MezzoldConnect
```

Crie e ative um ambiente virtual:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependências usadas pelos recursos opcionais e pelo empacotamento:

```powershell
py -m pip install --upgrade selenium pystray pillow pyinstaller
```

Execute:

```powershell
py main.py
```

Os dados locais são criados na pasta `data/`, que não deve ser versionada.

### Credencial administrativa de bootstrap

O código não possui senha administrativa fixa. Quando o fluxo especial de bootstrap for necessário em um ambiente autorizado, forneça a credencial apenas durante a execução:

PowerShell:

```powershell
$env:MEZZOLD_MASTER_BOOTSTRAP_PASSWORD="defina-uma-senha-segura"
py main.py
```

Prompt de Comando do Windows:

```cmd
set MEZZOLD_MASTER_BOOTSTRAP_PASSWORD=defina-uma-senha-segura
py main.py
```

Linux:

```bash
export MEZZOLD_MASTER_BOOTSTRAP_PASSWORD="defina-uma-senha-segura"
python3 main.py
```

Se a variável não estiver definida, o fluxo de bootstrap é bloqueado e a aplicação informa que a credencial precisa ser configurada. Não há valor padrão ou fallback.

Não salve essa senha no repositório, em scripts versionados ou em capturas de tela.

## Gerar executável e instalador

Gerar `dist/Mezzold Connect.exe`:

```powershell
.\build.ps1
```

Gerar o instalador:

```powershell
.\installer\build-installer.ps1
```

Os executáveis gerados são artefatos de release e não devem permanecer no histórico do Git. Publique-os na seção [Releases](https://github.com/ViniciusNoetzold/MezzoldConnect/releases).

## Executar o serviço Node.js

### Pré-requisitos

- Node.js 20.19 ou superior;
- Docker Desktop com suporte a contêineres Linux.

Instale as dependências e crie o arquivo local de configuração:

```powershell
npm ci
Copy-Item .env.example .env
```

Suba PostgreSQL e Redis:

```powershell
docker compose up -d
```

Execute as migrações:

```powershell
npm run migrate
```

Abra três terminais:

```powershell
npm run dev
```

```powershell
npm run worker
```

```powershell
npm run dev:webhook
```

Depois, acesse:

- dashboard: `http://localhost:3000`;
- saúde da API: `http://localhost:3000/healthz`;
- saúde do webhook de teste: `http://localhost:4000/healthz`.

Para validar o fluxo local:

```powershell
npm run smoke
```

## Endpoints da API

| Método | Rota | Finalidade |
|---|---|---|
| `GET` | `/` | dashboard HTML local |
| `GET` | `/healthz` | disponibilidade da API |
| `POST` | `/numbers` | cadastrar um número |
| `POST` | `/numbers/:id/warmup/start` | iniciar o aquecimento e enfileirar destinatários |
| `POST` | `/numbers/:id/warmup/pause` | pausar o número e seus agendamentos |
| `GET` | `/numbers/:id/status` | consultar número, agenda, cota e horário permitido |
| `GET` | `/numbers/:id/health` | calcular e gravar um snapshot de saúde |
| `GET` | `/warmup/report` | consolidar o relatório dos números |

### Verificar a API

```http
GET /healthz
```

```json
{
  "ok": true
}
```

### Cadastrar um número

```http
POST /numbers
Content-Type: application/json
```

```json
{
  "phoneNumber": "+5511999999999",
  "displayName": "Número de teste",
  "maxDailyQuota": 500,
  "timezone": "America/Sao_Paulo",
  "quietHoursStart": "00:00",
  "quietHoursEnd": "07:00",
  "webhookUrl": "http://localhost:4000/messages"
}
```

A resposta usa a estrutura real abaixo. UUIDs e datas são gerados em tempo de execução:

```json
{
  "number": {
    "id": "6f93433a-d5bf-4a2d-b63c-c17f0f0cb456",
    "phoneNumber": "+5511999999999",
    "displayName": "Número de teste",
    "status": "registered",
    "dailyQuota": 20,
    "maxDailyQuota": 500,
    "rampRate": 0.2,
    "timezone": "America/Sao_Paulo",
    "quietHoursStart": "00:00:00",
    "quietHoursEnd": "07:00:00",
    "providerConfig": {
      "webhookUrl": "http://localhost:4000/messages"
    },
    "warmupStartedAt": null,
    "pausedAt": null,
    "autoPausedReason": null,
    "createdAt": "2026-06-22T12:00:00.000Z",
    "updatedAt": "2026-06-22T12:00:00.000Z"
  }
}
```

### Iniciar o aquecimento

```http
POST /numbers/6f93433a-d5bf-4a2d-b63c-c17f0f0cb456/warmup/start
Content-Type: application/json
```

```json
{
  "recipients": [
    "+5511888887777"
  ],
  "template": "{Oi|Olá} {{name}}, teste da plataforma {{company}}.",
  "variables": {
    "name": "Ana",
    "company": "Mezzold Connect"
  },
  "perRecipientVariables": {},
  "metadata": {
    "source": "readme"
  },
  "sendSpacingSeconds": 60
}
```

A resposta contém `number`, `schedule` e os jobs realmente agendados:

```json
{
  "number": {
    "id": "6f93433a-d5bf-4a2d-b63c-c17f0f0cb456",
    "status": "warming"
  },
  "schedule": {
    "numberId": "6f93433a-d5bf-4a2d-b63c-c17f0f0cb456",
    "dailyQuota": 20,
    "sentCount": 0,
    "status": "pending"
  },
  "scheduledJobs": [
    {
      "recipient": "+5511888887777",
      "jobId": "1",
      "runAt": "2026-06-22T12:01:00.000Z"
    }
  ]
}
```

Os objetos completos também incluem IDs e datas gerados pelo banco. Os exemplos acima omitem somente campos dinâmicos repetidos para facilitar a leitura.

### Erro de validação

O formato real de erro de entrada é:

```json
{
  "error": "validation_error",
  "details": [
    {
      "path": "phoneNumber",
      "message": "String must contain at least 1 character(s)"
    }
  ]
}
```

## Testes

### Desktop

```powershell
py -m unittest discover -s tests -p "test_*.py" -v
```

### Serviço Node.js

```powershell
npm test
npm run build
```

### Fluxo local completo

Com API, worker, webhook, PostgreSQL e Redis em execução:

```powershell
npm run smoke
```

## Segurança e privacidade

- o modo de simulação fica ativo por padrão;
- tokens da Meta podem ser fornecidos por `MEZZOLD_WHATSAPP_TOKEN`;
- no Windows, tokens salvos pela interface usam proteção DPAPI;
- `.env`, bancos SQLite, logs, perfis de navegador e dados locais são ignorados pelo Git;
- senhas de usuários são derivadas com PBKDF2 e salt aleatório;
- não existe credencial administrativa padrão no código;
- contatos sem opt-in ou em blacklist são bloqueados pelas regras do desktop;
- o modo WhatsApp Web é experimental e não substitui a API oficial.

Nunca utilize dados reais de clientes em exemplos públicos, testes ou capturas de tela.

## Aprendizados e desafios técnicos

- separar interface, persistência e regras de negócio em um aplicativo desktop;
- preservar consistência durante pausa, retomada e reprocessamento de campanhas;
- proteger tokens sem gravá-los em texto puro;
- normalizar contatos importados de formatos diferentes;
- aplicar regras de consentimento antes do envio;
- coordenar API, banco, fila, worker e provedor externo;
- reservar cota de forma transacional para jobs concorrentes;
- respeitar fusos horários e janelas de silêncio;
- transformar eventos de entrega em um score de saúde;
- empacotar uma aplicação Python para Windows e manter atualização segura.

O desafio central é manter rastreabilidade entre o que foi solicitado, enfileirado, enviado, adiado, bloqueado ou simulado. Essa rastreabilidade é importante tanto para QA quanto para suporte técnico e investigação de incidentes.

## Limitações atuais

- o aplicativo desktop é direcionado ao Windows;
- o envio real depende de credenciais e serviços externos;
- o provedor Node.js incluído é um webhook genérico de desenvolvimento;
- a API local não possui autenticação;
- o modo WhatsApp Web é experimental e sensível a mudanças na interface do site;
- desktop e serviço Node.js ainda possuem bancos e fluxos independentes;
- testes reais com a Meta exigem conta, número e template aprovados.

## Melhorias futuras

Possíveis evoluções, ainda não implementadas:

- unificar os fluxos de dados do desktop e do serviço Node.js;
- adicionar autenticação à API local;
- ampliar os testes de integração com PostgreSQL, Redis e worker;
- automatizar a publicação de instaladores em GitHub Releases;
- adicionar observabilidade estruturada para API e filas;
- reduzir o acoplamento da interface principal em módulos menores.

## Demonstração e capturas pendentes

Produza manualmente, sempre com dados fictícios:

1. `01-login.png`: tela de login;
2. `02-dashboard-desktop.png`: dashboard principal;
3. `03-contatos-em-pastas.png`: contatos organizados em pastas;
4. `04-importacao-contatos.png`: importação de uma planilha de exemplo;
5. `05-campanha-simulacao.png`: campanha em modo de simulação;
6. `06-analise-risco.png`: análise de risco;
7. `07-historico-envios.png`: histórico com diferentes status;
8. `08-saude-numeros.png`: aquecimento e score de saúde;
9. `09-configuracoes-seguras.png`: configurações com credenciais ocultas;
10. `10-dashboard-node.png`: dashboard web do serviço Node.js;
11. `11-endpoint-api.png`: resposta de endpoint no Postman ou Insomnia;
12. `12-testes-automatizados.png`: testes concluídos no terminal.

Salve as imagens em `docs/images/`. Oculte tokens, credenciais, IDs da Meta, telefones, nomes de clientes, mensagens reais, URLs privadas, caminhos locais e informações de sessão do navegador.

## Documentação complementar

- [Configuração do serviço Node.js](README.node-service.md)
- [Instruções adicionais de setup](SETUP.md)
- [Releases do aplicativo](https://github.com/ViniciusNoetzold/MezzoldConnect/releases)
