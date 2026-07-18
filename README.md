# HaumeaCupons

Monitore grupos do Telegram, encontre ofertas com sinais verificáveis e revise os resultados em um painel próprio.

O HaumeaCupons combina Telethon, um classificador de ofertas, validação de links e preços, persistência em SQLite ou Firestore e um dashboard React. O fluxo foi desenhado para reduzir falsos positivos sem transformar a conta do Telegram em um disparador de mensagens.

## O que o projeto entrega

- monitora apenas mensagens recebidas com `events.NewMessage(incoming=True)`;
- encontra preço, título, links, cupons e marketplace no texto;
- classifica mensagens por regras de produto, sinais estruturais ou uma combinação dos dois;
- aplica preço mínimo, preço máximo, termos excluídos, lojistas e aprovação manual;
- evita reprocessamento por chat, mensagem e hash;
- mantém auditoria das decisões no SQLite;
- sincroniza findings com o Firestore quando essa opção é habilitada;
- oferece dashboard React com autenticação Firebase e uma API FastAPI para manutenção local;
- pode encaminhar ofertas aprovadas ao Hermes por webhook, apenas para produtos autorizados.

> [!IMPORTANT]
> O envio direto de alertas pelo Telegram está desativado no código. O bot lê mensagens e salva resultados; notificações externas, quando configuradas, seguem pelo webhook do Hermes.

## Segurança antes da cobertura

Contas de usuário são bloqueadas por padrão quando `chat_groups=all`. Para liberar esse modo, é preciso definir `ALLOW_ALL_CHATS=true` e aceitar explicitamente o risco de monitorar todos os chats acessíveis.

Para uma operação mais segura:

- prefira `BOT_TOKEN` sempre que o caso de uso permitir;
- restrinja `CHAT_GROUPS` a IDs ou nomes conhecidos;
- mantenha `STORE_RAW_MESSAGES=false` para não persistir o texto completo;
- defina `DASHBOARD_API_KEY` antes de expor a API local;
- use allowlist de domínios na verificação HTTP quando possível;
- nunca versione `.env`, sessão do Telegram ou conta de serviço do Firebase.

O script `tunnel.sh` se recusa a publicar o dashboard sem `DASHBOARD_API_KEY`.

## Requisitos

- Python 3.10 ou superior;
- credenciais de API do Telegram;
- token de bot ou telefone para uma sessão MTProto;
- Node.js e npm para compilar o frontend;
- projeto Firebase apenas se você quiser autenticação, Firestore e Hosting.

## Instalação

```bash
git clone https://github.com/riique/HaumeaCupons.git
cd HaumeaCupons
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p logs
```

No PowerShell:

```powershell
git clone https://github.com/riique/HaumeaCupons.git
Set-Location HaumeaCupons
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
New-Item -ItemType Directory -Force logs
```

Preencha pelo menos `API_ID`, `API_HASH`, uma forma de autenticação (`BOT_TOKEN` ou `PHONE`) e `CHAT_GROUPS`.

## Configuração dos produtos

Produtos e grupos podem ser definidos em `data.json`:

```json
{
  "products": [
    {
      "id": 0,
      "name": "iPhone",
      "keywords": ["iphone", "smartphone apple"],
      "exclude_terms": ["capinha", "película"],
      "max_price": 4500
    }
  ],
  "chat_groups": ["@grupo_de_ofertas"]
}
```

`chat_groups` aceita IDs, nomes de usuário ou `"all"`. O formato de produto também suporta `min_price`, `merchants`, `category` e `auto_approve`.

### Modos de detecção

Defina `DETECTION_MODE` como:

| Modo | Comportamento |
| --- | --- |
| `keywords` | exige correspondência com uma regra cadastrada |
| `signals` | procura sinais fortes de oferta sem depender de palavra-chave |
| `hybrid` | aceita regra cadastrada ou sinais fortes; é o padrão |

Uma oferta detectada apenas por sinais vai para revisão. Ela só é aprovada automaticamente quando `SIGNAL_ONLY_MAX_PRICE` define um teto global e o preço encontrado respeita esse limite. Mensagens de cupom puro recebem penalidade para evitar que o desconto ou o valor mínimo da compra seja confundido com preço de produto.

As opções de operação estão documentadas em `.env.example`, incluindo:

- `MIN_OFFER_CONFIDENCE`;
- `DEDUPE_TTL_SECONDS`;
- `STORE_REVIEW_FINDINGS`;
- `MESSAGE_AUDIT_ENABLED`;
- `FIRESTORE_SYNC_FINDINGS`;
- `VERIFY_LINK_ALLOWLIST_DOMAINS` e `VERIFY_LINK_DENYLIST_DOMAINS`;
- variáveis `HAUMEA_HERMES_*` para o webhook opcional.

## Executar

Inicie o monitor:

```bash
python main.py
```

Inicie a API e o dashboard local:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Depois, abra `http://127.0.0.1:8000`. O endpoint `/healthz` verifica SQLite e informa se o build do frontend está disponível.

Para compilar e publicar o frontend:

```bash
cd frontend
npm install
npm run build
cd ..
firebase deploy --only hosting,firestore:rules
```

O frontend hospedado lê o Firestore diretamente. A API FastAPI continua como ferramenta local de manutenção e não é necessária para o site publicado.

## Firebase e permissões

As regras em `firestore.rules` permitem leitura a usuários autenticados e reservam escrita e exclusão para administradores. Um administrador é representado por `admins/{uid}`.

```bash
python ops/grant_admin.py --email pessoa@exemplo.com
# ou
python ops/grant_admin.py --uid UID_DO_FIREBASE_AUTH
```

O bot usa Firebase Admin SDK quando a sincronização está ativa. Forneça a conta de serviço por configuração local; não a adicione ao repositório.

## Testes

```bash
python -m pytest -q
cd frontend
npm run build
```

## Estrutura

| Caminho | Responsabilidade |
| --- | --- |
| `main.py` | sessão Telethon, filtros, decisões e persistência |
| `offers.py` | extração de sinais e classificação |
| `verifier.py` | links, cupons e verificação HTTP/HTML |
| `storage.py` | SQLite, deduplicação e fila de sincronização |
| `app.py` | API FastAPI e entrega do build React |
| `firebase_setup.py` | integração opcional com Firebase |
| `frontend/` | dashboard em React, TypeScript e Tailwind |
| `ops/` | verificação de configuração e tarefas administrativas |

## Limitações

- Sites e formatos de mensagens mudam; parsers e verificadores podem precisar de ajustes.
- Detecção por sinais é heurística e não elimina revisão humana.
- O frontend do Firebase depende de Auth, Firestore e regras implantadas corretamente.
- A conta do Telegram continua sujeita às regras e limites da plataforma.

## Contribuição

Abra uma issue com uma mensagem de exemplo anonimizada, o resultado esperado e o resultado obtido. Em pull requests, mantenha as proteções de conta, privacidade e deduplicação, e execute os testes antes do envio.

## Licença

Distribuído sob a [Licença MIT](LICENSE).
