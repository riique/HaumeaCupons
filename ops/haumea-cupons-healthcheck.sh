#!/usr/bin/env bash
set -euo pipefail

systemctl --user is-active --quiet haumea-cupons-bot.service

cd /home/henriquelenz/Haumea/HaumeaCupons
.venv/bin/python - <<'PY'
from pathlib import Path
import sqlite3

db_path = Path("logs/findings.sqlite3")
with sqlite3.connect(db_path) as conn:
    conn.execute("SELECT 1").fetchone()
print("bot active; sqlite ok")
PY
