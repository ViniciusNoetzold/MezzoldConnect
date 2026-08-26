# Checklist de migração V1 → V2

Inventário criado antes da migração, a partir do código executável da V1. O status final só deve ser marcado após implementação e teste na V2.

Legenda: `[ ]` pendente · `[x]` migrado e validado · `[~]` migrado, mas depende de credencial/serviço externo para validação real.

## 1. Autenticação, sessão e permissões

- [x] Login local com senha PBKDF2, usuário ativo/inativo e atualização do último acesso.
- [x] Perfis Cliente/Operador, Equipe, Administrador do cliente e Mezzold Master.
- [x] Bootstrap do Mezzold Master no modo `Ctrl+Alt+Shift+M`, usuário `000`, senha padrão `M3zz0ld` e override opcional por `MEZZOLD_MASTER_BOOTSTRAP_PASSWORD`.
- [x] Primeiro usuário, troca obrigatória de senha e alteração da própria senha.
- [x] Administração de usuários: criar, listar, ativar, desativar, redefinir senha e alterar perfil.
- [x] Proteções do usuário reservado Mezzold Master.
- [x] Bloqueio de rotas e recursos conforme o perfil autenticado.
- [x] Encerramento correto da sessão ao sair/trocar usuário.

## 2. Contatos, consentimento e pastas

- [x] Criar, consultar, editar e excluir contatos.
- [x] Normalizar/validar telefone e impedir duplicidades.
- [x] Registrar e editar e-mail, observações e pasta principal.
- [x] Registrar opt-in, origem, categoria, data e comprovante/observação de consentimento.
- [x] Registrar opt-out, blacklist e última mensagem recebida.
- [x] Criar, listar, renomear e excluir pastas sem perder contatos.
- [x] Buscar e filtrar contatos por pasta.
- [x] Visualizar todos, autorizados, blacklist e contatos já usados/enviados.
- [x] Importar CSV, TXT e XLSX, com upsert, deduplicação e relatório de erros.
- [x] Exportar contatos filtrados em CSV UTF-8.
- [x] Buscar leads no modo manual assistido: abrir Maps, colar texto, extrair, mesclar/deduplicar e importar selecionados.

## 3. Campanhas e agenda

- [x] Criar campanha a partir de uma pasta apenas com contatos autorizados.
- [x] Nome, categoria, mensagem principal, variações de texto, mídia principal e variações de mídia.
- [x] Template Meta e idioma configuráveis.
- [x] Modos API Oficial, WhatsApp Web experimental e Manual Assistido.
- [x] Delay mínimo/máximo, recomendação por volume e avisos de risco.
- [x] Início imediato ou agendamento com data/hora.
- [x] Listar e detalhar campanhas, destinatários e progresso.
- [x] Editar nome, agendamento, delay e modo antes/durante o fluxo permitido.
- [x] Iniciar, pausar, continuar e cancelar campanhas.
- [x] Impedir reinício indevido de campanha finalizada/cancelada.
- [x] Duplicar campanha para reenvio, preservando conteúdo e incrementando o nome.
- [x] Processar campanhas vencidas e retomar campanhas interrompidas.
- [x] Worker nativo em segundo plano com trava de instância única.
- [x] Controle de limite diário, duração da sessão, intervalos e pausas inteligentes.
- [x] Pausa/bloqueio por risco alto e falha de sessão WhatsApp Web.
- [x] Confirmação explícita antes de envio real pelo WhatsApp Web.

## 4. Provedores WhatsApp e segurança de envio

- [x] Modo simulação ativo por padrão e histórico distinto para simulado/real/erro.
- [~] API Meta Cloud: texto livre na janela de atendimento e template aprovado fora dela.
- [~] API Meta Cloud: mídia por URL e bloqueio claro para arquivo local em envio real.
- [x] Token via ambiente ou armazenamento DPAPI, sem persistência em texto puro.
- [~] WhatsApp Web local experimental com perfil persistente, QR Code e fallback Chrome/Edge.
- [~] Estado da sessão Web (abrindo, QR necessário, conectado, desconectado e erro).
- [x] Modo manual assistido com link `wa.me` e abertura pelo histórico.
- [x] Bloqueio de envio para blacklist e contato sem opt-in.
- [x] Log técnico sem expor token/segredo.

