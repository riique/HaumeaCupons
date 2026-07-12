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
from firebase_setup import (
    clear_findings as firestore_clear_findings,
    delete_finding as firestore_delete_finding,
    delete_product as firestore_delete_product,
    get_chat_groups as firestore_get_chat_groups,
    list_findings as firestore_list_findings,
    list_products as firestore_list_products,
    save_chat_groups as firestore_save_chat_groups,
    save_finding as firestore_save_finding,
    save_product as firestore_save_product,
    verify_id_token,
)
from storage import DEFAULT_DB_FILE, LEGACY_ALERTS_FILE, get_findings, get_message_event_stats, init_findings_db, migrate_alerts_jsonl


FRONTEND_DIST = Path("frontend/dist")
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FINDINGS_DB_FILE = DEFAULT_DB_FILE


class ProductPayload(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=20)
    max_price: float = Field(ge=0)
    name: str = ""
    min_price: float | None = Field(default=None, ge=0)
    exclude_terms: list[str] = Field(default_factory=list, max_length=50)
    merchants: list[str] = Field(default_factory=list, max_length=20)
    category: str = ""
    auto_approve: bool = True

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in value if k.strip()]
        if not cleaned:
            raise ValueError("Informe ao menos uma palavra-chave")
        if any(len(keyword) > 80 for keyword in cleaned):
            raise ValueError("Cada palavra-chave deve ter no maximo 80 caracteres")
        return list(dict.fromkeys(cleaned))  # dedupe, preserve order

    @field_validator("exclude_terms", "merchants")
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in value if k.strip()]
        return list(dict.fromkeys(cleaned))


class ProductResponse(ProductPayload):
    id: int | str
    active: bool = True
    created_by: str = ""
    created_at: str = ""


class ChatGroupsPayload(BaseModel):
    chat_groups: str | list[str] = "all"

    @field_validator("chat_groups")
    @classmethod
    def normalize_chat_groups(cls, value: str | list[str]) -> str | list[str]:
        return parse_groups(value)


class ChatGroupsResponse(BaseModel):
    chat_groups: str | list[str]


class FindingResponse(BaseModel):
    id: int | str
    timestamp: str
    product_keyword: str
    url: str
    price_found: float | None
    price_ok: bool
    source_group: str
    coupons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source_chat_id: str = ""
    source_message_id: str = ""
    product_title: str = ""
    merchant: str = ""
    message_type: str = ""
    match_reason: str = ""
    confidence: float | None = None
    raw_message: str = ""
    message_hash: str = ""
    url_hash: str = ""
    decision: str = "approved"
    matched_rule_id: str = ""
    rule_name: str = ""
    detected_title: str = ""
    price_source: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    schema_version: int = 1
    user_id: str = "bot"


class StateResponse(BaseModel):
    products: list[ProductResponse]
    chat_groups: str | list[str]
    findings: list[FindingResponse]


class FindingsPage(BaseModel):
    findings: list[FindingResponse]
    limit: int
    offset: int


class FindingPayload(BaseModel):
    timestamp: str | None = None
    product_keyword: str = ""
    url: str = ""
    price_found: float | None = None
    price_ok: bool = False
    source_group: str = ""
    coupons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source_chat_id: str = ""
    source_message_id: str = ""
    product_title: str = ""
    merchant: str = ""
    message_type: str = ""
    match_reason: str = ""
    confidence: float | None = None
    raw_message: str = ""
    message_hash: str = ""
    url_hash: str = ""
    decision: str = "approved"
    matched_rule_id: str = ""
    rule_name: str = ""
    detected_title: str = ""
    price_source: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    schema_version: int = 2
    user_id: str = "bot"


class MessageEventStatsResponse(BaseModel):
    source_group: str
    decision: str
    message_type: str
    total: int
    avg_confidence: float | None = None
    with_price: int
    with_links: int
    with_coupons: int
    first_seen: str
    last_seen: str


