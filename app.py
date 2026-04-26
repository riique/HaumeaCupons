from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from config import DATA_FILE, DEFAULT_DATA, _atomic_save_json
from storage import DEFAULT_DB_FILE, LEGACY_ALERTS_FILE, get_findings, init_findings_db, migrate_alerts_jsonl


FRONTEND_DIST = Path("frontend/dist")
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FINDINGS_DB_FILE = DEFAULT_DB_FILE


class ProductPayload(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    min_price: float = Field(ge=0)
    max_price: float = Field(ge=0)

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        keyword = value.strip()
        if not keyword:
            raise ValueError("Informe a palavra-chave")
        return keyword

    @model_validator(mode="after")
    def validate_range(self) -> "ProductPayload":
        if self.max_price < self.min_price:
            raise ValueError("O preço máximo deve ser maior ou igual ao mínimo")
        return self


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
    payload = ProductPayload.model_validate(product)
    return ProductResponse(
        id=_product_id(product, fallback),
        keyword=payload.keyword,
        min_price=payload.min_price,
        max_price=payload.max_price,
    )


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
        "keyword": payload.keyword,
        "min_price": payload.min_price,
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
        "keyword": payload.keyword,
        "min_price": payload.min_price,
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
