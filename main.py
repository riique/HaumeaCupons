from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from config import Settings, load_settings
from verifier import VerificationResult, extract_coupons, extract_links, verify_links


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / "haumea_cupons.log", encoding="utf-8"),
        ],
    )


def has_keyword(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def format_alert(
    chat_title: str,
    message_text: str,
    coupons: list[str],
    results: list[VerificationResult],
) -> str:
    lines = [
        "HaumeaCupons alert",
        f"Origem: {chat_title}",
    ]
    if coupons:
        lines.append("Cupons: " + ", ".join(coupons))
    if results:
        lines.append("Links:")
        for result in results:
            status = result.status if result.status is not None else "erro"
            price = f" R$ {result.price:.2f}" if result.price is not None else ""
            price_flag = " preço ok" if result.price_ok else " preço fora da faixa"
            title = f" - {result.title}" if result.title else ""
            lines.append(f"- {result.url} [{status}]{price}{price_flag} {result.reason}{title}")
    lines.extend(["", message_text[:1200]])
    return "\n".join(lines)


def append_jsonl(logs_dir: Path, payload: dict) -> None:
    logs_dir.mkdir(exist_ok=True)
    with (logs_dir / "alerts.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def build_handler(settings: Settings):
    async def handler(event) -> None:
        text = event.raw_text or ""
        links = extract_links(text)
        coupons = extract_coupons(text)
        if not links and not coupons:
            return
        if not has_keyword(text, settings.product_keywords):
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(event.chat_id)
        logging.info("Coupon candidate from %s with %d links", chat_title, len(links))

        results = await verify_links(links, settings.products)
        if not any(result.price_ok for result in results):
            logging.info("Skipping candidate outside configured price ranges")
            return

        alert = format_alert(chat_title, text, coupons, results)
        await event.client.send_message(settings.main_user_id, alert, link_preview=False)
        append_jsonl(
            settings.logs_dir,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "chat": chat_title,
                "coupons": coupons,
                "links": [asdict(result) for result in results],
                "text": text,
            },
        )

    return handler


async def run() -> None:
    from telethon import TelegramClient, events

    settings = load_settings()
    setup_logging(settings.logs_dir)
    settings.logs_dir.mkdir(exist_ok=True)

    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    handler = build_handler(settings)
    chats = None if settings.chat_groups == "all" else settings.chat_groups
    client.add_event_handler(handler, events.NewMessage(chats=chats))

    logging.info("Starting Telethon client. Login may ask for code on first run.")
    await client.start(phone=settings.phone)
    group_count = "all" if settings.chat_groups == "all" else str(len(settings.chat_groups))
    logging.info("Listening to %s chat/group entries", group_count)
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(run())