## 5. Risco, histórico e dashboard

- [x] Dashboard com contatos, opt-in, blacklist, campanhas, agendadas, enviadas e falhas.
- [x] Tabela de campanhas recentes e ação para envios atrasados.
- [x] Análise de risco por campanha, score, nível, notas e detalhes.
- [x] Histórico de mensagens com data, destinatário, telefone, status, modo, erro e link manual.
- [x] Relação consolidada de telefones já usados/enviados.
- [x] Exportação do histórico para CSV (complemento já documentado na V1, embora não estivesse conectado no código atual).

## 6. Warmup nativo

- [x] Cadastro, edição, ativação/desativação e exclusão de números WhatsApp.
- [x] Campos de provedor, Phone Number ID, qualidade, limite, meta diária/máxima e descanso.
- [x] Seleção obrigatória de grupo de contatos autorizados para aquecimento.
- [x] Cota inicial de 20/dia, crescimento diário de 20% e teto configurável.
- [x] Respeito a horário de descanso e exclusão de contatos já usados pelo número.
- [x] Execução nativa via SQLite e provedores do desktop, sem serviço externo separado.
- [x] Pausar aquecimento em andamento e registrar execução/eventos.
- [x] Score de saúde por entrega, falha, resposta e opt-out.
- [x] Auto-pausa abaixo de 40 e liberação para campanhas conforme score/piso.
- [x] Dashboard de números, últimos eventos e atualização manual da saúde.

## 7. Configurações e manutenção

- [x] Nome da empresa, tema, densidade e tamanho de fonte.
- [x] API Meta: versão, token, IDs, webhook, template, idioma e modo padrão.
- [x] Limite diário, intervalo global, presets de delay, dry-run e bloqueio por risco.
- [x] Parâmetros completos de pausas inteligentes e aquecimento.
- [~] Teste de internet e conexão/estado do WhatsApp Web.
- [x] Inicialização com Windows em worker ou minimizado na bandeja.
- [x] Backup SQLite escolhido pelo usuário e backup automático antes de migração.
- [x] Verificação de atualização por manifesto/canal e abertura segura da página de download.
- [x] Campos de licença/plano/validade (armazenamento; a V1 não implementa validação remota).
- [x] Confirmação sensível com senha e código antes de salvar configurações técnicas.
- [x] Links para política oficial WhatsApp e documentação Cloud API.

## 8. Desktop, ajuda e distribuição

- [x] Minimizar para a bandeja, restaurar, pausar/retomar envios, ver status e encerrar.
- [x] Logs unificados de app, worker, campanha e sessão WhatsApp.
- [x] Tela de Ajuda/FAQ com busca (o módulo existia órfão na V1; será conectado na V2).
- [x] Tela de Conexão WhatsApp (o módulo existia órfão na V1; será conectado na V2).
- [x] Tela de Atualizações integrada ao novo design.
- [x] Build Windows reproduzível com Flet, Selenium, pystray e Pillow incluídos.
- [x] Instalador reproduzível, atualização segura do executável, atalhos e preservação dos dados.

## 9. Compatibilidade de dados

- [x] Reconhecer automaticamente o banco legado em `%LOCALAPPDATA%\Mezzold Connect\data`.
- [x] Corrigir o caminho instalado da V2 para `C:\MezzoldConnect\data` (não `app\data`).
- [x] Migrar/copy-once com backup, verificação de integridade e sem sobrescrever banco V2 com dados.
- [x] Migrar schema incrementalmente, incluindo roles legadas, `image_path` e `security_preset`.
- [x] Recuperar com segurança bancos criados pelo schema incompatível do instalador V2 antigo.
- [x] Preservar IDs, usuários, contatos, pastas, campanhas, logs, settings, licença e warmup.
- [x] Registrar versão do schema e relatório da migração.

## 10. Validação obrigatória

- [x] Testes automatizados do backend e migração de dados.
- [x] Testes automatizados de sessão/RBAC e fluxos críticos.
- [x] Todas as telas renderizam sem exceção.
- [x] Navegação, cliques, inputs e diálogos principais validados tela a tela.
- [x] Dry-run ponta a ponta validado sem abrir provedor real.
- [x] Build final gerado.
- [x] Executável final inicia sem crash e cria/abre banco compatível.
- [x] Instalador final gerado e inspecionado.

