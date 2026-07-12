from __future__ import annotations

import os
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

try:
    from firebase_setup import get_chat_groups as firestore_get_chat_groups
    from firebase_setup import list_products as firestore_list_products
except Exception:  # pragma: no cover - Firestore dependency may be unavailable locally
    firestore_get_chat_groups = None
    firestore_list_products = None


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return _env_bool_value(value)


def _env_bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


def _env_choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in choices:
        raise RuntimeError(f"{name} must be one of: {', '.join(sorted(choices))}")
    return value


@dataclass(frozen=True)
class Product:
    keywords: list[str]
    max_price: float
    id: int | str = ""
    name: str = ""
    min_price: float | None = None
    exclude_terms: list[str] | None = None
    merchants: list[str] | None = None
    category: str = ""
    auto_approve: bool = True
    notify_email: str = ""
    notify_hermes: bool = False
    notify_hermes_explicit: bool = False

    @property
    def primary_keyword(self) -> str:
        return self.name or (self.keywords[0] if self.keywords else "")

    @property
    def match_terms(self) -> list[str]:
        return self.keywords

    @property
    def rule_id(self) -> str:
        return str(self.id or self.primary_keyword)


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    chat_groups: str | list[str]
    products: list[Product]
    keywords: list[str]
    bot_token: str = ""
    phone: str = ""
    session_name: str = "haumea_cupons"
    logs_dir: Path = Path("logs")
    allow_all_chats: bool = False
    dedupe_ttl_seconds: int = 1800
    detection_mode: Literal["keywords", "signals", "hybrid"] = "hybrid"
    min_offer_confidence: float = 0.62
    message_audit_enabled: bool = True
    store_raw_messages: bool = False
    signal_only_max_price: float = 0.0

    @property
    def product_keywords(self) -> list[str]:
        return self.keywords


DATA_FILE = Path("data.json")
DEFAULT_DATA = {
    "products": [],
    "chat_groups": "all",
}


def _default_data() -> dict[str, Any]:
    return deepcopy(DEFAULT_DATA)


def _atomic_save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    tmp_path.replace(path)


def _initial_data_from_env(chat_groups: str | None) -> dict[str, Any]:
    data = _default_data()
    if chat_groups:
        data["chat_groups"] = _parse_chat_groups(chat_groups)
    product_keywords = os.getenv("PRODUCTS_KEYWORDS", "")
    if product_keywords:
        data["products"] = [
            {"keywords": [keyword], "max_price": 0}
            for keyword in _split_csv(product_keywords)
        ]
    return data


