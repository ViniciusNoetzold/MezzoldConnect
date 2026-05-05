# Mezzold Connect

O Mezzold Connect é um aplicativo para Windows que ajuda a organizar clientes, campanhas e envios pelo WhatsApp.

Ele foi pensado para rodar na máquina do cliente. Você abre a tela para configurar tudo e, depois, o app pode ficar trabalhando em segundo plano quando o computador ligar.

## Como Instalar

Use o instalador:

```powershell
installer\Mezzold Connect Setup.exe
```

O instalador faz quatro coisas:

- copia o aplicativo para a pasta do usuário no Windows;
- cria atalho na Área de Trabalho;
- cria atalho no Menu Iniciar;
- configura o envio em segundo plano para iniciar junto com o computador.

## Como Abrir

Depois de instalar, abra pelo atalho **Mezzold Connect**.

Na primeira vez, crie o primeiro acesso do sistema. Depois, entre com usuário e senha.

## Como o App Trabalha em Segundo Plano

Quando a opção **Começar sozinho quando ligar o computador** estiver ativa, o Windows inicia o app em modo invisível.

Nesse modo, ele:

- verifica campanhas agendadas;
- retoma campanhas que pararam no meio;
- respeita os limites configurados;
- registra tudo no histórico.

Para mudar contatos, mensagens, números e configurações, abra a janela normal do aplicativo.

## Clientes

Use a tela **Clientes** para cadastrar quem pode receber mensagens.

Campos mais importantes:

- **Nome do cliente**: nome que aparece nos relatórios.
- **Telefone com DDD**: pode usar espaços, parênteses, hífen ou `+55`.
- **Cliente autorizou receber mensagens**: marque apenas quando houver autorização.
- **Bloquear este cliente para envios**: use quando a pessoa pediu para não receber mais mensagens.
- **Onde autorizou receber mensagens**: exemplo: formulário, WhatsApp, contrato, atendimento.
- **Comprovante ou observação da autorização**: anote qualquer detalhe que ajude a provar a autorização.

## Importar Clientes

Use **Importar clientes** para trazer uma planilha CSV ou Excel.

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

O app tenta limpar telefones, evitar repetidos e ignorar linhas inválidas.

## Nova Campanha

Use **Nova campanha** para preparar a mensagem.

Você escolhe:

- nome da campanha;
- tipo de mensagem;
- modelo aprovado na Meta, quando for envio automático oficial;
- mensagem principal;
- outras versões da mensagem;
- clientes autorizados.

Se as pausas automáticas estiverem ligadas, use pelo menos 3 versões de mensagem.

Para separar versões longas, use uma linha assim:

```text
---
```

## Agenda de Envios

Use **Agenda de envios** para escolher quando enviar.

Você pode:

- agendar;
- enviar agora;
- pausar envio;
- cancelar envio.

Se o computador desligar ou perder internet, o app salva o que já foi feito e tenta retomar depois.

## Aquecimento dos Números

Use **Aquecer números** antes de usar um número em campanhas maiores.

O aquecimento começa com poucos envios por dia e aumenta aos poucos:

- começa em 20 envios por dia;
- cresce 20% por dia;
- nunca passa do limite máximo configurado;
- não envia entre 00:00 e 07:00 por padrão;
- calcula um score de saúde de 0 a 100;
- pausa automaticamente números com score abaixo de 40.

A tela mostra:

- score do número;
- quantidade que pode enviar hoje;
- quanto já enviou;
- horário em que não deve enviar;
- se o número já pode ser usado em campanhas.

## Conferir Risco

Use **Conferir risco** para revisar campanhas antes de enviar.

O app observa pontos como:

- clientes sem autorização;
- clientes bloqueados;
- falta de prova de autorização;
- volume alto;
- histórico de erro;
- uso fora da API oficial.

O risco não garante que nada dará errado, mas ajuda a evitar problemas óbvios.

## Histórico

Use **Histórico de envios** para ver o que aconteceu.

Ali aparecem envios feitos, erros, simulações e links manuais do WhatsApp.

## Configurações

Use **Configurações** para ajustar:

- modo de envio;
- token e IDs da Meta;
- modo teste;
- limite diário;
- pausas automáticas;
- aquecimento dos números;
- licença;
- backup.

### Modo Teste

Com **Modo teste** ligado, o app registra os envios sem mandar mensagem de verdade.

Use isso para treinar, revisar campanha e testar a operação.

### Modo Manual

O modo manual abre um link do WhatsApp para a pessoa concluir o envio.

Ele não automatiza WhatsApp Web, QR Code ou disparo em massa fora da API oficial.

## Backup

Na tela **Configurações**, clique em **Criar backup** para salvar uma cópia do banco local.

## Para Desenvolvedores

Rodar em desenvolvimento:

```powershell
python main.py
```

Gerar o aplicativo:

```powershell
.\build.ps1
```

Gerar o instalador:

```powershell
.\installer\build-installer.ps1
```
