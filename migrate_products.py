from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from firebase_setup import save_chat_groups, save_product


DATA_FILE = Path("data.json")


def load_data() -> dict[str, Any]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RuntimeError("data.json must contain a JSON object")
    return data


def main() -> None:
    data = load_data()
    products = data.get("products", [])
    if not isinstance(products, list):
        raise RuntimeError("data.json products must be a list")

    migrated = 0
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            continue
        payload = {
            "id": product.get("id", index),
            "keywords": product.get("keywords", []),
            "max_price": product.get("max_price", product.get("maxPrice", 0)),
        }
        if save_product(payload, created_by="migration") is None:
            raise RuntimeError("Firestore não está disponível. Verifique a service account.")
        migrated += 1

    chat_groups = data.get("chat_groups")
    if chat_groups is not None and not save_chat_groups(chat_groups):
        raise RuntimeError("Falha ao migrar chat_groups para Firestore.")

    print(f"Migrados {migrated} produtos para Firestore.")


if __name__ == "__main__":
    main()