class TokenPayload(BaseModel):
    token: str


class AuthUserResponse(BaseModel):
    uid: str
    email: str | None = None
    display_name: str | None = None


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

    if provided_key and secrets.compare_digest(provided_key, expected_key):
        return await call_next(request)

    if provided_key and verify_id_token(provided_key):
        return await call_next(request)

    if not provided_key:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Chave do dashboard obrigatoria"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Token Firebase ou chave do dashboard inválida"},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, Any]:
    sqlite_ok = False
    try:
        init_findings_db(FINDINGS_DB_FILE)
        with closing(sqlite3.connect(FINDINGS_DB_FILE)) as conn:
            conn.execute("SELECT 1").fetchone()
        sqlite_ok = True
    except Exception:
        sqlite_ok = False
    return {
        "ok": sqlite_ok,
        "sqlite": "ok" if sqlite_ok else "error",
        "frontend_dist": FRONTEND_INDEX.exists(),
    }


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


def _product_id(product: dict[str, Any], fallback: int) -> int | str:
    raw_id = product.get("id")
    if isinstance(raw_id, int) and raw_id >= 0:
        return raw_id
    if isinstance(raw_id, str) and raw_id.isdigit():
        return int(raw_id)
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    return fallback


def _next_product_id(products: list[dict[str, Any]]) -> int:
    if not products:
        return 0
    numeric_ids = [
        product_id
        for index, product in enumerate(products)
        if isinstance((product_id := _product_id(product, index)), int)
    ]
    return (max(numeric_ids) + 1) if numeric_ids else len(products)


def _product_response(product: dict[str, Any], fallback: int) -> ProductResponse:
    # Migrate legacy single-keyword format
    normalized = dict(product)
    if "keyword" in normalized and "keywords" not in normalized:
        normalized["keywords"] = [normalized.pop("keyword")]
    if "matchTerms" in normalized and "keywords" not in normalized:
        normalized["keywords"] = normalized["matchTerms"]
    if "match_terms" in normalized and "keywords" not in normalized:
        normalized["keywords"] = normalized["match_terms"]
    if "maxPrice" in normalized and "max_price" not in normalized:
        normalized["max_price"] = normalized["maxPrice"]
    if "minPrice" in normalized and "min_price" not in normalized:
        normalized["min_price"] = normalized["minPrice"]
    if "excludeTerms" in normalized and "exclude_terms" not in normalized:
        normalized["exclude_terms"] = normalized["excludeTerms"]
    if "autoApprove" in normalized and "auto_approve" not in normalized:
        normalized["auto_approve"] = normalized["autoApprove"]
    payload = ProductPayload.model_validate(normalized)
    return ProductResponse(
        id=_product_id(product, fallback),
        name=payload.name,
        keywords=payload.keywords,
        max_price=payload.max_price,
        min_price=payload.min_price,
        exclude_terms=payload.exclude_terms,
        merchants=payload.merchants,
        category=payload.category,
        auto_approve=payload.auto_approve,
        active=bool(product.get("active", True)),
        created_by=str(product.get("created_by", product.get("createdBy", "")) or ""),
        created_at=str(product.get("created_at", product.get("createdAt", "")) or ""),
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
                "name": response.name,
                "keywords": response.keywords,
                "max_price": response.max_price,
                "min_price": response.min_price,
                "exclude_terms": response.exclude_terms,
                "merchants": response.merchants,
                "category": response.category,
                "auto_approve": response.auto_approve,
            }
        )

    if not normalized:
        return list(DEFAULT_DATA["products"]), True
    return normalized, normalized != raw_products


def _product_index(products: list[dict[str, Any]], product_id: int | str) -> int:
    for index, product in enumerate(products):
        if str(_product_id(product, index)) == str(product_id):
            return index
    raise HTTPException(status_code=404, detail="Produto não encontrado")


