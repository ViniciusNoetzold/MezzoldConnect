# Mezzold Connect

Protótipo em Python para gerenciamento de campanhas e contatos para WhatsApp.

## O que o projeto faz hoje

- Cadastro e login de usuário no terminal.
- Cadastro e leitura de contatos em CSV.
- Normalização e validação básica de números brasileiros.
- Filtros por DDD, nome e limite de contatos.
- Blacklist para bloquear números.
- Controle de duplicados e histórico de envios.
- Simulação de envio de texto e mídia.
- Geração de logs de campanha.

## Observação importante

Neste estado inicial, o projeto ainda não envia mensagens reais pelo WhatsApp. As funções de envio simulam a digitação e o envio no terminal. Para uso em produção, o próximo passo é integrar com a WhatsApp Business Cloud API ou outro provedor autorizado.

## Como executar

```bash
python "arquivo completo do bot.txt"
```

## Próximos passos sugeridos

- Renomear o arquivo principal para `mezzold_connect.py`.
- Corrigir acentuação dos textos exibidos no terminal.
- Implementar envio real via API oficial.
- Separar o código em módulos.
- Trocar arquivos CSV por banco de dados.
- Implementar agendamento, tela de campanhas e interface gráfica.
