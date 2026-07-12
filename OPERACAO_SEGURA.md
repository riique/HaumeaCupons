# Operacao segura

Este projeto automatiza leitura de mensagens do Telegram e salva findings no SQLite para o dashboard. Ele nao envia mensagens no Telegram.

## Regra principal

Nao rode conta de usuario com `chat_groups=all` como configuracao normal. O codigo bloqueia esse modo por padrao porque ele amplia demais a superficie de eventos e pode gerar leituras/verificacoes desnecessarias.

## Checklist antes de iniciar

1. Use `BOT_TOKEN` quando o caso de uso permitir.
2. Se usar `PHONE`, configure uma lista explicita em `chat_groups`.
3. Remova palavras-chave genericas como `cupom` e `desconto` quando elas nao forem produtos reais.
4. Defina `DASHBOARD_API_KEY` antes de expor o painel.
5. Se usar Firebase Hosting, crie o documento `admins/{uid}` para os usuarios que podem editar regras.
6. Mantenha `SIGNAL_ONLY_MAX_PRICE=0` em producao ate revisar a qualidade dos falsos positivos; ofertas sem regra entram como `review`.
7. Verifique `python -m pytest -q` antes de rodar mudancas.
8. Acompanhe logs nos primeiros minutos e pause se aparecer erro repetido de conexao, login ou verificacao HTTP.

## Ramp-up apos dessuspensao

1. Comece com 1 ou 2 grupos confiaveis.
2. Rode por 15 a 30 minutos sem `chat_groups=all`.
3. Confirme que os findings no dashboard estao relevantes.
4. Aumente grupos gradualmente.
5. Se houver qualquer erro repetido do Telegram, pare e investigue antes de tentar de novo.

## O que evitar

- Reativar envio automatico de mensagens pela conta pessoal.
- Expor o dashboard via tunnel sem chave.
- Rodar multiplas instancias usando a mesma sessao.
- Comitar `.env`, `*.session`, bancos SQLite ou logs sensiveis.

## Sinais de parada

Pare o processo se aparecer:

- erros repetidos de conexao/login Telegram
- erros repetidos de verificacao HTTP
- muitos candidatos irrelevantes por minuto
- alertas duplicados
- fila de revisao crescendo sem regra correspondente
