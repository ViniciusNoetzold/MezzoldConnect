# Mezzold Connect v2.1.1

Correção incremental sobre a v2.1.0, com foco no primeiro acesso, navegação e WhatsApp Web local.

## Correções

- O modo `Ctrl+Alt+Shift+M` agora aceita por padrão o usuário `000` e a senha `M3zz0ld`; a variável `MEZZOLD_MASTER_BOOTSTRAP_PASSWORD` continua disponível como override administrativo.
- A sidebar preserva o estado expandido/recolhido entre rotas e ignora eventos atrasados da tela desmontada, eliminando o piscar e o pulo após o clique.
- Chrome e Edge usam classes concretas do Selenium 4.47, sem depender dos lazy imports que faltavam no executável v2.1.0.
- O build inclui e verifica os WebDrivers Chrome/Edge/Chromium e `selenium-manager.exe` antes de gerar a distribuição.
- O instalador encerra instâncias anteriores antes da troca atômica do executável e mantém os dados em `C:\MezzoldConnect\data`.

## Validação

- 73/73 testes automatizados aprovados.
- Login master padrão validado em interface real.
- Sidebar validada em navegação real, com 0 erros e 0 avisos no console.
- Chrome real abriu `web.whatsapp.com`, usando perfil persistente, e chegou ao estado `Aguardando QR Code`.
- O diagnóstico executado dentro do próprio `.exe` empacotado retornou código 0.
- Nenhuma mensagem real foi enviada durante os testes.

## Artefatos

- `MezzoldConnect.exe`
  SHA-256: `7C61B9295E600CBBAB66D68DD7841BE0F0690F2BC52EC21033E4992D09243631`
- `Mezzold.Connect.Setup.v2.1.1.exe`
  SHA-256: `9C9CA8B78F516680D69D837D98756B1BAFD76533EE79DCB4B7617844BE6EA6BE`

## Observações

- A leitura do QR Code deve ser feita pelo titular da conta no celular.
- Os executáveis ainda não possuem assinatura Authenticode, então o Windows SmartScreen pode apresentar um aviso.
