# Auditoria tecnica - HaumeaCupons

Data: 2026-04-26  
Escopo: backend Python/Telethon/FastAPI, persistencia SQLite/JSON, dashboard React/Vite e sinais operacionais locais.  
Nota de privacidade: valores de `.env`, arquivo de sessao, IDs pessoais, URLs reais e conteudo sensivel dos logs nao foram incluidos.
Status: snapshot da auditoria antes das correcoes aplicadas na sequencia.

## Resumo executivo

O projeto esta em estado funcional experimental, mas nao esta pronto para operar de forma segura com uma conta Telegram real. O maior risco nao e a arquitetura em si; e a combinacao de automacao via conta de usuario, monitoramento amplo, ausencia de fila/rate limit/idempotencia e alertas com links/promocoes. Isso se conecta diretamente ao contexto de suspensao: os logs mostram erro de "Too many requests" em envio de mensagem, e a documentacao oficial do Telegram trata flooding/spam via API como motivo grave de limitacao ou banimento.

Nivel geral de risco: alto.  
Maturidade tecnica percebida: 4/10.  
Principal gargalo estrutural: fluxo de eventos Telegram acoplado diretamente a verificacao HTTP, persistencia e envio de alerta, sem controle operacional intermediario.  
Principal prioridade imediata: parar a execucao em conta de usuario ate implementar filtros, dedupe e rate limit antes de qualquer `send_message`.  
Justificativa da nota: o frontend compila e ha tentativas boas de validacao/SSRF/SQLite, mas os testes falham, ha bugs de runtime confirmados, o dashboard e destrutivo sem autenticacao, e o fluxo que toca Telegram ainda nao tem as protecoes minimas contra flood.

## Validacoes executadas

- `python -m pytest -q`: falhou com 5 testes quebrados e 3 passando.
- `npm run build` em `frontend/`: passou.
- `python -m compileall -q app.py config.py main.py storage.py verifier.py test_sim.py`: passou.
- `npm audit --omit=dev --json`: 0 vulnerabilidades em dependencias de producao do frontend.
- Inspecao de logs locais: 8 candidatos, 3 excecoes nao tratadas historicas, 3 falhas de envio, 1 alerta enviado e 1 registro de "Too many requests".
- Verificacao local de `/api/state`/`get_findings`: falha confirmada por `IndexError` quando ha findings no banco.

## Contexto externo relevante

- A FAQ oficial de spam do Telegram informa que contas podem ser limitadas quando usuarios reportam mensagens indesejadas, especialmente publicidade, links, convites e conteudo comercial enviado de forma nao esperada: https://telegram.org/faq_spam
- A pagina oficial de criacao de apps Telegram diz que clientes API nao oficiais ficam sob observacao e que uso da API para flooding/spamming pode resultar em banimento permanente: https://core.telegram.org/api/obtaining_api_id
- Os termos da API proibem interferir no funcionamento basico do Telegram e exigem cuidado com privacidade/transparencia: https://core.telegram.org/api/terms
- A FAQ oficial de bots recomenda evitar mais de 1 mensagem por segundo em um chat e alerta para 429 quando limites sao excedidos: https://core.telegram.org/bots/faq

## 1. Riscos de erros e regressoes

**Diagnostico:** a migracao de produto unico (`keyword`, `min_price`) para multiplas keywords (`keywords`, sem `min_price`) ficou incompleta. Isso quebrou testes, dados, README e parte do runtime.  
**Evidencias:** `config.py:17-20` define `Product(keywords, max_price)`, mas `test_sim.py:63`, `test_sim.py:117`, `test_sim.py:161`, `test_sim.py:184` ainda usam `keyword/min_price`. `data.json:3-50` tambem esta no formato legado. `main.py:56` chama `product.primary_keyword`, atributo que nao existe em `Product`.  
**Impacto:** novas alteracoes podem parecer corretas no frontend, mas quebrar o bot ou a API. A falha em `main.py:56` pode derrubar o handler quando a pagina nao traz `product_keyword` e a funcao tenta inferir a keyword.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** escolher um contrato unico. Preferencialmente migrar `data.json`, README, testes e fixtures para `{ "keywords": [...], "max_price": n }`; adicionar propriedade `primary_keyword` em `Product` ou trocar `product.primary_keyword` por `product.keywords[0]`; remover definitivamente `min_price` ou reintroduzi-lo de ponta a ponta.

