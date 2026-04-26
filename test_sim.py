from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from config import Product, Settings
from main import build_handler
from verifier import VerificationResult, extract_coupons, extract_links


@dataclass
class DummyChat:
    title: str = "Dummy Login Test Group"


class DummyClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str, bool]] = []

    async def send_message(self, user_id: int, text: str, link_preview: bool = False) -> None:
        self.sent_messages.append((user_id, text, link_preview))


class DummyEvent:
    def __init__(self, text: str) -> None:
        self.raw_text = text
        self.chat_id = -100123
        self.client = DummyClient()

    async def get_chat(self) -> DummyChat:
        return DummyChat()


def test_extract_links_and_coupons() -> None:
    text = "Notebook em promo https://example.com/oferta. Cupom: SAVE10"
    assert extract_links(text) == ["https://example.com/oferta"]
    assert extract_coupons(text) == ["SAVE10"]


def test_handler_simule_dummy_login_alert() -> None:
    async def run_case() -> None:
        with TemporaryDirectory() as tmp:
            settings = Settings(
                api_id=1,
                api_hash="hash",
                phone="+5500000000000",
                main_user_id=42,
                chat_groups=["dummy"],
                products=[Product(keyword="notebook", min_price=100.0, max_price=5000.0)],
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
                )
            ]

            with patch("main.verify_links", return_value=expected):
                await build_handler(settings)(event)

            assert len(event.client.sent_messages) == 1
            user_id, message, link_preview = event.client.sent_messages[0]
            assert user_id == 42
            assert link_preview is False
            assert "SAVE10" in message
            assert "Oferta Notebook" in message
            assert (Path(tmp) / "alerts.jsonl").exists()

    asyncio.run(run_case())
