# Mezzold Connect v2.1.0

Esta versão conclui a migração funcional da V1 para a interface V2 em Flet, mantendo o backend desktop nativo em Python/SQLite.

## Destaques

- Migração de autenticação/RBAC, contatos, pastas, importação, leads, campanhas, agenda, risco, histórico, configurações e manutenção.
- Warmup nativo completo, sem serviço externo separado.
- Compatibilidade copy-once com o banco legado, backup pré-migração, schema incremental e relatório `migration-report.json`.
- Sidebar recolhível com animação curta e transições entre telas desativadas.
- Fluxos de API Oficial, WhatsApp Web experimental, Manual Assistido e dry-run.
- Worker, bandeja do Windows, backup, exportação Firebird, verificador de atualização e instalador preservando dados.

## Validação

- 62/62 testes automatizados aprovados.
- Login e 13 telas autenticadas percorridos em navegador real com zero erros/avisos de console.
- Fluxo completo risco → confirmação → campanha dry-run concluído.
- `MezzoldConnect.exe` iniciado nativamente, com schema 4 íntegro, backup e exportação funcionando.
- Instalador v2.1.0 aberto e inspecionado sem executar a instalação.

## Artefatos

- `MezzoldConnect.exe`
  SHA-256: `E9D93F36869E046E7E3C6D83309908E26E6DE69B6AA247AABF4C89FC134F4059`
- `Mezzold.Connect.Setup.v2.1.0.exe`
  SHA-256: `A28573BC980721671EC4AEE06AB0B24F50993CA45FD08DCEC9C6730834A281E2`

## Limitações conhecidas

- Envio Meta real e autenticação QR do WhatsApp Web não foram executados sem credenciais/número de produção; contratos e estados foram testados com mocks e dry-run.
- Os executáveis ainda não têm assinatura Authenticode, portanto o Windows SmartScreen pode exibir um aviso.
- A checagem automática requer configurar a URL do manifesto na tela Atualizações. Para esta release, use:
  `https://github.com/ViniciusNoetzold/MezzoldConnect/releases/latest/download/update-manifest.json`