**Diagnostico:** a API de findings esta quebrada quando ha registros.  
**Evidencias:** `storage.py:98-107` seleciona `id,timestamp,product_keyword,url,price_found,price_ok,source_group`, mas `storage.py:123-124` tenta ler `coupons` e `links`. O banco local tem essas colunas e 5 registros, mas `get_findings(1)` falha por `IndexError`.  
**Impacto:** `/api/state` e `/api/findings` podem retornar 500 assim que houver alertas; o dashboard fica parcialmente inutilizavel.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** incluir `coupons, links` no `SELECT` e adicionar teste de regressao para findings com e sem essas colunas.

## 2. Oportunidades de simplificacao

**Diagnostico:** o handler Telegram faz extracao, filtro, verificacao HTTP, decisao de preco, persistencia e envio. Isso aumenta complexidade e torna dificil limitar danos.  
**Evidencias:** `main.py:126-218` concentra o fluxo inteiro; `verify_links` e chamado diretamente antes do envio; `add_finding` acontece antes de confirmar que o alerta foi enviado.  
**Impacto:** qualquer mudanca em preco, cupom, filtro de grupo ou envio pode gerar regressao cruzada. Em incidente, fica dificil saber se o problema veio do Telegram, da pagina, do parser ou da fila inexistente.  
**Criticidade:** media.  
**Horizonte de risco:** medio prazo.  
**Acao recomendada:** separar em funcoes puras: `classify_message`, `verify_candidate`, `build_alert`, `persist_finding`, `enqueue_alert`. O handler deve apenas transformar evento em comando interno e empurrar para uma fila.

**Diagnostico:** ha dois modelos de configuracao competindo: `.env` inicializa dados, `data.json` e editado pelo dashboard, e o bot recarrega por polling.  
**Evidencias:** `config.py:71-77` gera dados iniciais via env, `app.py:98-99` salva em JSON, `main.py:114-120` recarrega periodicamente.  
**Impacto:** o operador pode mudar `.env` achando que alterou produtos/grupos, mas `data.json` existente prevalece. Isso cria comportamento "fantasma".  
**Criticidade:** media.  
**Horizonte de risco:** curto/medio prazo.  
**Acao recomendada:** documentar e aplicar uma regra: `.env` so para credenciais; `data.json` ou SQLite para configuracao operacional. Se `data.json` existir, ignorar produtos/grupos do env de forma explicita no log.

## 3. Problemas latentes de crescimento

**Diagnostico:** nao ha idempotencia nem deduplicacao por mensagem/link/cupom.  
**Evidencias:** `main.py:176-203` salva um finding por mensagem sem registrar `chat_id`, `message_id` ou hash; `storage.py:19-29` nao tem constraint de unicidade.  
**Impacto:** mensagens repostadas, edits, reinicios, alertas enviados para "me" ou duplicatas de grupos podem gerar avalanche de alertas e hit de rate limit. Isso e especialmente perigoso para uma conta recem-dessuspensa.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** persistir `source_chat_id`, `source_message_id`, `canonical_url_hash` e `message_hash`; criar `UNIQUE(source_chat_id, source_message_id)` e uma janela de dedupe por URL/produto.

**Diagnostico:** `chat_groups: "all"` com keywords genericas cria superficie enorme.  
**Evidencias:** `data.json:52` usa `"all"`; `data.json:41-49` inclui termos amplos como "Cupom" e "Desconto"; `main.py:34-35` permite todos os chats quando configurado assim.  
**Impacto:** o bot reage a muitos grupos/canais, inclusive locais nao intencionais. Quanto mais mensagens comerciais com links, maior a chance de flood, falso positivo e classificacao de comportamento automatizado agressivo.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** trocar default operacional para allow-list de chats. Bloquear startup em conta de usuario se `chat_groups == "all"` sem flag explicita de risco.

## 4. Escalabilidade e manutenibilidade

**Diagnostico:** nao existe fila/rate limiter para `send_message`.  
**Evidencias:** `main.py:207` chama `send_message` diretamente; `main.py:209-216` trata apenas `FloodWaitError`; logs locais mostram "Too many requests (caused by SendMessageRequest)" caindo no `except Exception`.  
**Impacto:** picos de candidatos viram picos de mensagens. O bot nao aprende com 429, nao reduz ritmo e nao preserva a conta.  
**Criticidade:** alta.  
**Horizonte de risco:** imediato.  
**Acao recomendada:** implementar uma `asyncio.Queue` de alertas, com limite por destino: no maximo 1 mensagem/segundo por chat, cooldown global apos qualquer erro de flood/429, retry com backoff e descarte controlado de duplicatas.

