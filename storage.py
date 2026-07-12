from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_FILE = Path("logs/findings.sqlite3")
LEGACY_ALERTS_FILE = Path("logs/alerts.jsonl")
CURRENT_SCHEMA_VERSION = 2


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def init_findings_db(db_path: Path = DEFAULT_DB_FILE) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                product_keyword TEXT NOT NULL,
                url TEXT NOT NULL,
                price_found REAL,
                price_ok INTEGER NOT NULL,
                source_group TEXT NOT NULL,
                coupons TEXT NOT NULL DEFAULT '[]',
                links TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        # Migrate: add columns if they don't exist yet
        existing = {row[1] for row in connection.execute("PRAGMA table_info(findings)").fetchall()}
        if "coupons" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN coupons TEXT NOT NULL DEFAULT '[]'")
        if "links" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN links TEXT NOT NULL DEFAULT '[]'")
        if "source_chat_id" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN source_chat_id TEXT NOT NULL DEFAULT ''")
        if "source_message_id" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN source_message_id TEXT NOT NULL DEFAULT ''")
        if "message_hash" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN message_hash TEXT NOT NULL DEFAULT ''")
        if "url_hash" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN url_hash TEXT NOT NULL DEFAULT ''")
        if "product_title" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN product_title TEXT NOT NULL DEFAULT ''")
        if "merchant" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN merchant TEXT NOT NULL DEFAULT ''")
        if "message_type" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN message_type TEXT NOT NULL DEFAULT ''")
        if "match_reason" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN match_reason TEXT NOT NULL DEFAULT ''")
        if "confidence" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN confidence REAL")
        if "raw_message" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN raw_message TEXT NOT NULL DEFAULT ''")
        if "decision" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN decision TEXT NOT NULL DEFAULT 'approved'")
        if "matched_rule_id" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN matched_rule_id TEXT NOT NULL DEFAULT ''")
        if "rule_name" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN rule_name TEXT NOT NULL DEFAULT ''")
        if "detected_title" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN detected_title TEXT NOT NULL DEFAULT ''")
        if "price_source" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN price_source TEXT NOT NULL DEFAULT ''")
        if "reason_codes" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN reason_codes TEXT NOT NULL DEFAULT '[]'")
        if "score_breakdown" not in existing:
            connection.execute("ALTER TABLE findings ADD COLUMN score_breakdown TEXT NOT NULL DEFAULT '{}'")
        if "schema_version" not in existing:
            connection.execute(f"ALTER TABLE findings ADD COLUMN schema_version INTEGER NOT NULL DEFAULT {CURRENT_SCHEMA_VERSION}")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_source_message
            ON findings(source_chat_id, source_message_id)
            WHERE source_chat_id != '' AND source_message_id != ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_findings_timestamp
            ON findings(timestamp)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_findings_decision_time
            ON findings(decision, timestamp)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_findings_message_hash
            ON findings(message_hash)
            WHERE message_hash != ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_findings_url_hash
            ON findings(url_hash)
            WHERE url_hash != ''
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source_group TEXT NOT NULL,
                source_chat_id TEXT NOT NULL DEFAULT '',
                source_message_id TEXT NOT NULL DEFAULT '',
                message_hash TEXT NOT NULL DEFAULT '',
                decision TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                message_type TEXT NOT NULL DEFAULT '',
                product_title TEXT NOT NULL DEFAULT '',
                merchant TEXT NOT NULL DEFAULT '',
                price_found REAL,
                confidence REAL,
                links_count INTEGER NOT NULL DEFAULT 0,
                coupons_count INTEGER NOT NULL DEFAULT 0,
                raw_preview TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_message_events_group_time
            ON message_events(source_group, timestamp)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_message_events_source_message
            ON message_events(source_chat_id, source_message_id, decision)
            WHERE source_chat_id != '' AND source_message_id != ''
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                dedupe_key TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_outbox_target_dedupe
            ON sync_outbox(target, dedupe_key)
            WHERE dedupe_key != ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sync_outbox_status_created
            ON sync_outbox(status, created_at)
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
            VALUES (?, ?)
            """,
            (CURRENT_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()


def enqueue_sync_outbox(
    *,
    target: str,
    payload: dict[str, Any],
    dedupe_key: str = "",
    db_path: Path = DEFAULT_DB_FILE,
) -> int:
    init_findings_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(db_path)) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO sync_outbox(target, dedupe_key, payload, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (target, dedupe_key.strip(), json.dumps(payload, ensure_ascii=False), now, now),
            )
        except sqlite3.IntegrityError:
            row = connection.execute(
                """
                SELECT id FROM sync_outbox
                WHERE target = ? AND dedupe_key = ?
                LIMIT 1
                """,
                (target, dedupe_key.strip()),
            ).fetchone()
            if row:
                return int(row[0])
            raise
        connection.commit()
        return int(cursor.lastrowid)


def get_pending_sync_outbox(
    *,
    target: str,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_FILE,
) -> list[dict[str, Any]]:
    init_findings_db(db_path)
    safe_limit = max(1, min(int(limit), 100))
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, target, dedupe_key, payload, attempts
            FROM sync_outbox
            WHERE target = ? AND status IN ('pending', 'retry')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (target, safe_limit),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}
        items.append(
            {
                "id": int(row["id"]),
                "target": row["target"],
                "dedupe_key": row["dedupe_key"],
                "payload": payload if isinstance(payload, dict) else {},
                "attempts": int(row["attempts"] or 0),
            }
        )
    return items


def mark_sync_outbox_done(*, item_id: int, db_path: Path = DEFAULT_DB_FILE) -> None:
    init_findings_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            UPDATE sync_outbox
            SET status = 'done', updated_at = ?, last_error = ''
            WHERE id = ?
            """,
            (now, int(item_id)),
        )
        connection.commit()