def _settings_response(data: dict[str, Any], findings_limit: int = 200) -> StateResponse:
    firestore_products = firestore_list_products()
    firestore_findings = firestore_list_findings(findings_limit, 0)
    firestore_groups = firestore_get_chat_groups()
    return StateResponse(
        products=[
            _product_response(product, index)
            for index, product in enumerate(firestore_products if firestore_products is not None else data.get("products", []))
            if isinstance(product, dict)
        ],
        chat_groups=parse_groups(firestore_groups if firestore_groups is not None else data.get("chat_groups", "all")),
        findings=[
            FindingResponse.model_validate(item)
            for item in (firestore_findings if firestore_findings is not None else get_findings(findings_limit, 0, FINDINGS_DB_FILE))
        ],
    )


@app.get("/api/state", response_model=StateResponse)
async def api_state(limit: int = Query(200, ge=1, le=500)) -> StateResponse:
    return _settings_response(load_data(), limit)


@app.get("/api/findings", response_model=FindingsPage)
async def api_findings(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FindingsPage:
    firestore_findings = firestore_list_findings(limit, offset)
    return FindingsPage(
        findings=[
            FindingResponse.model_validate(item)
            for item in (firestore_findings if firestore_findings is not None else get_findings(limit, offset, FINDINGS_DB_FILE))
        ],
        limit=limit,
        offset=offset,
    )


@app.get("/api/message-stats", response_model=list[MessageEventStatsResponse])
async def api_message_stats(limit: int = Query(50, ge=1, le=200)) -> list[MessageEventStatsResponse]:
    return [MessageEventStatsResponse.model_validate(item) for item in get_message_event_stats(limit, FINDINGS_DB_FILE)]


@app.get("/api/metrics")
async def api_metrics() -> dict[str, Any]:
    findings = get_findings(500, 0, FINDINGS_DB_FILE)
    decisions: dict[str, int] = {}
    for finding in findings:
        decision = str(finding.get("decision") or "approved")
        decisions[decision] = decisions.get(decision, 0) + 1
    return {
        "findings_window": len(findings),
        "decisions": decisions,
        "message_event_stats": get_message_event_stats(20, FINDINGS_DB_FILE),
    }


@app.get("/api/products", response_model=list[ProductResponse])
async def api_products() -> list[ProductResponse]:
    firestore_products = firestore_list_products()
    data = load_data()
    products = firestore_products if firestore_products is not None else data.get("products", [])
    return [
        _product_response(product, index)
        for index, product in enumerate(products)
        if isinstance(product, dict)
    ]


@app.post("/api/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductPayload, request: Request) -> ProductResponse:
    data = load_data()
    firestore_products = firestore_list_products()
    products = [product for product in (firestore_products if firestore_products is not None else data.get("products", [])) if isinstance(product, dict)]
    product = {
        "id": _next_product_id(products),
        "name": payload.name,
        "keywords": payload.keywords,
        "max_price": payload.max_price,
        "min_price": payload.min_price,
        "exclude_terms": payload.exclude_terms,
        "merchants": payload.merchants,
        "category": payload.category,
        "auto_approve": payload.auto_approve,
    }
    firestore_product = firestore_save_product(product, created_by=_request_user_id(request))
    if firestore_product is not None:
        return _product_response(firestore_product, len(products))
    products.append(product)
    data["products"] = products
    save_data(data)
    return _product_response(product, len(products) - 1)


@app.put("/api/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, payload: ProductPayload, request: Request) -> ProductResponse:
    data = load_data()
    firestore_products = firestore_list_products()
    products = [product for product in (firestore_products if firestore_products is not None else data.get("products", [])) if isinstance(product, dict)]
    index = _product_index(products, product_id)
    product = {
        "id": int(product_id) if product_id.isdigit() else product_id,
        "name": payload.name,
        "keywords": payload.keywords,
        "max_price": payload.max_price,
        "min_price": payload.min_price,
        "exclude_terms": payload.exclude_terms,
        "merchants": payload.merchants,
        "category": payload.category,
        "auto_approve": payload.auto_approve,
    }
    firestore_product = firestore_save_product(product, created_by=_request_user_id(request))
    if firestore_product is not None:
        return _product_response(firestore_product, index)
    products[index] = product
    data["products"] = products
    save_data(data)
    return _product_response(product, index)


@app.delete("/api/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: str) -> Response:
    if firestore_delete_product(product_id):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    data = load_data()
    products = [product for product in data.get("products", []) if isinstance(product, dict)]
    index = _product_index(products, product_id)
    products.pop(index)
    data["products"] = products
    save_data(data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/api/chat-groups", response_model=ChatGroupsResponse)
async def update_chat_groups(payload: ChatGroupsPayload) -> ChatGroupsResponse:
    if firestore_save_chat_groups(payload.chat_groups):
        return ChatGroupsResponse(chat_groups=payload.chat_groups)
    data = load_data()
    data["chat_groups"] = payload.chat_groups
    save_data(data)
    return ChatGroupsResponse(chat_groups=payload.chat_groups)

@app.delete("/api/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_finding(finding_id: str) -> Response:
    if firestore_delete_finding(finding_id):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not finding_id.isdigit():
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    with closing(sqlite3.connect(FINDINGS_DB_FILE)) as conn:
        cursor = conn.execute("DELETE FROM findings WHERE id = ?", (int(finding_id),))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alerta não encontrado")
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/findings", status_code=status.HTTP_204_NO_CONTENT)
async def clear_findings() -> Response:
    if firestore_clear_findings():
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    with closing(sqlite3.connect(FINDINGS_DB_FILE)) as conn:
        conn.execute("DELETE FROM findings")
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/findings", response_model=FindingResponse, status_code=status.HTTP_201_CREATED)
async def create_finding(payload: FindingPayload) -> FindingResponse:
    finding = payload.model_dump()
    doc_id = firestore_save_finding(finding, user_id=payload.user_id)
    if doc_id:
        return FindingResponse.model_validate({**finding, "id": doc_id, "timestamp": payload.timestamp or ""})

    from storage import add_finding

    row_id = add_finding(
        timestamp=payload.timestamp,
        product_keyword=payload.product_keyword,
        url=payload.url,
        price_found=payload.price_found,
        price_ok=payload.price_ok,
        source_group=payload.source_group,
        coupons=payload.coupons,
        links=payload.links,
        source_chat_id=payload.source_chat_id,
        source_message_id=payload.source_message_id,
        message_hash=payload.message_hash,
        url_hash=payload.url_hash,
        product_title=payload.product_title,
        merchant=payload.merchant,
        message_type=payload.message_type,
        match_reason=payload.match_reason,
        confidence=payload.confidence,
        raw_message=payload.raw_message,
        decision=payload.decision,
        matched_rule_id=payload.matched_rule_id,
        rule_name=payload.rule_name,
        detected_title=payload.detected_title,
        price_source=payload.price_source,
        reason_codes=payload.reason_codes,
        score_breakdown=payload.score_breakdown,
        db_path=FINDINGS_DB_FILE,
    )
    saved = get_findings(1, 0, FINDINGS_DB_FILE)[0]
    saved["id"] = row_id
    return FindingResponse.model_validate(saved)


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _request_user_id(request: Request) -> str:
    decoded = verify_id_token(_bearer_token(request))
    if decoded:
        return str(decoded.get("uid") or "bot")
    return "bot"


@app.post("/api/auth/verify-token", response_model=AuthUserResponse)
async def verify_token(payload: TokenPayload) -> AuthUserResponse:
    decoded = verify_id_token(payload.token)
    if not decoded:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Firebase inválido")
    return AuthUserResponse(
        uid=str(decoded.get("uid") or ""),
        email=decoded.get("email"),
        display_name=decoded.get("name"),
    )


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