## Fora do escopo por decisão arquitetural explícita

- Serviço opcional Node.js/TypeScript (PostgreSQL, Redis e BullMQ): a V1 o mantinha independente do desktop; o warmup solicitado é o módulo nativo Python/SQLite, sem serviço externo separado.
- Envio real para clientes em teste automatizado: depende de conta Meta, número, token e templates autorizados. A implementação será testada com mocks e dry-run; qualquer validação externa não disponível será registrada no resultado final.

## Resultado final — 26/08/2026

- Inventário V1: **93 itens**, sendo **88 concluídos e validados**, **5 implementados e validados localmente/mocados, mas dependentes de credencial ou sessão externa**, e **0 pendentes**.
- Testes automatizados: **62/62 aprovados** durante o build final.
- Interface: login e as 13 rotas autenticadas foram abertas em sessão Playwright limpa; navegação, sidebar recolhível, ausência de transição entre telas e fluxo risco → confirmação → dry-run passaram com **0 erros e 0 avisos de console**.
- Executável nativo: abriu como **Mezzold Connect v2.1.0**, criou banco íntegro no schema 4, gerou o relatório `migration-report.json`, executou backup/exportação com código 0 e minimizou para a bandeja ao fechar.
- Instalador: abriu como **Mezzold Connect v2.1.0 — Instalador**, exibiu os caminhos corretos de aplicativo/dados/backup e foi fechado sem alterar a instalação local.
- Build: `dist\MezzoldConnect.exe` — SHA-256 `E9D93F36869E046E7E3C6D83309908E26E6DE69B6AA247AABF4C89FC134F4059`.
- Instalador: `dist\Mezzold.Connect.Setup.v2.1.0.exe` — SHA-256 `A28573BC980721671EC4AEE06AB0B24F50993CA45FD08DCEC9C6730834A281E2`.
- Limitação externa dos itens `[~]`: envio Meta real e autenticação QR do WhatsApp Web não foram executados sem credenciais/número de produção. Os contratos, bloqueios de segurança, DPAPI, fallback Chrome/Edge, estados da sessão e dry-run foram cobertos por testes. Nenhum contato real recebeu mensagem.
- Distribuição: os dois binários estão sem assinatura Authenticode; o Windows SmartScreen pode exibir aviso até que um certificado de assinatura de código seja configurado.

## Correção v2.1.1 — 26/08/2026

- [x] Acesso master padrão restrito ao atalho `Ctrl+Alt+Shift+M`, usuário `000` e senha `M3zz0ld`.
- [x] Estado da sidebar preservado entre rotas, com eventos atrasados da View anterior ignorados e recolhimento normal ao sair com o mouse.
- [x] Chrome/Edge WebDriver e Selenium Manager incluídos e inspecionados dentro do executável PyInstaller.
- [x] Chrome real abriu `web.whatsapp.com` com perfil persistente e a tela chegou ao estado **Aguardando QR Code**, sem enviar mensagem.
- [x] Instalador encerra instâncias em execução antes da substituição atômica e preserva `C:\MezzoldConnect\data`.
- Testes automatizados: **73/73 aprovados** no build v2.1.1.
- Interface: autenticação master e navegação Dashboard → Conexão WhatsApp validadas; sidebar permaneceu expandida durante a troca e recolheu apenas na saída real do mouse; **0 erros e 0 avisos de console**.
- Build: `dist\MezzoldConnect.exe` — SHA-256 `7C61B9295E600CBBAB66D68DD7841BE0F0690F2BC52EC21033E4992D09243631`.
- Instalador: `dist\Mezzold.Connect.Setup.v2.1.1.exe` — SHA-256 `9C9CA8B78F516680D69D837D98756B1BAFD76533EE79DCB4B7617844BE6EA6BE`.
- O próprio `MezzoldConnect.exe --check-whatsapp-web-runtime` retornou código 0 após o empacotamento.
- Instalação local atualizada de 2.1.0 para 2.1.1; o binário anterior foi preservado como `MezzoldConnect.exe.bak`, e todas as contagens do banco permaneceram idênticas após a atualização (`integrity_check=ok`, schema 4).
- A leitura do QR Code continua sendo uma autenticação feita manualmente pelo titular do WhatsApp; nenhum contato real recebeu mensagem durante a validação.
