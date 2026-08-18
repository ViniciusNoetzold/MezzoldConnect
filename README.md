# Mezzold Connect V2

## Visao Geral
Mezzold Connect V2 e uma aplicacao desktop para gestao de campanhas de mensagens WhatsApp, contatos e automacoes. Reescrita com interface moderna usando **Flet (Flutter)**, substituindo o Tkinter legado.

## Estrutura de Pastas
```
MezzoldConnect_V2/
  main.py              # Ponto de entrada e roteamento
  database.py          # SQLite + migracao de schema
  auth.py              # Autenticacao e perfis de usuario
  campaigns.py         # Logica de campanhas
  contacts.py          # Gestao de contatos e pastas
  whatsapp.py          # Integracao Meta Cloud API
  compliance.py        # Analise de risco e compliance
  warmup.py            # Aquecimento de numeros
  background_worker.py # Worker de envio em background
  startup.py           # Inicializacao com Windows
  network.py           # Verificacao de conexao
  app_update.py        # Verificacao de atualizacoes
  screens/             # Telas da aplicacao (Flet Views)
    login.py
    dashboard.py
    contacts.py
    campaigns.py
    import_contacts.py
    schedule.py
    risk.py
    history.py
    health.py
    settings.py
  installer/           # Instalador oficial Windows
    installer_app.py   # GUI do instalador (tkinter)
    export_firebird.py # Exportacao SQL/Firebird
```

## Instalacao
Execute o instalador `Mezzold.Connect.Setup.v2.0.0.exe` da pasta `dist/`.

O instalador cria a seguinte estrutura no seu disco:
```
C:\MezzoldConnect\
  app\                         # Executavel principal
    MezzoldConnect.exe
  data\                        # Banco de dados e arquivos
    mezzold_connect.sqlite3    # Banco SQLite principal
    mezzold_connect_firebird.sql  # Schema compativel Firebird/DBeaver
    media\                     # Midias de campanhas
    imports\                   # Planilhas importadas
    exports\                   # Exportacoes
    backups\                   # Backups automaticos
    logs\                      # Logs do sistema
  scripts\                     # Utilitarios de manutencao
    backup_banco.bat           # Fazer backup rapidamente
    exportar_dados_firebird_sql.bat  # Exportar para SQL/Firebird
    abrir_pasta_dados.bat      # Abrir pasta de dados
    export_firebird.py         # Script Python de exportacao
  uninstall.ps1               # Desinstalador
```

## Banco de Dados
O banco e SQLite3, armazenado em `C:\MezzoldConnect\data\mezzold_connect.sqlite3`.

### Visualizacao no Firebird / DBeaver / FlameRobin
O instalador gera automaticamente um arquivo `mezzold_connect_firebird.sql` com o schema e dados exportados em SQL padrao ANSI, compativel com:
- **DBeaver** (abrir como script SQL)
- **FlameRobin**
- **Firebird** (via isql)
- Qualquer outro SGBD que aceite SQL padrao

Para atualizar o export, execute `C:\MezzoldConnect\scripts\exportar_dados_firebird_sql.bat`.

## Telas Disponiveis
| Rota | Descricao |
|---|---|
| `/` | Login e Cadastro |
| `/dashboard` | Visao geral e metricas |
| `/contacts` | Gestao de contatos e pastas |
| `/campaigns` | Criar e listar campanhas |
| `/import_contacts` | Importar planilhas Excel/CSV/TXT |
| `/schedule` | Central de envios e agendamentos |
| `/risk` | Analise de risco e compliance |
| `/history` | Historico completo de envios |
| `/health` | Saude e aquecimento de numeros |
| `/settings` | Configuracoes, API Meta, usuarios |

## Perfis de Usuario
- **Admin**: Acesso total (todas as telas, gerenciamento de usuarios)
- **Equipe**: Acesso a campanhas, contatos e saude do numero
- **Cliente**: Acesso basico

## Tecnologias
- Python 3.12+
- Flet 0.86+
- SQLite3
- Meta Cloud API (WhatsApp Business)

## Releases
Disponiveis em: https://github.com/ViniciusNoetzold/MezzoldConnect/releases