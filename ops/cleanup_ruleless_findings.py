from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firebase_setup import client, initialize_firebase
from storage import DEFAULT_DB_FILE


def cleanup_sqlite(*, apply: bool, db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM findings WHERE COALESCE(matched_rule_id, '') = ''"
            ).fetchone()[0]
        )
        if apply and count:
            conn.execute("DELETE FROM findings WHERE COALESCE(matched_rule_id, '') = ''")
            conn.execute(
                """
                DELETE FROM sync_outbox
                WHERE target = 'firestore_finding'
                  AND (
                    payload NOT LIKE '%matched_rule_id%'
                    OR payload LIKE '%\"matched_rule_id\": \"\"%'
                    OR payload LIKE '%\"matched_rule_id\":\"\"%'
                  )
                """
            )
            conn.commit()
        return count


def cleanup_firestore(*, apply: bool) -> int:
    if not initialize_firebase():
        raise SystemExit("Firebase Admin SDK indisponivel.")
    db = client()
    if db is None:
        raise SystemExit("Firestore indisponivel.")

    batch = db.batch()
    batch_size = 0
    total = 0
    for doc in db.collection("findings").stream():
        data = doc.to_dict() or {}
        matched_rule_id = str(data.get("matchedRuleId", data.get("matched_rule_id", "")) or "").strip()
        if matched_rule_id:
            continue
        total += 1
        if apply:
            batch.delete(doc.reference)
            batch_size += 1
            if batch_size >= 400:
                batch.commit()
                batch = db.batch()
                batch_size = 0
    if apply and batch_size:
        batch.commit()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove findings sem regra associada.")
    parser.add_argument("--apply", action="store_true", help="Executa a limpeza. Sem isso, apenas conta.")
    parser.add_argument("--skip-firestore", action="store_true")
    parser.add_argument("--db", default=str(DEFAULT_DB_FILE))
    args = parser.parse_args()

    sqlite_count = cleanup_sqlite(apply=args.apply, db_path=Path(args.db))
    print(f"sqlite ruleless findings: {sqlite_count}{' deleted' if args.apply else ''}")

    if not args.skip_firestore:
        firestore_count = cleanup_firestore(apply=args.apply)
        print(f"firestore ruleless findings: {firestore_count}{' deleted' if args.apply else ''}")


if __name__ == "__main__":
    main()