def _load_data(path: Path = DATA_FILE, initial_data: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        data = deepcopy(initial_data) if initial_data is not None else _default_data()
        _atomic_save_json(path, data)
        return data
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RuntimeError("data.json must contain a JSON object")
    return data


def _parse_products(raw: Any) -> list[Product]:
    products: list[Product] = []
    if not isinstance(raw, list):
        raise RuntimeError("data.json products must be a list")

    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id", "")
        name = str(item.get("name", item.get("title", "")) or "").strip()

        # Support legacy single-keyword format and the new rule terminology.
        if "keyword" in item and "keywords" not in item:
            kws = [str(item["keyword"]).strip().lower()]
        else:
            raw_kws = item.get("match_terms", item.get("matchTerms", item.get("keywords", [])))
            kws = [
                str(k).strip().lower()
                for k in (raw_kws if isinstance(raw_kws, list) else [raw_kws])
                if str(k).strip()
            ]
        kws = list(dict.fromkeys(kws))
        if not kws:
            continue
        try:
            max_price = float(item.get("max_price", item.get("maxPrice", 0)))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid max_price for product {kws!r}") from exc
        if max_price < 0:
            raise RuntimeError(f"max_price must be >= 0 for product {kws!r}")
        raw_min_price = item.get("min_price", item.get("minPrice"))
        min_price: float | None
        if raw_min_price in (None, ""):
            min_price = None
        else:
            try:
                min_price = float(raw_min_price)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid min_price for product {kws!r}") from exc
            if min_price < 0:
                raise RuntimeError(f"min_price must be >= 0 for product {kws!r}")
        raw_exclude_terms = item.get("exclude_terms", item.get("excludeTerms", []))
        exclude_terms = [
            str(k).strip().lower()
            for k in (raw_exclude_terms if isinstance(raw_exclude_terms, list) else [raw_exclude_terms])
            if str(k).strip()
        ]
        raw_merchants = item.get("merchants", item.get("merchant", []))
        merchants = [
            str(k).strip().lower()
            for k in (raw_merchants if isinstance(raw_merchants, list) else [raw_merchants])
            if str(k).strip()
        ]
        category = str(item.get("category", "") or "").strip().lower()
        auto_approve = _env_bool_value(item.get("auto_approve", item.get("autoApprove", True)), True)
        notify_email = str(item.get("notify_email", item.get("created_by", ""))).strip()
        notify_key = next(
            (
                key
                for key in ("notify_hermes", "notifyHermes", "notify_telegram", "notifyTelegram")
                if key in item
            ),
            "",
        )
        notify_explicit = bool(notify_key)
        notify_hermes = _env_bool_value(item.get(notify_key)) if notify_explicit else False
        products.append(
            Product(
                keywords=kws,
                max_price=max_price,
                id=raw_id,
                name=name,
                min_price=min_price,
                exclude_terms=exclude_terms,
                merchants=merchants,
                category=category,
                auto_approve=auto_approve,
                notify_email=notify_email,
                notify_hermes=notify_hermes,
                notify_hermes_explicit=notify_explicit,
            )
        )

    return products


def _parse_chat_groups(raw: Any) -> str | list[str]:
    if raw == "all":
        return "all"
    if isinstance(raw, str):
        parsed = _split_csv(raw)
        return "all" if raw.strip().lower() == "all" else parsed
    if isinstance(raw, list):
        parsed = [str(item).strip() for item in raw if str(item).strip()]
        return parsed or "all"
    return "all"


def load_settings() -> Settings:
    load_dotenv()
    chat_groups_env = os.getenv("CHAT_GROUPS")
    data = _load_data(initial_data=_initial_data_from_env(chat_groups_env))

    api_id_raw = os.getenv("API_ID", "")
    api_hash = os.getenv("API_HASH", "")
    bot_token = os.getenv("BOT_TOKEN", "")
    phone = os.getenv("PHONE", "")

    if not api_id_raw or not api_hash:
        raise RuntimeError("Missing required env vars: API_ID, API_HASH")
    if not bot_token and not phone:
        raise RuntimeError("Set BOT_TOKEN (recommended) or PHONE in .env")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("API_ID must be an integer") from exc

    skip_firestore_config = _env_bool("HAUMEA_CONFIG_SKIP_FIRESTORE", False)
    firestore_products = None if skip_firestore_config else (firestore_list_products() if firestore_list_products is not None else None)
    products_source = firestore_products if firestore_products is not None else data.get("products", [])
    products_raw = [
        product
        for product in (products_source or [])
        if not isinstance(product, dict) or product.get("active", True)
    ]
    products = _parse_products(products_raw)

    firestore_chat_groups = None if skip_firestore_config else (firestore_get_chat_groups() if firestore_get_chat_groups is not None else None)
    chat_groups_raw = firestore_chat_groups if firestore_chat_groups is not None else data.get("chat_groups")
    if chat_groups_raw is None and chat_groups_env:
        chat_groups_raw = chat_groups_env
    chat_groups = _parse_chat_groups(chat_groups_raw if chat_groups_raw is not None else DEFAULT_DATA["chat_groups"])
    keywords = list(dict.fromkeys(kw.lower() for product in products for kw in product.keywords))
    allow_all_chats = _env_bool("ALLOW_ALL_CHATS", False)
    dedupe_ttl_seconds = max(60, _env_int("DEDUPE_TTL_SECONDS", 1800))
    detection_mode = _env_choice("DETECTION_MODE", "hybrid", {"keywords", "signals", "hybrid"})
    min_offer_confidence = min(1.0, max(0.0, _env_float("MIN_OFFER_CONFIDENCE", 0.62)))
    message_audit_enabled = _env_bool("MESSAGE_AUDIT_ENABLED", True)
    store_raw_messages = _env_bool("STORE_RAW_MESSAGES", False)
    signal_only_max_price = max(0.0, _env_float("SIGNAL_ONLY_MAX_PRICE", 0.0))

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        bot_token=bot_token,
        phone=phone,
        chat_groups=chat_groups,
        products=products,
        keywords=keywords,
        allow_all_chats=allow_all_chats,
        dedupe_ttl_seconds=dedupe_ttl_seconds,
        detection_mode=detection_mode,  # type: ignore[arg-type]
        min_offer_confidence=min_offer_confidence,
        message_audit_enabled=message_audit_enabled,
        store_raw_messages=store_raw_messages,
        signal_only_max_price=signal_only_max_price,
    )
