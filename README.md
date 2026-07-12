# HaumeaCupons

Bot Telethon/FastAPI para monitorar mensagens do Telegram, detectar ofertas por sinais estruturais ou regras legadas por palavra-chave, validar links/precos, registrar findings em SQLite/Firestore e exibir tudo em um dashboard React.

## Modo seguro primeiro

Depois de qualquer limitacao ou dessuspensao de conta, nao rode o projeto em conta de usuario com `chat_groups=all`.

Protecoes atuais:

- `events.NewMessage(incoming=True)` evita processar mensagens de saida.
- Conta de usuario com `chat_groups=all` fica bloqueada por padrao.
- `ALLOW_ALL_CHATS=true` e necessario para assumir esse risco explicitamente.
- O bot nao envia mensagens no Telegram; ele apenas salva findings no SQLite para o dashboard.
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
- `CHAT_GROUPS`: grupos permitidos. Use IDs/usernames separados por virgula.
- `ALLOW_ALL_CHATS`: precisa ser `true` para permitir `chat_groups=all` em conta de usuario.
- `DEDUPE_TTL_SECONDS`: janela de dedupe em memoria. Padrao: `1800`.
- `SIGNAL_ONLY_MAX_PRICE`: teto global opcional para autoaprovar ofertas sem regra. Padrao: `0`, que envia para revisao.
- `STORE_REVIEW_FINDINGS`: quando `true`, tambem grava revisoes como findings. Padrao: `false`; em producao, deixe falso para nao poluir alertas.
- `FIRESTORE_SYNC_FINDINGS`: sincroniza findings do bot para Firestore via Admin SDK quando `true`.
- `FIRESTORE_SYNC_TIMEOUT_SECONDS`: timeout da sincronizacao assíncrona com Firestore. Padrao: `8`.
- `VERIFY_LINK_ALLOWLIST_DOMAINS` / `VERIFY_LINK_DENYLIST_DOMAINS`: filtros opcionais de dominios para verificacao HTTP.
- `DASHBOARD_API_KEY`: chave exigida em `/api/*` quando definida.

## Dados

Produtos e grupos ficam em `data.json`:

```json
{
  "products": [
    {
      "id": 0,
      "name": "iPhone",
      "keywords": ["iphone", "smartphone apple"],
      "exclude_terms": ["capinha", "pelicula"],
      "max_price": 4500.0
    }
  ],
  "chat_groups": ["@grupo_de_ofertas"]
}
```

`chat_groups` aceita uma lista de IDs/usernames ou `"all"`. Para conta de usuario, `"all"` so inicia com `ALLOW_ALL_CHATS=true`.

## Deteccao de ofertas

O bot nao depende mais de `keywords` para transformar uma mensagem em candidata. O modo padrao e `DETECTION_MODE=hybrid`:

- `keywords`: comportamento legado, exige keyword cadastrada.
- `signals`: ignora keywords e captura ofertas por sinais fortes: titulo de produto, preco contextual, marketplace conhecido, links e cupom.
- `hybrid`: aceita regra legada ou sinais fortes de oferta. Quando uma regra cadastrada bate, o `max_price` continua sendo aplicado. Quando nao ha regra, a oferta vira `review` por padrao; so vira `approved` automaticamente se `SIGNAL_ONLY_MAX_PRICE` estiver definido e o preco extraido estiver abaixo dele.

`keywords` segue aceito por compatibilidade, mas hoje representa termos de match de uma regra de preco. O modelo novo aceita tambem `name`, `min_price`, `exclude_terms`, `merchants`, `category` e `auto_approve`.

Variaveis relevantes:

- `MIN_OFFER_CONFIDENCE`: minimo do classificador de oferta. Padrao: `0.62`.
- `MESSAGE_AUDIT_ENABLED`: registra decisoes em `message_events` no SQLite. Padrao: `true`.
- `STORE_RAW_MESSAGES`: grava texto bruto nos findings/auditoria. Padrao: `false`; mantenha assim em producao salvo necessidade operacional.

Mensagens de cupom puro, como `R$100 OFF acima de R$999`, sao penalizadas para evitar tratar desconto/minimo de compra como preco de produto.

## Segurança do Firestore

O frontend publicado no Firebase Hosting le o Firestore diretamente. Nao ha Cloud Run nem Cloud Functions neste projeto.

As regras em `firestore.rules` permitem leitura para usuarios autenticados, mas escrita/delecao de regras e findings apenas para administradores. Um administrador e representado por um documento `admins/{uid}` criado via Firebase Console ou Admin SDK. O bot usa service account/Admin SDK e nao depende dessas rules para gravar findings.

Para conceder admin sem Cloud Functions:

```bash
python ops/grant_admin.py --email pessoa@exemplo.com
# ou
python ops/grant_admin.py --uid UID_DO_FIREBASE_AUTH
```

## Dashboard

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000`.

Em producao, o frontend vai para Firebase Hosting e le o Firestore diretamente:

```bash
cd frontend
npm install
npm run build
cd ..
firebase deploy --only hosting,firestore:rules
```

O FastAPI continua util como dashboard/API local de manutencao. Para expor via Cloudflare Tunnel:

```bash
export DASHBOARD_API_KEY="uma-chave-forte"
./tunnel.sh
```

O frontend publicado no Firebase Hosting nao usa essa API local; ele depende de Firebase Auth + Firestore Rules.

## Testes

```bash
python -m pytest -q
cd frontend
npm run build
```

## Arquivos principais

- `config.py`: leitura e validacao de ambiente.
- `main.py`: cliente Telethon, filtros, dedupe, persistencia em SQLite e handler `NewMessage`.
- `verifier.py`: extracao de links/cupons e verificacao HTTP/HTML.
- `storage.py`: SQLite de findings e dedupe persistente.
- `app.py`: API FastAPI, auth opcional por chave e entrega do build React.
- `frontend/`: dashboard React + TypeScript + Tailwind.
- `data.json`: produtos e grupos monitorados.
- `test_sim.py`: testes de simulacao/API/parser.
- `logs/`: logs locais e banco SQLite.