def mark_sync_outbox_failed(
    *,
    item_id: int,
    error: str,
    max_attempts: int = 10,
    db_path: Path = DEFAULT_DB_FILE,
) -> None:
    init_findings_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(db_path)) as connection:
        attempts = int(
            connection.execute("SELECT attempts FROM sync_outbox WHERE id = ?", (int(item_id),)).fetchone()[0]
        ) + 1
        status = "failed" if attempts >= max(1, int(max_attempts)) else "retry"
        connection.execute(
            """
            UPDATE sync_outbox
            SET status = ?, attempts = ?, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, attempts, error[:500], now, int(item_id)),
        )
        connection.commit()


def _table_is_empty(db_path: Path) -> bool:
    init_findings_db(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    return int(count) == 0


def add_finding(
    *,
    product_keyword: str,
    url: str,
    price_found: float | None,
    price_ok: bool,
    source_group: str,
    coupons: list[str] | None = None,
    links: list[str] | None = None,
    source_chat_id: str | int | None = None,
    source_message_id: str | int | None = None,
    message_hash: str = "",
    url_hash: str = "",
    product_title: str = "",
    merchant: str = "",
    message_type: str = "",
    match_reason: str = "",
    confidence: float | None = None,
    raw_message: str = "",
    decision: str = "approved",
    matched_rule_id: str = "",
    rule_name: str = "",
    detected_title: str = "",
    price_source: str = "",
    reason_codes: list[str] | None = None,
    score_breakdown: dict[str, float] | None = None,
    timestamp: str | None = None,
    db_path: Path = DEFAULT_DB_FILE,
) -> int:
    init_findings_db(db_path)
    created_at = timestamp or datetime.now(timezone.utc).isoformat()
    source_chat = str(source_chat_id or "").strip()
    source_message = str(source_message_id or "").strip()
    with closing(sqlite3.connect(db_path)) as connection:
        if source_chat and source_message:
            existing = connection.execute(
                """
                SELECT id FROM findings
                WHERE source_chat_id = ? AND source_message_id = ?
                LIMIT 1
                """,
                (source_chat, source_message),
            ).fetchone()
            if existing:
                return int(existing[0])
        try:
            cursor = connection.execute(
                """
                INSERT INTO findings (
                    timestamp, product_keyword, url,
                    price_found, price_ok, source_group,
                    coupons, links,
                    source_chat_id, source_message_id,
                    message_hash, url_hash,
                    product_title, merchant, message_type,
                    match_reason, confidence, raw_message,
                    decision, matched_rule_id, rule_name,
                    detected_title, price_source, reason_codes,
                    score_breakdown, schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    product_keyword.strip(),
                    url.strip(),
                    price_found,
                    1 if price_ok else 0,
                    source_group.strip(),
                    json.dumps(coupons or []),
                    json.dumps(links or []),
                    source_chat,
                    source_message,
                    message_hash.strip(),
                    url_hash.strip(),
                    product_title.strip(),
                    merchant.strip(),
                    message_type.strip(),
                    match_reason.strip(),
                    confidence,
                    raw_message,
                    decision.strip() or "approved",
                    matched_rule_id.strip(),
                    rule_name.strip(),
                    detected_title.strip(),
                    price_source.strip(),
                    json.dumps(reason_codes or []),
                    json.dumps(score_breakdown or {}),
                    CURRENT_SCHEMA_VERSION,
                ),
            )
        except sqlite3.IntegrityError:
            if not source_chat or not source_message:
                raise
            existing = connection.execute(
                """
                SELECT id FROM findings
                WHERE source_chat_id = ? AND source_message_id = ?
                LIMIT 1
                """,
                (source_chat, source_message),
            ).fetchone()
            if not existing:
                raise
            return int(existing[0])
        connection.commit()
        return int(cursor.lastrowid)


def finding_exists(
    *,
    source_chat_id: str | int | None = None,
    source_message_id: str | int | None = None,
    message_hash: str = "",
    db_path: Path = DEFAULT_DB_FILE,
) -> bool:
    init_findings_db(db_path)
    source_chat = str(source_chat_id or "").strip()
    source_message = str(source_message_id or "").strip()
    with closing(sqlite3.connect(db_path)) as connection:
        if source_chat and source_message:
            row = connection.execute(
                """
                SELECT 1 FROM findings
                WHERE source_chat_id = ? AND source_message_id = ?
                LIMIT 1
                """,
                (source_chat, source_message),
            ).fetchone()
            if row:
                return True
        if message_hash:
            row = connection.execute(
                """
                SELECT 1 FROM findings
                WHERE message_hash = ?
                LIMIT 1
                """,
                (message_hash.strip(),),
            ).fetchone()
            return row is not None
    return False


