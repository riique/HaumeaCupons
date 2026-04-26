# HaumeaCupons

Telethon bot para monitorar grupos/canais do Telegram, detectar mensagens com palavras-chave de produtos, extrair links e cupons, verificar páginas com `aiohttp` + BeautifulSoup, validar faixa de preço e enviar alertas para o usuário principal. Inclui dashboard FastAPI + React para editar produtos/grupos e acompanhar findings em SQLite.

## Setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p logs
python main.py
```

No primeiro login, o Telethon pode pedir o código enviado pelo Telegram para o telefone configurado em `PHONE`.

## Variáveis `.env`

- `API_ID`: API ID do Telegram.
- `API_HASH`: API hash do Telegram.
- `PHONE`: telefone da conta, com DDI.
- `MAIN_USER_ID`: ID numérico do usuário que receberá os alertas.
Produtos e grupos ficam em `data.json`:

```json
{
  "products": [{"keyword": "iphone", "min_price": 50.0, "max_price": 200.0}],
  "chat_groups": "all"
}
```

`chat_groups` aceita `"all"` ou uma lista de IDs/usernames.

## Dashboard

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000`. A tela permite adicionar, editar, listar e excluir produtos, atualizar grupos e acompanhar findings com polling em `/api/findings`.

Em produção, gere o build do frontend antes de subir o FastAPI:

```bash
cd frontend
npm install
npm run build
```

O backend serve `frontend/dist/index.html` em `/` e mantém as APIs em `/api/*`.

Para expor via Cloudflare Tunnel:

```bash
./tunnel.sh
```

## Segurança

- O dashboard não tem autenticação própria; mantenha o bind em `127.0.0.1` quando for uso local.
- Ao usar túnel público, proteja o acesso com Cloudflare Access ou outra camada de autenticação.
- `data.json` é salvo de forma atômica para reduzir risco de corrupção em queda/interrupção.
- A API valida produtos, grupos e faixa de preço com Pydantic.
- O verificador bloqueia URLs locais/privadas, limita redirects, limita resposta a 1MB e usa concorrência controlada.
- Não coloque tokens, sessão Telethon ou `.env` em repositório público.

## Teste local

O simulador não faz login real no Telegram. Ele cria um evento dummy, simula uma mensagem com link e cupom, mocka a verificação HTTP e valida o envio do alerta.

```bash
source .venv/bin/activate
pip install -e .
python -m pytest test_sim.py
```

## Arquivos

- `config.py`: leitura e validação de ambiente.
- `app.py`: API FastAPI e entrega do build React.
- `frontend/`: dashboard React + TypeScript + Tailwind.
- `storage.py`: persistência SQLite de findings.
- `data.json`: produtos e grupos monitorados.
- `verifier.py`: extração de links/cupons e verificação HTTP/HTML.
- `main.py`: cliente Telethon, handler `NewMessage`, alerta, hot-reload e findings.
- `test_sim.py`: simulação dummy de login/evento.
- `logs/`: saída local de execução e banco SQLite.
- `tunnel.sh`: túnel Cloudflare para `localhost:8000`.
