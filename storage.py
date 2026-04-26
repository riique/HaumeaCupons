from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_FILE = Path("logs/findings.sqlite3")
LEGACY_ALERTS_FILE = Path("logs/alerts.jsonl")


def init_findings_db(db_path: Path = DEFAULT_DB_FILE) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                product_keyword TEXT NOT NULL,
                url TEXT NOT NULL,
                price_found REAL,
                price_ok INTEGER NOT NULL,
                source_group TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _table_is_empty(db_path: Path) -> bool:
    init_findings_db(db_path)
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    return int(count) == 0


def add_finding(
    *,
    product_keyword: str,
    url: str,
    price_found: float | None,
    price_ok: bool,
    source_group: str,
    timestamp: str | None = None,
    db_path: Path = DEFAULT_DB_FILE,
) -> int:
    init_findings_db(db_path)
    created_at = timestamp or datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO findings (
                timestamp,
                product_keyword,
                url,
                price_found,
                price_ok,
                source_group
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                product_keyword.strip(),
                url.strip(),
                price_found,
                1 if price_ok else 0,
                source_group.strip(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_findings(
    limit: int = 200,
    offset: int = 0,
    db_path: Path = DEFAULT_DB_FILE,
) -> list[dict[str, Any]]:
    init_findings_db(db_path)
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                id,
                timestamp,
                product_keyword,
                url,
                price_found,
                price_ok,
                source_group
            FROM findings
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (safe_limit, safe_offset),
        ).fetchall()

    return [
        {
            "id": int(row["id"]),
            "timestamp": row["timestamp"],
            "product_keyword": row["product_keyword"],
            "url": row["url"],
            "price_found": row["price_found"],
            "price_ok": bool(row["price_ok"]),
            "source_group": row["source_group"],
        }
        for row in rows
    ]


def migrate_alerts_jsonl(
    legacy_path: Path = LEGACY_ALERTS_FILE,
    db_path: Path = DEFAULT_DB_FILE,
) -> int:
    if not legacy_path.exists() or not _table_is_empty(db_path):
        return 0

    migrated = 0
    with legacy_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue

            links = item.get("links")
            if not isinstance(links, list):
                continue

            timestamp = str(item.get("ts") or item.get("timestamp") or datetime.now(timezone.utc).isoformat())
            source_group = str(item.get("chat") or item.get("source_group") or "")
            for link in links:
                if not isinstance(link, dict):
                    continue
                url = str(link.get("url") or "").strip()
                if not url:
                    continue
                raw_price = link.get("price")
                try:
                    price_found = float(raw_price) if raw_price is not None else None
                except (TypeError, ValueError):
                    price_found = None
                add_finding(
                    timestamp=timestamp,
                    product_keyword=str(link.get("product_keyword") or ""),
                    url=url,
                    price_found=price_found,
                    price_ok=bool(link.get("price_ok")),
                    source_group=source_group,
                    db_path=db_path,
                )
                migrated += 1

    return migrated
