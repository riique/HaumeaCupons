from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import DATA_FILE, DEFAULT_DATA, _atomic_save_json


LOGS_FILE = Path("logs/alerts.jsonl")
MAX_FINDINGS = 200

app = FastAPI(title="HaumeaCupons Dashboard")
templates = Jinja2Templates(directory="templates")


def load_data() -> dict[str, Any]:
    if not DATA_FILE.exists():
        save_data(dict(DEFAULT_DATA))
    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="data.json must be an object")
    if not isinstance(data.get("products"), list):
        data["products"] = list(DEFAULT_DATA["products"])
    data.setdefault("chat_groups", DEFAULT_DATA["chat_groups"])
    return data


def save_data(data: dict[str, Any]) -> None:
    _atomic_save_json(DATA_FILE, data)


def parse_groups(raw: str) -> str | list[str]:
    cleaned = raw.strip()
    if not cleaned or cleaned.lower() == "all":
        return "all"
    groups = [item.strip() for item in cleaned.replace("\n", ",").split(",") if item.strip()]
    return groups or "all"


def groups_text(groups: str | list[str]) -> str:
    if groups == "all":
        return "all"
    if isinstance(groups, list):
        return "\n".join(str(group) for group in groups)
    return str(groups)


def validate_product(keyword: str, min_price: float, max_price: float) -> dict[str, Any]:
    keyword = keyword.strip()
    if not 1 <= len(keyword) <= 80:
        raise HTTPException(status_code=400, detail="Keyword must be 1-80 characters")
    if min_price < 0 or max_price < min_price:
        raise HTTPException(status_code=400, detail="Invalid price range")
    return {"keyword": keyword, "min_price": float(min_price), "max_price": float(max_price)}


def parse_findings(limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    if not LOGS_FILE.exists():
        return []
    rows: list[dict[str, Any]] = []
    with LOGS_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw_links = item.get("links") if isinstance(item.get("links"), list) else []
            links = [link for link in raw_links if isinstance(link, dict)]
            best_link = next((link for link in links if link.get("price_ok")), links[0] if links else {})
            raw_coupons = item.get("coupons", [])
            coupons = raw_coupons if isinstance(raw_coupons, list) else []
            rows.append(
                {
                    "ts": item.get("ts", ""),
                    "chat": item.get("chat", ""),
                    "coupons": ", ".join(str(coupon) for coupon in coupons),
                    "url": best_link.get("url", ""),
                    "status": best_link.get("status", ""),
                    "price": best_link.get("price"),
                    "price_ok": bool(best_link.get("price_ok")),
                    "reason": best_link.get("reason", ""),
                    "text": item.get("text", "")[:240],
                }
            )
    return rows[-limit:][::-1]


def redirect_home() -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


@app.get("/")
async def index(request: Request):
    data = load_data()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "products": data["products"],
            "chat_groups": groups_text(data["chat_groups"]),
            "findings": parse_findings(),
        },
    )


@app.get("/api/state")
async def api_state():
    data = load_data()
    return JSONResponse({"settings": data, "findings": parse_findings()})


@app.get("/api/findings")
async def api_findings():
    return JSONResponse({"findings": parse_findings()})


@app.post("/products")
async def add_product(
    keyword: str = Form(...),
    min_price: float = Form(...),
    max_price: float = Form(...),
):
    data = load_data()
    products = data["products"]
    products.append(validate_product(keyword, min_price, max_price))
    save_data(data)
    return redirect_home()


@app.post("/products/{index}/edit")
async def edit_product(
    index: int,
    keyword: str = Form(...),
    min_price: float = Form(...),
    max_price: float = Form(...),
):
    data = load_data()
    products = data["products"]
    if index < 0 or index >= len(products):
        raise HTTPException(status_code=404, detail="Product not found")
    products[index] = validate_product(keyword, min_price, max_price)
    save_data(data)
    return redirect_home()


@app.post("/products/{index}/delete")
async def delete_product(index: int):
    data = load_data()
    products = data["products"]
    if index < 0 or index >= len(products):
        raise HTTPException(status_code=404, detail="Product not found")
    products.pop(index)
    if not products:
        products.append(dict(DEFAULT_DATA["products"][0]))
    save_data(data)
    return redirect_home()


@app.post("/chat-groups")
async def update_chat_groups(chat_groups: str = Form(...)):
    data = load_data()
    data["chat_groups"] = parse_groups(chat_groups)
    save_data(data)
    return redirect_home()
