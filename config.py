from __future__ import annotations

import os
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Product:
    keywords: list[str]
    max_price: float

    @property
    def primary_keyword(self) -> str:
        return self.keywords[0] if self.keywords else ""


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

    @property
    def product_keywords(self) -> list[str]:
        return self.keywords


DATA_FILE = Path("data.json")
ENV_PRODUCT_MAX_PRICE = 1_000_000.0
DEFAULT_DATA = {
    "products": [{"keywords": ["iphone"], "max_price": 200.0}],
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


def _env_products_from_keywords(keywords: list[str]) -> list[dict[str, Any]]:
    # Seed: one product per keyword from .env, no price cap
    return [{"keywords": [keyword], "max_price": ENV_PRODUCT_MAX_PRICE} for keyword in keywords]


def _initial_data_from_env(chat_groups: str | None, product_keywords: list[str]) -> dict[str, Any]:
    data = _default_data()
    if product_keywords:
        data["products"] = _env_products_from_keywords(product_keywords)
    if chat_groups:
        data["chat_groups"] = _parse_chat_groups(chat_groups)
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
        # Support legacy single-keyword format
        if "keyword" in item and "keywords" not in item:
            kws = [str(item["keyword"]).strip().lower()]
        else:
            raw_kws = item.get("keywords", [])
            kws = [
                str(k).strip().lower()
                for k in (raw_kws if isinstance(raw_kws, list) else [raw_kws])
                if str(k).strip()
            ]
        kws = list(dict.fromkeys(kws))
        if not kws:
            continue
        try:
            max_price = float(item.get("max_price", 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid max_price for product {kws!r}") from exc
        if max_price < 0:
            raise RuntimeError(f"max_price must be >= 0 for product {kws!r}")
        products.append(Product(keywords=kws, max_price=max_price))

    if not products:
        products = [Product(**DEFAULT_DATA["products"][0])]
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
    product_keywords_env = _split_csv(os.getenv("PRODUCTS_KEYWORDS", ""))
    data = _load_data(initial_data=_initial_data_from_env(chat_groups_env, product_keywords_env))

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

    products_raw = data.get("products")
    products = _parse_products(products_raw or DEFAULT_DATA["products"])

    chat_groups_raw = data.get("chat_groups")
    if chat_groups_raw is None and chat_groups_env:
        chat_groups_raw = chat_groups_env
    chat_groups = _parse_chat_groups(chat_groups_raw if chat_groups_raw is not None else DEFAULT_DATA["chat_groups"])
    keywords = list(dict.fromkeys(kw.lower() for product in products for kw in product.keywords))
    allow_all_chats = _env_bool("ALLOW_ALL_CHATS", False)
    dedupe_ttl_seconds = max(60, _env_int("DEDUPE_TTL_SECONDS", 1800))

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
    )
