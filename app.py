from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from collections import deque
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from config import DATA_FILE, DEFAULT_DATA, _atomic_save_json
from storage import DEFAULT_DB_FILE, LEGACY_ALERTS_FILE, get_findings, init_findings_db, migrate_alerts_jsonl


FRONTEND_DIST = Path("frontend/dist")
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FINDINGS_DB_FILE = DEFAULT_DB_FILE


class ProductPayload(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=20)
    max_price: float = Field(ge=0)

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in value if k.strip()]
        if not cleaned:
            raise ValueError("Informe ao menos uma palavra-chave")
        if any(len(keyword) > 80 for keyword in cleaned):
            raise ValueError("Cada palavra-chave deve ter no maximo 80 caracteres")
        return list(dict.fromkeys(cleaned))  # dedupe, preserve order


class ProductResponse(ProductPayload):
    id: int


class ChatGroupsPayload(BaseModel):
    chat_groups: str | list[str] = "all"

    @field_validator("chat_groups")
    @classmethod
    def normalize_chat_groups(cls, value: str | list[str]) -> str | list[str]:
        return parse_groups(value)


class ChatGroupsResponse(BaseModel):
    chat_groups: str | list[str]


class FindingResponse(BaseModel):
    id: int
    timestamp: str
    product_keyword: str
    url: str
    price_found: float | None
    price_ok: bool
    source_group: str
    coupons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class StateResponse(BaseModel):
    products: list[ProductResponse]
    chat_groups: str | list[str]
    findings: list[FindingResponse]


class FindingsPage(BaseModel):
    findings: list[FindingResponse]
    limit: int
    offset: int


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_findings_db(FINDINGS_DB_FILE)
    migrate_alerts_jsonl(LEGACY_ALERTS_FILE, FINDINGS_DB_FILE)
    yield


app = FastAPI(title="HaumeaCupons Dashboard", lifespan=lifespan)


@app.middleware("http")
async def require_dashboard_api_key(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    expected_key = os.getenv("DASHBOARD_API_KEY", "").strip()
    if not expected_key:
        return await call_next(request)

    provided_key = request.headers.get("x-dashboard-key", "").strip()
    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        provided_key = authorization[7:].strip()

    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Chave do dashboard obrigatoria"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)


def load_data() -> dict[str, Any]:
    if not DATA_FILE.exists():
        save_data({"products": list(DEFAULT_DATA["products"]), "chat_groups": DEFAULT_DATA["chat_groups"]})
    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="data.json deve conter um objeto")
    if not isinstance(data.get("products"), list):
        data["products"] = list(DEFAULT_DATA["products"])
    data["chat_groups"] = parse_groups(data.get("chat_groups", DEFAULT_DATA["chat_groups"]))
    products, changed = _normalize_products_for_storage(data.get("products", []))
    if changed:
        data["products"] = products
        save_data(data)
    return data


def save_data(data: dict[str, Any]) -> None:
    _atomic_save_json(DATA_FILE, data)


def parse_groups(raw: str | list[str] | Any) -> str | list[str]:
    if isinstance(raw, list):
        groups = [str(item).strip() for item in raw if str(item).strip()]
        if len(groups) == 1 and groups[0].lower() == "all":
            return "all"
        return groups or "all"

    cleaned = str(raw or "").strip()
    if not cleaned or cleaned.lower() == "all":
        return "all"
    groups = [item.strip() for item in cleaned.replace("\n", ",").split(",") if item.strip()]
    return groups or "all"


def _product_id(product: dict[str, Any], fallback: int) -> int:
    raw_id = product.get("id")
    if isinstance(raw_id, int) and raw_id >= 0:
        return raw_id
    if isinstance(raw_id, str) and raw_id.isdigit():
        return int(raw_id)
    return fallback


def _next_product_id(products: list[dict[str, Any]]) -> int:
    if not products:
        return 0
    return max(_product_id(product, index) for index, product in enumerate(products)) + 1


def _product_response(product: dict[str, Any], fallback: int) -> ProductResponse:
    # Migrate legacy single-keyword format
    normalized = dict(product)
    if "keyword" in normalized and "keywords" not in normalized:
        normalized["keywords"] = [normalized.pop("keyword")]
    if "min_price" in normalized:
        normalized.pop("min_price", None)
    payload = ProductPayload.model_validate(normalized)
    return ProductResponse(
        id=_product_id(product, fallback),
        keywords=payload.keywords,
        max_price=payload.max_price,
    )


