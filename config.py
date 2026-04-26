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


@dataclass(frozen=True)
class Product:
    keyword: str
    min_price: float
    max_price: float


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str
    main_user_id: int
    chat_groups: str | list[str]
    products: list[Product]
    keywords: list[str]
    session_name: str = "haumea_cupons"
    logs_dir: Path = Path("logs")

    @property
    def product_keywords(self) -> list[str]:
        return self.keywords


DATA_FILE = Path("data.json")
DEFAULT_DATA = {
    "products": [{"keyword": "iphone", "min_price": 50.0, "max_price": 200.0}],
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


def _load_data(path: Path = DATA_FILE) -> dict[str, Any]:
    if not path.exists():
        data = _default_data()
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
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        try:
            min_price = float(item.get("min_price", 0))
            max_price = float(item.get("max_price", 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid price range for product {keyword!r}") from exc
        if min_price < 0 or max_price < min_price:
            raise RuntimeError(f"Invalid min/max price for product {keyword!r}")
        products.append(Product(keyword=keyword, min_price=min_price, max_price=max_price))

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
    data = _load_data()

    required = {
        "API_ID": os.getenv("API_ID"),
        "API_HASH": os.getenv("API_HASH"),
        "PHONE": os.getenv("PHONE"),
        "MAIN_USER_ID": os.getenv("MAIN_USER_ID"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    try:
        api_id = int(required["API_ID"] or "")
        main_user_id = int(required["MAIN_USER_ID"] or "")
    except ValueError as exc:
        raise RuntimeError("API_ID and MAIN_USER_ID must be integers") from exc

    products = _parse_products(data.get("products", DEFAULT_DATA["products"]))
    chat_groups = _parse_chat_groups(data.get("chat_groups", DEFAULT_DATA["chat_groups"]))

    return Settings(
        api_id=api_id,
        api_hash=required["API_HASH"] or "",
        phone=required["PHONE"] or "",
        main_user_id=main_user_id,
        chat_groups=chat_groups,
        products=products,
        keywords=[product.keyword.lower() for product in products],
    )