**Diagnostico:** verificacao HTTP e consumo de Telegram competem no mesmo caminho assincrono.  
**Evidencias:** `main.py:154` aguarda `verify_links`; `verifier.py:285` limita concorrencia de URLs a 5, mas nao limita quantidade de eventos Telegram pendentes.  
**Impacto:** grupos com muitos links podem acumular tarefas e atrasar ou sobrecarregar o processo. Se a conta recebe muitas mensagens, o processo vira crawler sem controle de orcamento.  
**Criticidade:** media.  
**Horizonte de risco:** medio prazo.  
**Acao recomendada:** colocar verificacoes HTTP em worker com fila e limite de throughput por dominio; descartar candidatos antigos quando a fila estiver cheia.

## 5. Prioridades de isolamento, documentacao e testes

**Diagnostico:** os testes nao protegem o comportamento atual porque estao desatualizados.  
**Evidencias:** `python -m pytest -q` falha em 5 testes; fixtures esperam `keyword/min_price`, mas codigo atual usa `keywords/max_price`.  
**Impacto:** qualquer refatoracao fica sem rede de seguranca. O projeto pode "parecer" ajustado no navegador, mas quebrar em runtime.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** primeiro corrigir testes existentes para o contrato atual, depois adicionar testes para: dedupe, `incoming=True`, rate limit, findings com `coupons/links`, formato legado de `data.json`, erro 429/FloodWait e pagina HTTP com status invalido.

**Diagnostico:** README esta parcialmente divergente do codigo.  
**Evidencias:** `README.md` ainda mostra `products: [{"keyword": "iphone", "min_price": 50.0, "max_price": 200.0}]`, enquanto `frontend/src/types.ts:1-5` e `app.py:21-31` usam `keywords`.  
**Impacto:** onboarding e operacao ficam propensos a configuracao errada.  
**Criticidade:** media.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** atualizar README com o schema real, avisos de suspensao/rate limit e um modo seguro recomendado.

## 6. Divergencias entre intencao e comportamento real

**Diagnostico:** a configuracao parece aceitar faixa de preco, mas o comportamento atual usa apenas teto.  
**Evidencias:** `data.json` e testes ainda contem `min_price`; `verifier.py:119-121` aprova qualquer preco `<= max_price`.  
**Impacto:** precos absurdamente baixos, erros de parser ou valores parciais podem disparar alerta.  
**Criticidade:** media.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** decidir se `min_price` deve existir. Se sim, restaurar em `Product`, API, frontend e parser. Se nao, remover dos dados/documentacao/testes.

**Diagnostico:** uma pagina HTTP com status ruim ainda pode aprovar preco.  
**Evidencias:** `verifier.py:255-264` calcula `price_ok` mesmo quando `status_ok` e falso; `main.py:155` considera apenas `result.price_ok`, nao `result.ok`.  
**Impacto:** uma pagina 404/500 que contenha texto com keyword/preco pode gerar alerta.  
**Criticidade:** media.  
**Horizonte de risco:** medio prazo.  
**Acao recomendada:** exigir `result.ok and result.price_ok` para `page_price_ok`, salvo quando a decisao vier explicitamente do texto da mensagem.

**Diagnostico:** keyword por substring gera falso positivo.  
**Evidencias:** `main.py:28-30` e `verifier.py:116` usam `kw in text`. Um teste manual mostrou que "capinha de iphone por R$ 500,00" aprova produto "iphone".  
**Impacto:** alertas irrelevantes aumentam volume de mensagens e risco de flood.  
**Criticidade:** media.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** usar regras por produto com termos positivos/negativos, word boundaries quando fizer sentido, e sinonimos explicitos.

## 7. Padroes e convencoes que reduziriam complexidade

**Diagnostico:** faltam contratos versionados para dados persistidos.  
**Evidencias:** `app.py:131-143` faz migracao ad hoc de produto legado; `storage.py:32-37` faz migracao ad hoc de colunas SQLite; nao ha versao de schema.  
**Impacto:** cada nova alteracao tende a virar compatibilidade manual espalhada.  
**Criticidade:** media.  
**Horizonte de risco:** medio prazo.  
**Acao recomendada:** adicionar `schema_version` em `data.json` e migracoes SQLite nomeadas/idempotentes. Testar cada migracao com fixtures antigas.