def _normalize_products_for_storage(raw_products: Any) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(raw_products, list):
        return list(DEFAULT_DATA["products"]), True

    normalized: list[dict[str, Any]] = []
    for index, product in enumerate(raw_products):
        if not isinstance(product, dict):
            continue
        response = _product_response(product, index)
        normalized.append(
            {
                "id": response.id,
                "keywords": response.keywords,
                "max_price": response.max_price,
            }
        )

    if not normalized:
        return list(DEFAULT_DATA["products"]), True
    return normalized, normalized != raw_products


def _product_index(products: list[dict[str, Any]], product_id: int) -> int:
    for index, product in enumerate(products):
        if _product_id(product, index) == product_id:
            return index
    raise HTTPException(status_code=404, detail="Produto não encontrado")


def _settings_response(data: dict[str, Any], findings_limit: int = 200) -> StateResponse:
    return StateResponse(
        products=[
            _product_response(product, index)
            for index, product in enumerate(data.get("products", []))
            if isinstance(product, dict)
        ],
        chat_groups=parse_groups(data.get("chat_groups", "all")),
        findings=[FindingResponse.model_validate(item) for item in get_findings(findings_limit, 0, FINDINGS_DB_FILE)],
    )


@app.get("/api/state", response_model=StateResponse)
async def api_state(limit: int = Query(200, ge=1, le=500)) -> StateResponse:
    return _settings_response(load_data(), limit)


@app.get("/api/findings", response_model=FindingsPage)
async def api_findings(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FindingsPage:
    return FindingsPage(
        findings=[FindingResponse.model_validate(item) for item in get_findings(limit, offset, FINDINGS_DB_FILE)],
        limit=limit,
        offset=offset,
    )


@app.post("/api/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductPayload) -> ProductResponse:
    data = load_data()
    products = [product for product in data.get("products", []) if isinstance(product, dict)]
    product = {
        "id": _next_product_id(products),
        "keywords": payload.keywords,
        "max_price": payload.max_price,
    }
    products.append(product)
    data["products"] = products
    save_data(data)
    return _product_response(product, len(products) - 1)


@app.put("/api/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: int, payload: ProductPayload) -> ProductResponse:
    data = load_data()
    products = [product for product in data.get("products", []) if isinstance(product, dict)]
    index = _product_index(products, product_id)
    product = {
        "id": product_id,
        "keywords": payload.keywords,
        "max_price": payload.max_price,
    }
    products[index] = product
    data["products"] = products
    save_data(data)
    return _product_response(product, index)


@app.delete("/api/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int) -> Response:
    data = load_data()
    products = [product for product in data.get("products", []) if isinstance(product, dict)]
    index = _product_index(products, product_id)
    products.pop(index)
    data["products"] = products
    save_data(data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/api/chat-groups", response_model=ChatGroupsResponse)
async def update_chat_groups(payload: ChatGroupsPayload) -> ChatGroupsResponse:
    data = load_data()
    data["chat_groups"] = payload.chat_groups
    save_data(data)
    return ChatGroupsResponse(chat_groups=payload.chat_groups)

@app.delete("/api/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_finding(finding_id: int) -> Response:
    with closing(sqlite3.connect(FINDINGS_DB_FILE)) as conn:
        cursor = conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alerta não encontrado")
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/findings", status_code=status.HTTP_204_NO_CONTENT)
async def clear_findings() -> Response:
    with closing(sqlite3.connect(FINDINGS_DB_FILE)) as conn:
        conn.execute("DELETE FROM findings")
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _redact_log_line(line: str) -> str:
    redacted = re.sub(r"user_id=\d+", "user_id=REDACTED", line, flags=re.IGNORECASE)
    redacted = re.sub(r"MAIN_USER_ID=\d+", "MAIN_USER_ID=REDACTED", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"https?://\S+", "URL_REDACTED", redacted)
    return redacted


@app.get("/api/logs")
async def get_logs(lines: int = Query(200, ge=1, le=1000)) -> dict[str, list[str]]:
    log_file = Path("logs/haumea_cupons.log")
    if not log_file.exists():
        return {"logs": ["Nenhum log encontrado. O bot já foi iniciado?"]}
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            tail = deque(f, maxlen=lines)
            return {"logs": [_redact_log_line(line.rstrip("\n")) for line in tail]}
    except Exception as e:
        return {"logs": [f"Erro ao ler arquivo de log: {e}"]}


@app.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Build do frontend não encontrado")
    return FileResponse(FRONTEND_INDEX)


@app.get("/{path:path}", include_in_schema=False)
async def frontend_static(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API não encontrada")

    dist_root = FRONTEND_DIST.resolve()
    target = (FRONTEND_DIST / path).resolve()
    if target.is_file() and (target == dist_root or dist_root in target.parents):
        return FileResponse(target)
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    raise HTTPException(status_code=404, detail="Build do frontend não encontrado")