def add_message_event(
    *,
    source_group: str,
    decision: str,
    reason: str = "",
    source_chat_id: str | int | None = None,
    source_message_id: str | int | None = None,
    message_hash: str = "",
    message_type: str = "",
    product_title: str = "",
    merchant: str = "",
    price_found: float | None = None,
    confidence: float | None = None,
    links_count: int = 0,
    coupons_count: int = 0,
    raw_preview: str = "",
    timestamp: str | None = None,
    db_path: Path = DEFAULT_DB_FILE,
) -> int:
    init_findings_db(db_path)
    created_at = timestamp or datetime.now(timezone.utc).isoformat()
    source_chat = str(source_chat_id or "").strip()
    source_message = str(source_message_id or "").strip()
    with closing(sqlite3.connect(db_path)) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO message_events (
                    timestamp, source_group, source_chat_id, source_message_id,
                    message_hash, decision, reason, message_type, product_title,
                    merchant, price_found, confidence, links_count, coupons_count,
                    raw_preview
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    source_group.strip(),
                    source_chat,
                    source_message,
                    message_hash.strip(),
                    decision.strip(),
                    reason.strip(),
                    message_type.strip(),
                    product_title.strip(),
                    merchant.strip(),
                    price_found,
                    confidence,
                    max(0, int(links_count)),
                    max(0, int(coupons_count)),
                    raw_preview[:500],
                ),
            )
        except sqlite3.IntegrityError:
            row = connection.execute(
                """
                SELECT id FROM message_events
                WHERE source_chat_id = ? AND source_message_id = ? AND decision = ?
                LIMIT 1
                """,
                (source_chat, source_message, decision.strip()),
            ).fetchone()
            if row:
                return int(row[0])
            raise
        connection.commit()
        return int(cursor.lastrowid)


def get_message_event_stats(
    limit: int = 50,
    db_path: Path = DEFAULT_DB_FILE,
) -> list[dict[str, Any]]:
    init_findings_db(db_path)
    safe_limit = max(1, min(int(limit), 200))
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                source_group,
                decision,
                message_type,
                COUNT(*) AS total,
                AVG(confidence) AS avg_confidence,
                SUM(CASE WHEN price_found IS NOT NULL THEN 1 ELSE 0 END) AS with_price,
                SUM(CASE WHEN links_count > 0 THEN 1 ELSE 0 END) AS with_links,
                SUM(CASE WHEN coupons_count > 0 THEN 1 ELSE 0 END) AS with_coupons,
                MIN(timestamp) AS first_seen,
                MAX(timestamp) AS last_seen
            FROM message_events
            GROUP BY source_group, decision, message_type
            ORDER BY total DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [
        {
            "source_group": row["source_group"],
            "decision": row["decision"],
            "message_type": row["message_type"],
            "total": int(row["total"]),
            "avg_confidence": row["avg_confidence"],
            "with_price": int(row["with_price"] or 0),
            "with_links": int(row["with_links"] or 0),
            "with_coupons": int(row["with_coupons"] or 0),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]


def get_findings(
    limit: int = 200,
    offset: int = 0,
    db_path: Path = DEFAULT_DB_FILE,
) -> list[dict[str, Any]]:
    init_findings_db(db_path)
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))
    with closing(sqlite3.connect(db_path)) as connection:
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
                source_group,
                coupons,
                links,
                source_chat_id,
                source_message_id,
                message_hash,
                url_hash,
                product_title,
                merchant,
                message_type,
                match_reason,
                confidence,
                raw_message,
                decision,
                matched_rule_id,
                rule_name,
                detected_title,
                price_source,
                reason_codes,
                score_breakdown,
                schema_version
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
            "coupons": json.loads(row["coupons"]) if row["coupons"] else [],
            "links": json.loads(row["links"]) if row["links"] else [],
            "source_chat_id": row["source_chat_id"],
            "source_message_id": row["source_message_id"],
            "message_hash": row["message_hash"],
            "url_hash": row["url_hash"],
            "product_title": row["product_title"],
            "merchant": row["merchant"],
            "message_type": row["message_type"],
            "match_reason": row["match_reason"],
            "confidence": row["confidence"],
            "raw_message": row["raw_message"],
            "decision": row["decision"],
            "matched_rule_id": row["matched_rule_id"],
            "rule_name": row["rule_name"],
            "detected_title": row["detected_title"],
            "price_source": row["price_source"],
            "reason_codes": _json_list(row["reason_codes"]),
            "score_breakdown": json.loads(row["score_breakdown"]) if row["score_breakdown"] else {},
            "schema_version": int(row["schema_version"] or 1),
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