**Diagnostico:** o painel expoe operacoes destrutivas sem camada de autorizacao.  
**Evidencias:** `app.py:231-248` deleta findings individuais e todos os findings; `app.py:251-262` expoe logs; nao ha middleware de auth em `app.py:82`. `tunnel.sh:2` expoe `localhost:8000`.  
**Impacto:** se o tunnel for publico sem Cloudflare Access, terceiros podem ler logs, ver links/cupons/grupos e apagar historico.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** exigir autenticacao antes de usar tunnel: Cloudflare Access ou API key local obrigatoria para `/api/*`; redigir logs antes de retornar ao frontend; desabilitar DELETE em modo publico.

## 8. Riscos de transferencia de conhecimento

**Diagnostico:** conhecimento operacional critico esta implicito.  
**Evidencias:** nao ha documento de "modo seguro"; README avisa que dashboard nao tem auth, mas nao descreve como evitar suspensao da conta, como configurar grupos, como reagir a FloodWait/429, ou quando preferir bot token.  
**Impacto:** outra pessoa pode rodar `python main.py` com `PHONE` e `chat_groups=all`, exatamente a combinacao mais arriscada.  
**Criticidade:** alta.  
**Horizonte de risco:** curto prazo.  
**Acao recomendada:** criar `OPERACAO_SEGURA.md` com checklist: usar bot/token ou canal proprio, allow-list de grupos, limites de envio, cooldown apos 429, nunca automatizar contato com desconhecidos, e procedimento de pausa apos dessuspensao.

**Diagnostico:** ha dados locais sensiveis que exigem disciplina.  
**Evidencias:** `.gitignore` cobre `.env` e `*.session`; existe arquivo de sessao Telethon local.  
**Impacto:** vazamento do arquivo de sessao equivale a risco de acesso indevido a conta.  
**Criticidade:** alta.  
**Horizonte de risco:** permanente.  
**Acao recomendada:** manter `*.session` fora de backup/sync publico, documentar rotacao/relogin, e considerar apagar sessoes antigas apos mudancas de seguranca.

## 9. Melhorias com melhor impacto/esforco

1. Corrigir `storage.py` para selecionar `coupons` e `links`. Dificuldade baixa, impacto alto.
2. Corrigir contrato `Product` em `main.py`, testes, README e `data.json`. Dificuldade baixa/media, impacto alto.
3. Mudar `events.NewMessage()` para filtrar apenas mensagens de entrada e excluir destino/self. Dificuldade baixa, impacto alto.
4. Desativar `chat_groups=all` para modo conta de usuario. Dificuldade baixa, impacto alto.
5. Adicionar rate limiter simples antes de `send_message`. Dificuldade media, impacto altissimo para evitar nova limitacao.
6. Adicionar dedupe por mensagem/link. Dificuldade media, impacto alto.
7. Proteger `/api/*` antes de usar tunnel. Dificuldade media, impacto alto.
8. Atualizar README/operacao segura. Dificuldade baixa, impacto medio/alto.

## 10. Lacunas para producao robusta

**Diagnostico:** falta previsibilidade operacional.  
**Evidencias:** nao ha healthcheck, metricas, log rotation, fila persistente, retry policy completa, CI, lock Python, processo supervisionado ou backup do SQLite.  
**Impacto:** em producao, falhas aparecem como logs locais e comportamento silencioso; recuperar estado e diagnosticar causa raiz fica lento.  
**Criticidade:** media/alta.  
**Horizonte de risco:** medio prazo.  
**Acao recomendada:** adicionar CI com pytest/build, log rotativo, health endpoint, metricas simples (`alerts_sent`, `alerts_dropped`, `flood_waits`, `queue_depth`), backup do SQLite e `.env.example` completo.

