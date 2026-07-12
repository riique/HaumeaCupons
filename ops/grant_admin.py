from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firebase_setup import _utc_now, auth, client, initialize_firebase


def main() -> None:
    parser = argparse.ArgumentParser(description="Concede acesso admin ao dashboard via documento admins/{uid}.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--uid", help="Firebase Auth UID")
    group.add_argument("--email", help="Email do usuario no Firebase Auth")
    args = parser.parse_args()

    if not initialize_firebase() or auth is None:
        raise SystemExit("Firebase Admin SDK indisponivel; verifique FIREBASE_SERVICE_ACCOUNT/ADC.")

    uid = args.uid
    if args.email:
        uid = auth.get_user_by_email(args.email).uid

    db = client()
    if db is None:
        raise SystemExit("Firestore indisponivel.")

    db.collection("admins").document(str(uid)).set(
        {
            "uid": str(uid),
            "grantedAt": _utc_now(),
            "source": "ops/grant_admin.py",
        },
        merge=True,
    )
    print(f"admin ok: {uid}")


if __name__ == "__main__":
    main()
