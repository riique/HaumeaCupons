# Prompt para deploy completo no servidor

Use este prompt em um agente/terminal com acesso a sua maquina servidor. Ele assume que o codigo ja esta no GitHub e que os arquivos sensiveis serao transferidos por canal seguro, fora do Git.

Diretorio local do projeto nesta maquina:

```text
C:\Users\Henri\Desktop\Bot\HaumeaCupons
```

Prompt:

```text
Voce e meu agente de deploy tecnico. Preciso implantar o projeto HaumeaCupons no servidor 24h.

Repositorio:
https://github.com/riique/HaumeaCupons.git

Objetivo:
1. Clonar ou atualizar o repositorio no servidor.
2. Configurar ambiente Python.
3. Instalar dependencias Python com `pip install -e .`.
4. Instalar/buildar frontend com `npm install` e `npm run build` dentro de `frontend`.
5. Criar o diretorio `logs`.
6. Receber de mim, por canal seguro fora do Git, os arquivos:
   - `.env`
   - `haumea_cupons.session`
7. Colocar `.env` e `haumea_cupons.session` na raiz do projeto no servidor.
8. Garantir que `.env` tenha, no minimo:
   - `API_ID`
   - `API_HASH`
   - `PHONE`
   - `CHAT_GROUPS` com lista explicita de grupos, nao `all`
   - `ALLOW_ALL_CHATS=false`
   - `DEDUPE_TTL_SECONDS=1800`
   - `DASHBOARD_API_KEY` forte
9. Confirmar que o bot nao envia mensagens no Telegram. Ele deve apenas salvar findings no SQLite/dashboard.
10. Subir o backend/dashboard com:
    `uvicorn app:app --host 127.0.0.1 --port 8000`
11. Subir o bot com:
    `python main.py`
12. Configurar ambos como servicos persistentes do servidor, garantindo restart automatico.
13. Verificar:
    - `python -m pytest -q`
    - resposta de `/api/state`
    - logs sem erro de login/conexao

Regras de seguranca:
- Nunca commitar `.env`, `haumea_cupons.session`, logs, bancos SQLite ou build `frontend/dist`.
- Nao expor o dashboard publicamente sem `DASHBOARD_API_KEY` ou camada adicional de acesso.
- Rodar apenas uma instancia de `python main.py`.
- Se aparecer erro repetido do Telegram, parar o bot e investigar antes de reiniciar.
```

Arquivos sensiveis que voce deve transferir manualmente/por canal seguro:

```text
C:\Users\Henri\Desktop\Bot\HaumeaCupons\.env
C:\Users\Henri\Desktop\Bot\HaumeaCupons\haumea_cupons.session
```
