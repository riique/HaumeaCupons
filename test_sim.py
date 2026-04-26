from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as dashboard_app
from config import Product, Settings, load_settings
from main import build_handler
from storage import add_finding, get_findings
from verifier import (
    VerificationResult,
    check_price_range,
    extract_coupons,
    extract_links,
    parse_price,
    validate_public_url,
)


@dataclass
class DummyChat:
    title: str = "Dummy Login Test Group"


class DummyClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int | str, str, bool]] = []

    async def send_message(self, user_id: int, text: str, link_preview: bool = False) -> None:
        self.sent_messages.append((user_id, text, link_preview))


class DummyEvent:
    def __init__(self, text: str) -> None:
        self.id = 99
        self.out = False
        self.raw_text = text
        self.chat_id = -100123
        self.client = DummyClient()

    async def get_chat(self) -> DummyChat:
        return DummyChat()


def test_extract_links_and_coupons() -> None:
    text = "Notebook em promo https://example.com/oferta. https://example.com/oferta Cupom: SAVE10"
    assert extract_links(text) == ["https://example.com/oferta"]
    assert extract_coupons(text) == ["SAVE10"]


def test_parse_price_formats() -> None:
    assert parse_price("Notebook por R$ 1.234,56") == 1234.56
    assert parse_price("Oferta BRL 1999.90") == 1999.90
    assert parse_price("Preço 899,90 reais") == 899.90
    assert parse_price("Sem preço aqui") is None


def test_check_price_range() -> None:
    products = [Product(keywords=["notebook"], max_price=2000.0)]
    assert check_price_range("Notebook em oferta por R$ 1.500,00", products) == (1500.0, True)
    assert check_price_range("Notebook em oferta por R$ 2.500,00", products) == (2500.0, False)
    assert check_price_range("Smartphone em oferta por R$ 1.500,00", products) == (1500.0, False)


