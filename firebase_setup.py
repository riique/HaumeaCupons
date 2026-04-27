from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import firebase_admin
    from firebase_admin import auth, credentials, firestore
    from google.cloud.firestore_v1 import FieldFilter
except ImportError:  # pragma: no cover - exercised when dependency is not installed locally
    firebase_admin = None
    auth = None
    credentials = None
    firestore = None
    FieldFilter = None


load_dotenv(dotenv_path=Path(".env"))
SERVICE_ACCOUNT_FILE = Path(
    os.getenv("FIREBASE_SERVICE_ACCOUNT", "haumea-cupons-firebase-adminsdk-fbsvc-225d0c512e.json")
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def initialize_firebase() -> bool:
    if firebase_admin is None:
        return False
    if firebase_admin._apps:
        return True

    try:
        if SERVICE_ACCOUNT_FILE.exists():
            cred = credentials.Certificate(str(SERVICE_ACCOUNT_FILE))
            firebase_admin.initialize_app(cred)
        elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("FIREBASE_USE_ADC", "").strip().lower() in {"1", "true", "yes", "on"}:
            firebase_admin.initialize_app()
        else:
            return False
        return True
    except Exception:
        return False


def firestore_available() -> bool:
    return initialize_firebase()


def client():
    if not initialize_firebase() or firestore is None:
        return None
    return firestore.client()


def verify_id_token(id_token: str) -> dict[str, Any] | None:
    if not initialize_firebase() or auth is None:
        return None
    try:
        return auth.verify_id_token(id_token)
    except Exception:
        return None


def _doc_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def product_from_doc(doc: Any, fallback_index: int = 0) -> dict[str, Any]:
    data = doc.to_dict() or {}
    raw_id = data.get("id", doc.id)
    try:
        product_id: int | str = int(raw_id)
    except (TypeError, ValueError):
        product_id = str(raw_id)
    return {
        "id": product_id,
        "keywords": list(data.get("keywords") or []),
        "max_price": float(data.get("maxPrice", data.get("max_price", 0)) or 0),
        "active": bool(data.get("active", True)),
        "created_by": data.get("createdBy", data.get("created_by", "")),
        "created_at": _doc_timestamp(data.get("createdAt", data.get("created_at", ""))),
        "_fallback_index": fallback_index,
    }


def list_products() -> list[dict[str, Any]] | None:
    db = client()
    if db is None:
        return None
    docs = db.collection("products").order_by("createdAt").stream()
    return [product_from_doc(doc, index) for index, doc in enumerate(docs)]


def save_product(product: dict[str, Any], *, created_by: str = "bot") -> dict[str, Any] | None:
    db = client()
    if db is None:
        return None
    product_id = str(product["id"])
    payload = {
        "id": product["id"],
        "keywords": product["keywords"],
        "maxPrice": product["max_price"],
        "createdBy": created_by,
        "active": True,
        "updatedAt": _utc_now(),
    }
    ref = db.collection("products").document(product_id)
    snap = ref.get()
    if not snap.exists:
        payload["createdAt"] = _utc_now()
    ref.set(payload, merge=True)
    return product_from_doc(ref.get())


def delete_product(product_id: int | str) -> bool:
    db = client()
    if db is None:
        return False
    db.collection("products").document(str(product_id)).delete()
    return True


def finding_from_doc(doc: Any) -> dict[str, Any]:
    data = doc.to_dict() or {}
    return {
        "id": doc.id,
        "timestamp": _doc_timestamp(data.get("timestamp")),
        "product_keyword": data.get("productKeyword", data.get("product_keyword", "")),
        "url": data.get("url", ""),
        "price_found": data.get("priceFound", data.get("price_found")),
        "price_ok": bool(data.get("priceOk", data.get("price_ok", False))),
        "source_group": data.get("sourceGroup", data.get("source_group", "")),
        "coupons": list(data.get("coupons") or []),
        "links": list(data.get("links") or []),
        "source_chat_id": data.get("sourceChatId", data.get("source_chat_id", "")),
        "source_message_id": data.get("sourceMessageId", data.get("source_message_id", "")),
        "user_id": data.get("userId", data.get("user_id", "bot")),
    }


def list_findings(limit: int = 200, offset: int = 0) -> list[dict[str, Any]] | None:
    db = client()
    if db is None:
        return None
    query = db.collection("findings").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit + offset)
    docs = list(query.stream())
    return [finding_from_doc(doc) for doc in docs[offset:]]


def save_finding(finding: dict[str, Any], *, user_id: str = "bot") -> str | None:
    db = client()
    if db is None:
        return None
    doc_id = str(finding.get("id") or "").strip()
    payload = {
        "timestamp": finding.get("timestamp") or _utc_now(),
        "productKeyword": finding.get("product_keyword", ""),
        "url": finding.get("url", ""),
        "priceFound": finding.get("price_found"),
        "priceOk": bool(finding.get("price_ok", False)),
        "sourceGroup": finding.get("source_group", ""),
        "coupons": list(finding.get("coupons") or []),
        "links": list(finding.get("links") or []),
        "sourceChatId": str(finding.get("source_chat_id") or ""),
        "sourceMessageId": str(finding.get("source_message_id") or ""),
        "userId": user_id,
        "updatedAt": _utc_now(),
    }
    if not doc_id:
        source_chat = payload["sourceChatId"]
        source_message = payload["sourceMessageId"]
        doc_id = f"{source_chat}_{source_message}" if source_chat and source_message else ""
    if doc_id:
        ref = db.collection("findings").document(doc_id)
        if not ref.get().exists:
            payload["createdAt"] = _utc_now()
        ref.set(payload, merge=True)
        return ref.id
    _, ref = db.collection("findings").add({**payload, "createdAt": _utc_now()})
    return ref.id


def delete_finding(finding_id: int | str) -> bool:
    db = client()
    if db is None:
        return False
    db.collection("findings").document(str(finding_id)).delete()
    return True


def clear_findings() -> bool:
    db = client()
    if db is None:
        return False
    for doc in db.collection("findings").limit(500).stream():
        doc.reference.delete()
    return True


def get_chat_groups() -> str | list[str] | None:
    db = client()
    if db is None:
        return None
    config = db.collection("chat_groups").document("config").get()
    if config.exists:
        data = config.to_dict() or {}
        if data.get("mode") == "all":
            return "all"
    query = db.collection("chat_groups")
    if FieldFilter is not None:
        query = query.where(filter=FieldFilter("active", "==", True))
    docs = query.stream()
    groups = [str((doc.to_dict() or {}).get("name") or doc.id).strip() for doc in docs if doc.id != "config"]
    groups = [group for group in groups if group]
    return groups or "all"


def save_chat_groups(groups: str | list[str]) -> bool:
    db = client()
    if db is None:
        return False
    config_ref = db.collection("chat_groups").document("config")
    if groups == "all":
        config_ref.set({"mode": "all", "active": True, "updatedAt": _utc_now()}, merge=True)
        return True
    config_ref.set({"mode": "list", "active": True, "updatedAt": _utc_now()}, merge=True)
    for group in groups:
        group_id = str(group).strip().lower().lstrip("@").replace("/", "_")
        if not group_id:
            continue
        db.collection("chat_groups").document(group_id).set(
            {"name": str(group).strip(), "active": True, "addedAt": _utc_now()},
            merge=True,
        )
    return True
