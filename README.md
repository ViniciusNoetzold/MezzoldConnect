# Mezzold Connect v2

Aplicativo desktop Windows para contatos, campanhas WhatsApp, compliance e aquecimento nativo de números. A interface usa Flet; dados, worker, agenda e warmup continuam no processo Python/SQLite do próprio aplicativo.

## Executar em desenvolvimento

No PowerShell, dentro desta pasta:

```powershell
py -m venv .venv_build
.\.venv_build\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv_build\Scripts\python.exe main.py
```

O atalho `Iniciar_V2.bat` usa o mesmo ambiente. Para isolar dados durante testes:

```powershell
$env:MEZZOLD_DATA_DIR = "$env:TEMP\mezzold-connect-teste"
$env:MEZZOLD_DB_PATH = "$env:MEZZOLD_DATA_DIR\mezzold_connect.sqlite3"
.\.venv_build\Scripts\python.exe main.py
```

Em uma instalação nova, pressione `Ctrl+Alt+Shift+M` no login e use o usuário reservado `000` com a senha padrão `M3zz0ld`. Esse acesso master continua bloqueado no login comum e só é aceito depois da ativação do modo administrativo pelo atalho. Para substituir a senha padrão em uma instalação gerenciada, defina `MEZZOLD_MASTER_BOOTSTRAP_PASSWORD` antes de iniciar o aplicativo. Usuários comuns são criados depois em Configurações por um administrador.

## Dados e migração da v1

- Instalação v2: `C:\MezzoldConnect\data\mezzold_connect.sqlite3`.
- Origem v1 reconhecida: `%LOCALAPPDATA%\Mezzold Connect\data\mezzold_connect.sqlite3`.
- Se a v2 ainda não tiver banco, a primeira inicialização faz uma cópia consistente da v1 com a API de backup do SQLite; a origem nunca é alterada.
- Antes de qualquer migração incremental, é criado um backup em `data\backups` e a integridade é verificada.
- Um banco v2 já existente nunca é sobrescrito automaticamente pelo banco legado.
- Token protegido com DPAPI continua utilizável pelo mesmo usuário do Windows.

Comandos de manutenção do executável:

```powershell
.\MezzoldConnect.exe --initialize-database
.\MezzoldConnect.exe --backup-database "C:\MezzoldConnect\data\backups"
.\MezzoldConnect.exe --export-firebird "C:\MezzoldConnect\data\mezzold_connect_firebird.sql"
.\MezzoldConnect.exe --background
.\MezzoldConnect.exe --minimized
```

## Telas

| Rota | Função |
|---|---|
| `/` | Login, bootstrap autorizado e troca obrigatória de senha |
| `/dashboard` | Métricas e campanhas recentes |
| `/contacts` | Contatos, pastas, opt-in, blacklist e exportação |
| `/import_contacts` | Importação CSV, TXT e XLSX |
| `/lead_search` | Coleta manual assistida e deduplicação de leads |
| `/campaigns` | Criação imediata/agendada, templates, variantes e mídia |
| `/schedule` | Gestão, edição, pausa, retomada, cancelamento e reenvio |
| `/risk` | Score e recomendações de compliance |
| `/history` | Logs, links manuais, telefones usados e exportação CSV |
| `/health` | Warmup nativo e saúde dos números |
| `/connection` | Internet e sessão local do WhatsApp Web |
| `/updates` | Canal, manifesto e download de atualização |
| `/help` | FAQ pesquisável |
| `/settings` | Conta, aparência, provedores, segurança, licença e usuários |

A tela de Saúde do Número é restrita a equipe, administrador e Mezzold Master. A gestão de usuários é restrita a administrador/master.

## Segurança dos envios

- `dry-run` começa ligado; simulações ficam identificadas no histórico.
- Contatos sem opt-in ou em blacklist são bloqueados antes do provedor.
- API Meta, WhatsApp Web experimental e modo manual assistido são selecionáveis por campanha.
- Envio real por WhatsApp Web exige confirmação explícita na interface.
- Token Meta pode vir do ambiente ou do armazenamento DPAPI; não é salvo em texto puro.
- O modo Web usa perfil local persistente e tenta Chrome, depois Edge.

## Testes e build Windows

```powershell
.\.venv_build\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\build.ps1
.\build_release.ps1
```

Artefatos esperados:

- `dist\MezzoldConnect.exe`
- `dist\Mezzold.Connect.Setup.v2.1.1.exe`

O instalador chama o mecanismo de migração do próprio aplicativo, preserva `C:\MezzoldConnect\data`, cria atalhos e grava utilitários de backup/exportação que não dependem de uma instalação global do Python.

O inventário funcional e o estado da migração ficam em `MIGRATION_CHECKLIST.md`.

## Publicação e atualizações

A release atual usa a branch `v2-flet`, a tag `v2.1.1` e anexa os dois executáveis, `update-manifest.json` e `RELEASE_NOTES_v2.1.1.md`. Não reutilize nem mova as tags antigas `v2.0.0` e `v2.1.0`.

Para habilitar a checagem pelo canal estável, configure na tela Atualizações:

`https://github.com/ViniciusNoetzold/MezzoldConnect/releases/latest/download/update-manifest.json`

O manifesto aponta para o instalador versionado e inclui seu SHA-256. Os binários atuais não possuem assinatura Authenticode; até a configuração de um certificado de assinatura de código, o Windows SmartScreen pode exibir um aviso.