def test_load_settings_reads_env_and_bootstraps_data(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_ID", "123456")
    monkeypatch.setenv("API_HASH", "test_hash")
    monkeypatch.setenv("PHONE", "+5500000000000")
    monkeypatch.setenv("CHAT_GROUPS", "grupo-a,grupo-b")
    monkeypatch.setenv("PRODUCTS_KEYWORDS", "notebook,ssd")

    settings = load_settings()

    assert settings.api_id == 123456
    assert settings.api_hash == "test_hash"
    assert settings.phone == "+5500000000000"
    assert settings.chat_groups == ["grupo-a", "grupo-b"]
    assert settings.product_keywords == ["notebook", "ssd"]

    data = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert [product["keywords"] for product in data["products"]] == [["notebook"], ["ssd"]]
    assert data["chat_groups"] == ["grupo-a", "grupo-b"]


def test_ssrf_private_urls_are_blocked() -> None:
    async def run_case() -> None:
        localhost_allowed, localhost_reason = await validate_public_url("http://localhost:8000")
        private_allowed, private_reason = await validate_public_url("http://127.0.0.1:8000")
        lan_allowed, lan_reason = await validate_public_url("http://192.168.0.1")

        assert localhost_allowed is False
        assert "local" in localhost_reason
        assert private_allowed is False
        assert "private" in private_reason
        assert lan_allowed is False
        assert "private" in lan_reason

    asyncio.run(run_case())


def test_handler_saves_finding_without_sending_telegram_message() -> None:
    async def run_case() -> None:
        with TemporaryDirectory() as tmp:
            settings = Settings(
                api_id=1,
                api_hash="hash",
                phone="+5500000000000",
                chat_groups="all",
                products=[Product(keywords=["notebook"], max_price=5000.0)],
                keywords=["notebook"],
                logs_dir=Path(tmp),
            )
            event = DummyEvent("Notebook em promo https://example.com/oferta Cupom: SAVE10")
            expected = [
                VerificationResult(
                    url="https://example.com/oferta",
                    ok=True,
                    status=200,
                    title="Oferta Notebook",
                    reason="matched keywords: notebook",
                    price=999.0,
                    price_ok=True,
                    product_keyword="notebook",
                )
            ]

            with patch("main.verify_links", return_value=expected):
                await build_handler(settings)(event)

            assert event.client.sent_messages == []
            findings = get_findings(db_path=Path(tmp) / "findings.sqlite3")
            assert len(findings) == 1
            assert findings[0]["product_keyword"] == "notebook"
            assert findings[0]["source_group"] == "Dummy Login Test Group"

    asyncio.run(run_case())


def test_handler_does_not_alert_when_only_failed_page_has_price() -> None:
    async def run_case() -> None:
        with TemporaryDirectory() as tmp:
            settings = Settings(
                api_id=1,
                api_hash="hash",
                phone="+5500000000000",
                chat_groups="all",
                products=[Product(keywords=["notebook"], max_price=5000.0)],
                keywords=["notebook"],
                logs_dir=Path(tmp),
            )
            event = DummyEvent("Notebook em promo https://example.com/oferta Cupom: SAVE10")
            failed_page = [
                VerificationResult(
                    url="https://example.com/oferta",
                    ok=False,
                    status=500,
                    title="Erro Notebook",
                    reason="HTTP 500; price R$ 999.00",
                    price=999.0,
                    price_ok=True,
                    product_keyword="notebook",
                )
            ]

            with patch("main.verify_links", return_value=failed_page):
                await build_handler(settings)(event)

            assert event.client.sent_messages == []
            assert get_findings(db_path=Path(tmp) / "findings.sqlite3") == []

    asyncio.run(run_case())


def test_api_state_products_and_chat_groups(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    data_file = tmp_path / "data.json"
    findings_db = tmp_path / "findings.sqlite3"
    legacy_file = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(dashboard_app, "DATA_FILE", data_file)
    monkeypatch.setattr(dashboard_app, "FINDINGS_DB_FILE", findings_db)
    monkeypatch.setattr(dashboard_app, "LEGACY_ALERTS_FILE", legacy_file)
    dashboard_app.save_data(
            {
                "products": [{"keywords": ["iphone"], "max_price": 200.0}],
                "chat_groups": "all",
            }
    )
    add_finding(
        timestamp="2026-04-26T12:00:00+00:00",
        product_keyword="iphone",
        url="https://example.com/oferta",
        price_found=150.0,
        price_ok=True,
        source_group="Grupo Teste",
        db_path=findings_db,
    )

    with TestClient(dashboard_app.app) as client:
        state = client.get("/api/state").json()
        assert state["products"][0]["id"] == 0
        assert state["products"][0]["keywords"] == ["iphone"]
        assert state["chat_groups"] == "all"
        assert state["findings"][0]["source_group"] == "Grupo Teste"
        assert state["findings"][0]["links"] == []

        created = client.post(
            "/api/products",
            json={"keywords": ["notebook"], "max_price": 4000},
        )
        assert created.status_code == 201
        product_id = created.json()["id"]

        updated = client.put(
            f"/api/products/{product_id}",
            json={"keywords": ["notebook gamer", "notebook"], "max_price": 5000},
        )
        assert updated.status_code == 200
        assert updated.json()["keywords"] == ["notebook gamer", "notebook"]

        groups = client.put("/api/chat-groups", json={"chat_groups": "grupo-a\ngrupo-b"})
        assert groups.status_code == 200
        assert groups.json()["chat_groups"] == ["grupo-a", "grupo-b"]

        deleted = client.delete(f"/api/products/{product_id}")
        assert deleted.status_code == 204


def test_api_findings_pagination(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    data_file = tmp_path / "data.json"
    findings_db = tmp_path / "findings.sqlite3"
    monkeypatch.setattr(dashboard_app, "DATA_FILE", data_file)
    monkeypatch.setattr(dashboard_app, "FINDINGS_DB_FILE", findings_db)
    monkeypatch.setattr(dashboard_app, "LEGACY_ALERTS_FILE", tmp_path / "alerts.jsonl")
    dashboard_app.save_data(
            {
                "products": [{"keywords": ["iphone"], "max_price": 200.0}],
                "chat_groups": "all",
            }
    )
    for index in range(3):
        add_finding(
            timestamp=f"2026-04-26T12:0{index}:00+00:00",
            product_keyword="iphone",
            url=f"https://example.com/{index}",
            price_found=100.0 + index,
            price_ok=True,
            source_group="Grupo Teste",
            db_path=findings_db,
        )

    with TestClient(dashboard_app.app) as client:
        response = client.get("/api/findings?limit=2&offset=1")
        assert response.status_code == 200
        payload = response.json()
        assert payload["limit"] == 2
        assert payload["offset"] == 1
        assert [finding["url"] for finding in payload["findings"]] == [
            "https://example.com/1",
            "https://example.com/0",
        ]


def test_api_requires_dashboard_key_when_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_API_KEY", "secret-test-key")
    monkeypatch.setattr(dashboard_app, "DATA_FILE", tmp_path / "data.json")
    monkeypatch.setattr(dashboard_app, "FINDINGS_DB_FILE", tmp_path / "findings.sqlite3")
    monkeypatch.setattr(dashboard_app, "LEGACY_ALERTS_FILE", tmp_path / "alerts.jsonl")
    dashboard_app.save_data({"products": [{"keywords": ["iphone"], "max_price": 200.0}], "chat_groups": "all"})

    with TestClient(dashboard_app.app) as client:
        unauthorized = client.get("/api/state")
        assert unauthorized.status_code == 401

        authorized = client.get("/api/state", headers={"Authorization": "Bearer secret-test-key"})
        assert authorized.status_code == 200
