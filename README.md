# HaumeaCupons

Bot Telethon/FastAPI para monitorar mensagens do Telegram, detectar ofertas por palavras-chave, validar links/precos, registrar findings em SQLite e exibir tudo em um dashboard React.

## Modo seguro primeiro

Depois de qualquer limitacao ou dessuspensao de conta, nao rode o projeto em conta de usuario com `chat_groups=all`.

Protecoes atuais:

- `events.NewMessage(incoming=True)` evita processar mensagens de saida.
- Conta de usuario com `chat_groups=all` fica bloqueada por padrao.
- `ALLOW_ALL_CHATS=true` e necessario para assumir esse risco explicitamente.
- Alertas passam por fila com intervalo minimo antes de `send_message`.
- Mensagens ja processadas sao deduplicadas por chat/mensagem/hash.
- `/api/*` aceita `DASHBOARD_API_KEY` para proteger painel e operacoes destrutivas.
- `tunnel.sh` se recusa a expor o dashboard sem `DASHBOARD_API_KEY`.

## Setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p logs
python main.py
```

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python main.py
```

## Variaveis `.env`

- `API_ID`: API ID do Telegram.
- `API_HASH`: API hash do Telegram.
- `BOT_TOKEN`: token do BotFather. Preferivel quando o caso de uso permitir.
- `PHONE`: telefone da conta de usuario. Use apenas quando realmente precisar MTProto como usuario.
- `MAIN_USER_ID`: ID numerico do usuario que recebera alertas.
- `MAIN_USERNAME`: fallback para resolver o destinatario dos alertas.
- `CHAT_GROUPS`: grupos permitidos. Use IDs/usernames separados por virgula.
- `ALLOW_ALL_CHATS`: precisa ser `true` para permitir `chat_groups=all` em conta de usuario.
- `ALERT_MIN_INTERVAL_SECONDS`: intervalo minimo por destino antes de enviar outro alerta. Padrao: `1.2`.
- `MAX_ALERT_QUEUE_SIZE`: tamanho maximo da fila de alertas. Padrao: `100`.
- `DEDUPE_TTL_SECONDS`: janela de dedupe em memoria. Padrao: `1800`.
- `DASHBOARD_API_KEY`: chave exigida em `/api/*` quando definida.

## Dados

Produtos e grupos ficam em `data.json`:

```json
{
  "products": [
    {
      "id": 0,
      "keywords": ["iphone", "smartphone apple"],
      "max_price": 4500.0
    }
  ],
  "chat_groups": ["@grupo_de_ofertas"]
}
```

`chat_groups` aceita uma lista de IDs/usernames ou `"all"`. Para conta de usuario, `"all"` so inicia com `ALLOW_ALL_CHATS=true`.

## Dashboard

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000`.

Em producao, gere o build do frontend antes de subir o FastAPI:

```bash
cd frontend
npm install
npm run build
```

Para expor via Cloudflare Tunnel:

```bash
export DASHBOARD_API_KEY="uma-chave-forte"
./tunnel.sh
```

O frontend pedira a chave quando a API responder 401.

## Testes

```bash
python -m pytest -q
cd frontend
npm run build
```

## Arquivos principais

- `config.py`: leitura e validacao de ambiente.
- `main.py`: cliente Telethon, filtros, dedupe, fila de alertas e handler `NewMessage`.
- `verifier.py`: extracao de links/cupons e verificacao HTTP/HTML.
- `storage.py`: SQLite de findings e dedupe persistente.
- `app.py`: API FastAPI, auth opcional por chave e entrega do build React.
- `frontend/`: dashboard React + TypeScript + Tailwind.
- `data.json`: produtos e grupos monitorados.
- `test_sim.py`: testes de simulacao/API/parser.
- `logs/`: logs locais e banco SQLite.
