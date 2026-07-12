from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("HAUMEA_CONFIG_SKIP_FIRESTORE", "true")

from config import load_settings
from storage import init_findings_db


def main() -> None:
    settings = load_settings()
    skip_firestore = os.getenv("HAUMEA_CONFIG_SKIP_FIRESTORE", "").strip().lower() in {"1", "true", "yes", "on"}
    if settings.chat_groups == "all" and not settings.bot_token and not settings.allow_all_chats and not skip_firestore:
        raise SystemExit("chat_groups=all bloqueado para conta de usuario sem ALLOW_ALL_CHATS=true")
    if settings.chat_groups == "all" and not settings.bot_token and not settings.allow_all_chats:
        print("config warning: Firestore ignorado no preflight; validacao final ocorre no main.py")
    init_findings_db(settings.logs_dir / "findings.sqlite3")
    print("config ok")


if __name__ == "__main__":
    main()
