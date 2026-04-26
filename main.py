from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_FILE, Settings, load_settings
from storage import add_finding, init_findings_db, migrate_alerts_jsonl
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


def chat_allowed(chat_groups: str | list[str], chat_title: str, chat_username: str | None, chat_id: int | str) -> bool:
    if chat_groups == "all":
        return True

    normalized_groups = {str(group).strip().lower().lstrip("@") for group in chat_groups if str(group).strip()}
    candidates = {
        str(chat_id).lower(),
        chat_title.lower(),
    }
    if chat_username:
        candidates.add(chat_username.lower().lstrip("@"))
    return bool(normalized_groups.intersection(candidates))


def finding_keyword(text: str, result: VerificationResult, settings: Settings) -> str:
    if result.product_keyword:
        return result.product_keyword

    searchable = f"{text} {result.title} {result.reason}".lower()
    for product in settings.products:
        if product.keyword.lower() not in searchable:
            continue
        if result.price is None or product.min_price <= result.price <= product.max_price:
            return product.keyword
    return ""


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


class SettingsStore:
    def __init__(
        self,
        settings: Settings,
        data_file: Path = DATA_FILE,
        interval_seconds: int = 30,
    ) -> None:
        self.settings = settings
        self.data_file = data_file
        self.interval_seconds = interval_seconds
        self._mtime = self._current_mtime()

    def _current_mtime(self) -> float | None:
        try:
            return self.data_file.stat().st_mtime
        except FileNotFoundError:
            return None

    def reload_if_changed(self) -> bool:
        current_mtime = self._current_mtime()
        if current_mtime == self._mtime:
            return False

        next_settings = load_settings()
        self.settings = next_settings
        self._mtime = current_mtime
        logging.info("Configuração recarregada de %s", self.data_file)
        return True

    async def watch(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                self.reload_if_changed()
            except Exception:
                logging.exception("Falha ao recarregar configuração")


def build_handler(settings_store: Settings | SettingsStore):
    store = settings_store if isinstance(settings_store, SettingsStore) else SettingsStore(settings_store)

    async def handler(event) -> None:
        settings = store.settings
        text = event.raw_text or ""
        links = extract_links(text)
        coupons = extract_coupons(text)
        if not links and not coupons:
            return
        if not has_keyword(text, settings.product_keywords):
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(event.chat_id)
        chat_username = getattr(chat, "username", None)
        if not chat_allowed(settings.chat_groups, chat_title, chat_username, event.chat_id):
            return

        logging.info("Coupon candidate from %s with %d links", chat_title, len(links))

        results = await verify_links(links, settings.products)
        if not any(result.price_ok for result in results):
            logging.info("Skipping candidate outside configured price ranges")
            return

        alert = format_alert(chat_title, text, coupons, results)
        await event.client.send_message(settings.main_user_id, alert, link_preview=False)
        timestamp = datetime.now(timezone.utc).isoformat()
        findings_db = settings.logs_dir / "findings.sqlite3"
        for result in results:
            if not result.price_ok:
                continue
            add_finding(
                timestamp=timestamp,
                product_keyword=finding_keyword(text, result, settings),
                url=result.url,
                price_found=result.price,
                price_ok=result.price_ok,
                source_group=chat_title,
                db_path=findings_db,
            )

    return handler


async def run() -> None:
    from telethon import TelegramClient, events

    settings = load_settings()
    setup_logging(settings.logs_dir)
    settings.logs_dir.mkdir(exist_ok=True)
    findings_db = settings.logs_dir / "findings.sqlite3"
    init_findings_db(findings_db)
    migrate_alerts_jsonl(settings.logs_dir / "alerts.jsonl", findings_db)

    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    settings_store = SettingsStore(settings)
    reload_task = asyncio.create_task(settings_store.watch())
    handler = build_handler(settings_store)
    client.add_event_handler(handler, events.NewMessage())

    logging.info("Starting Telethon client. Login may ask for code on first run.")
    await client.start(phone=settings.phone)
    group_count = "all" if settings.chat_groups == "all" else str(len(settings.chat_groups))
    logging.info("Listening to %s chat/group entries", group_count)
    try:
        await client.run_until_disconnected()
    finally:
        reload_task.cancel()
        with suppress(asyncio.CancelledError):
            await reload_task


if __name__ == "__main__":
    asyncio.run(run())