**Diagnostico:** ha mitigacoes boas de SSRF, mas ainda incompletas para ambiente hostil.  
**Evidencias:** `verifier.py:147-176` bloqueia localhost/IP privada e valida redirects; porem ha janela DNS entre validacao e request, e qualquer membro de grupo monitorado pode induzir o servidor a buscar URLs.  
**Impacto:** risco residual de SSRF/DNS rebinding e abuso como crawler.  
**Criticidade:** media.  
**Horizonte de risco:** medio prazo.  
**Acao recomendada:** resolver e conectar via IP validado ou usar resolver/connector controlado; impor allow/deny-list de dominios de lojas; cachear verificacoes; limitar requisicoes por dominio.

## Principais riscos priorizados

1. Nova limitacao/suspensao Telegram. Onde: `main.py:207`, `main.py:237`, `data.json:52`. Perigoso porque combina conta de usuario, todos os grupos, links comerciais e ausencia de rate limit. Pode quebrar a conta. Severidade alta, urgencia imediata.
2. Dashboard quebrado por findings. Onde: `storage.py:98-124`, `app.py:161`, `app.py:176`. Pode quebrar `/api/state` e `/api/findings`. Severidade alta, urgencia imediata.
3. Migracao incompleta de produto. Onde: `config.py`, `main.py`, `test_sim.py`, `data.json`, `README.md`. Pode quebrar runtime, testes e configuracao. Severidade alta, urgencia imediata.
4. Exposicao publica do painel sem auth. Onde: `app.py:231-262`, `tunnel.sh:2`. Pode expor logs e permitir delecao. Severidade alta, urgencia curta.
5. Falsos positivos por keywords genericas. Onde: `data.json`, `main.py:28-30`, `verifier.py:116`. Pode aumentar volume de alertas e flood. Severidade media/alta, urgencia curta.
6. Ausencia de dedupe/idempotencia. Onde: `storage.py` schema e `main.py:176-203`. Pode gerar alertas repetidos. Severidade alta, urgencia curta.
7. Testes sem confiabilidade. Onde: `test_sim.py`. Pode esconder regressao. Severidade media/alta, urgencia curta.

## Divergencias consolidadas entre intencao e comportamento

- A UI e tipos dizem `keywords`, mas dados/testes/documentacao ainda dizem `keyword`.
- A configuracao sugere faixa `min_price/max_price`, mas o codigo so aplica `max_price`.
- O README recomenda seguranca no tunnel, mas o codigo nao exige nenhuma protecao.
- O bot aparenta monitorar "ofertas", mas keywords amplas como "Cupom" e "Desconto" transformam quase qualquer promocao em candidato.
- A verificacao de pagina parece validar link, mas `main.py` usa `price_ok` sem exigir `ok`.
- O envio parece protegido por `FloodWaitError`, mas o erro real registrado foi "Too many requests" generico, sem cooldown.

## Plano de acao recomendado

### Imediato

1. Nao rodar novamente em conta dessuspensa ate aplicar limite de envio, dedupe e allow-list de grupos.
2. Alterar o handler para `events.NewMessage(incoming=True)` e ignorar mensagens do proprio usuario/destino de alertas.
3. Trocar `chat_groups` para lista explicita; remover keywords genericas como "Cupom" e "Desconto" ate haver regras negativas.
4. Corrigir `storage.py` (`SELECT coupons, links`) e `main.py:56`.
5. Atualizar testes para o contrato atual e garantir `pytest` verde.

### Curto prazo

1. Implementar fila de alertas com 1 mensagem/segundo por destino e cooldown global em qualquer flood/429.
2. Persistir dedupe por `chat_id/message_id` e hash de URL/produto.
3. Migrar `data.json` para o schema atual e remover campos legados ou restaura-los de ponta a ponta.
4. Proteger `/api/*` com auth antes de qualquer tunnel.
5. Redigir `/api/logs` e limitar leitura por tail real, nao `readlines()` do arquivo inteiro.

### Medio prazo

1. Separar classificacao, verificacao, persistencia e envio em modulos testaveis.
2. Adicionar schema version/migracoes para JSON e SQLite.
3. Adicionar testes para 429/FloodWait, duplicatas, status HTTP ruim, paginas sem preco, cupom sem link e grupos bloqueados.
4. Criar healthcheck e metricas simples.

### Longo prazo

1. Preferir bot oficial/canal proprio quando o caso de uso permitir, evitando automacao de conta pessoal por MTProto.
2. Criar modo de producao com processo supervisionado, logs rotativos, backups e CI.
3. Adicionar politica operacional para dessuspensao: cooldown, ramp-up lento, lista pequena de grupos e revisao manual dos primeiros alertas.
