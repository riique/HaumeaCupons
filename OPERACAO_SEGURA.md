# Operacao segura

Este projeto automatiza leitura de mensagens e envio de alertas no Telegram. Use com cuidado, especialmente apos uma dessuspensao.

## Regra principal

Nao rode conta de usuario com `chat_groups=all` como configuracao normal. O codigo agora bloqueia esse modo por padrao porque ele amplia demais a superficie de eventos e pode gerar flood.

## Checklist antes de iniciar

1. Use `BOT_TOKEN` quando o caso de uso permitir.
2. Se usar `PHONE`, configure uma lista explicita em `chat_groups`.
3. Remova palavras-chave genericas como `cupom` e `desconto` quando elas nao forem produtos reais.
4. Mantenha `ALERT_MIN_INTERVAL_SECONDS` em `1.2` ou maior.
5. Defina `DASHBOARD_API_KEY` antes de expor o painel.
6. Verifique `python -m pytest -q` antes de rodar mudancas.
7. Acompanhe logs nos primeiros minutos e pause se aparecer `Too many requests`, `FloodWait` ou erro de entidade.

## Ramp-up apos dessuspensao

1. Comece com 1 ou 2 grupos confiaveis.
2. Rode por 15 a 30 minutos sem `chat_groups=all`.
3. Confirme que os alertas estao relevantes.
4. Aumente grupos gradualmente.
5. Se houver qualquer rate limit, pare e aguarde antes de tentar de novo.

## O que evitar

- Enviar mensagens para desconhecidos.
- Usar conta pessoal como broadcaster.
- Expor o dashboard via tunnel sem chave.
- Rodar multiplas instancias usando a mesma sessao.
- Comitar `.env`, `*.session`, bancos SQLite ou logs sensiveis.

## Sinais de parada

Pare o processo se aparecer:

- `Too many requests`
- `FloodWait`
- `PeerFlood`
- falhas repetidas em `send_message`
- muitos candidatos irrelevantes por minuto
- alertas duplicados
