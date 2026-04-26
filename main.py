from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATA_FILE, Settings, load_settings
from storage import add_finding, finding_exists, init_findings_db, migrate_alerts_jsonl
from telethon.errors import FloodWaitError
from verifier import VerificationResult, extract_coupons, extract_links, match_price_range, verify_links


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
        if not any(kw.lower() in searchable for kw in product.keywords):
            continue
        if result.price is None or result.price <= product.max_price:
            return product.primary_keyword
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


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _event_message_id(event: Any) -> str:
    message_id = getattr(event, "id", None)
    if message_id is None:
        message = getattr(event, "message", None)
        message_id = getattr(message, "id", None)
    return str(message_id or "")


def build_message_hash(chat_id: int | str, text: str, links: list[str], coupons: list[str]) -> str:
    normalized_text = " ".join((text or "").lower().split())
    normalized_links = "|".join(sorted(link.strip().lower() for link in links))
    normalized_coupons = "|".join(sorted(coupon.strip().upper() for coupon in coupons))
    return _hash_value(f"{chat_id}\n{normalized_text}\n{normalized_links}\n{normalized_coupons}")


class DedupeCache:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds))
        self._seen: dict[str, float] = {}

    def _prune(self, now: float) -> None:
        expired = [key for key, expires_at in self._seen.items() if expires_at <= now]
        for key in expired:
            self._seen.pop(key, None)

    def seen(self, key: str) -> bool:
        now = time.monotonic()
        self._prune(now)
        return key in self._seen

    def mark(self, key: str) -> None:
        now = time.monotonic()
        self._prune(now)
        self._seen[key] = now + self.ttl_seconds


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "too many requests" in message or "flood" in message or "429" in message


async def send_alert_with_retry(
    client: Any,
    target: Any,
    alert: str,
    *,
    rate_limit_retry_seconds: int = 60,
) -> bool:
    try:
        await client.send_message(target, alert, link_preview=False)
        logging.info("  Alerta enviado")
        return True
    except FloodWaitError as fw:
        wait_seconds = int(fw.seconds) + 1
        logging.warning("  Flood wait %ds; aguardando antes do retry", wait_seconds)
        await asyncio.sleep(wait_seconds)
    except Exception as exc:
        if not _is_rate_limit_error(exc):
            logging.error("  Falha ao enviar alerta: %s", exc)
            return False
        wait_seconds = max(1, int(rate_limit_retry_seconds))
        logging.warning("  Rate limit ao enviar alerta; aguardando %ds antes do retry: %s", wait_seconds, exc)
        await asyncio.sleep(wait_seconds)

    try:
        await client.send_message(target, alert, link_preview=False)
        logging.info("  Alerta enviado no retry")
        return True
    except Exception as exc:
        logging.error("  Falha no retry do alerta: %s", exc)
        return False


class AlertDispatcher:
    def __init__(self, client: Any, min_interval_seconds: float = 1.2, max_queue_size: int = 100) -> None:
        self.client = client
        self.min_interval_seconds = max(1.0, float(min_interval_seconds))
        self.queue: asyncio.Queue[tuple[Any, str]] = asyncio.Queue(maxsize=max(1, int(max_queue_size)))
        self._last_sent_by_target: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def enqueue(self, target: Any, alert: str) -> bool:
        try:
            self.queue.put_nowait((target, alert))
        except asyncio.QueueFull:
            logging.warning("Fila de alertas cheia; alerta descartado para proteger a conta")
            return False
        logging.info("  Alerta enfileirado (fila=%d)", self.queue.qsize())
        return True

    async def _wait_for_target_slot(self, target: Any) -> None:
        key = repr(target)
        last_sent = self._last_sent_by_target.get(key, 0.0)
        elapsed = time.monotonic() - last_sent
        wait_seconds = self.min_interval_seconds - elapsed
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

    async def _worker(self) -> None:
        while True:
            target, alert = await self.queue.get()
            try:
                await self._wait_for_target_slot(target)
                await send_alert_with_retry(self.client, target, alert)
                self._last_sent_by_target[repr(target)] = time.monotonic()
            finally:
                self.queue.task_done()


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
        self.alert_target: Any = settings.main_user_id
        self.dedupe_cache = DedupeCache(getattr(settings, "dedupe_ttl_seconds", 1800))
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


def build_handler(settings_store: Settings | SettingsStore, dispatcher: AlertDispatcher | None = None):
    store = settings_store if isinstance(settings_store, SettingsStore) else SettingsStore(settings_store)

    async def handler(event) -> None:
        if getattr(event, "out", False):
            return

        settings = store.settings
        text = event.raw_text or ""
        if not text:
            return

        links = extract_links(text)
        coupons = extract_coupons(text)

        # Need at least a link or coupon code to be actionable
        if not links and not coupons:
            return

        if not has_keyword(text, settings.product_keywords):
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(event.chat_id)
        chat_username = getattr(chat, "username", None)
        if not chat_allowed(settings.chat_groups, chat_title, chat_username, event.chat_id):
            logging.debug("Grupo %s não está na lista permitida", chat_title)
            return

        findings_db = settings.logs_dir / "findings.sqlite3"
        source_chat_id = str(event.chat_id)
        source_message_id = _event_message_id(event)
        message_hash = build_message_hash(source_chat_id, text, links, coupons)
        if store.dedupe_cache.seen(message_hash) or finding_exists(
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            db_path=findings_db,
        ):
            logging.info("Mensagem duplicada ignorada de %s", chat_title)
            return
        store.dedupe_cache.mark(message_hash)

        logging.info("→ Candidato de %s | %d link(s) | %d cupom(ns) | texto: %.80s", chat_title, len(links), len(coupons), text.replace('\n', ' '))

        # Check price in the message text itself (most reliable in deal groups)
        msg_price, msg_price_ok, msg_kw = match_price_range(text, settings.products)

        results = await verify_links(links, settings.products)
        page_price_ok = any(result.ok and result.price_ok for result in results)

        if not msg_price_ok and not page_price_ok:
            prices_found = [r.price for r in results if r.price is not None]
            if msg_price is not None:
                prices_found.insert(0, msg_price)
            logging.info("  ✗ Preço fora do limite (encontrados: %s)", prices_found or "nenhum")
            return

        # Use message price if page didn't find one
        if msg_price_ok and not page_price_ok:
            logging.info("  ✓ Preço R$ %.2f aceito via texto da mensagem (keyword: %s)", msg_price, msg_kw)
            results = [
                VerificationResult(
                    url=r.url, ok=r.ok, status=r.status, title=r.title,
                    reason=r.reason, price=msg_price, price_ok=True, product_keyword=msg_kw,
                )
                if r.price is None else r
                for r in results
            ]

        # Save ONE finding per message (all links + coupons together)
        timestamp = datetime.now(timezone.utc).isoformat()
        best_price = msg_price
        best_kw = msg_kw
        all_links = [r.url for r in results]
        if not best_kw:
            for result in results:
                kw = finding_keyword(text, result, settings)
                if kw:
                    best_kw = kw
                    break
        if best_price is None:
            for result in results:
                if result.price is not None:
                    best_price = result.price
                    break
        add_finding(
            timestamp=timestamp,
            product_keyword=best_kw,
            url=all_links[0] if all_links else "",
            price_found=best_price,
            price_ok=True,
            source_group=chat_title,
            coupons=coupons,
            links=all_links,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            url_hash=_hash_value("|".join(sorted(all_links)) or "|".join(coupons) or text[:200]),
            db_path=findings_db,
        )

        alert = format_alert(chat_title, text, coupons, results)
        if dispatcher:
            await dispatcher.enqueue(store.alert_target, alert)
        else:
            await send_alert_with_retry(event.client, store.alert_target, alert)

    return handler


async def run() -> None:
    from telethon import TelegramClient, events

    settings = load_settings()
    setup_logging(settings.logs_dir)
    if settings.chat_groups == "all" and not settings.bot_token and not settings.allow_all_chats:
        raise RuntimeError(
            "chat_groups=all esta bloqueado para conta de usuario. "
            "Configure grupos especificos ou defina ALLOW_ALL_CHATS=true assumindo o risco."
        )

    settings.logs_dir.mkdir(exist_ok=True)
    findings_db = settings.logs_dir / "findings.sqlite3"
    init_findings_db(findings_db)
    migrate_alerts_jsonl(settings.logs_dir / "alerts.jsonl", findings_db)

    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    settings_store = SettingsStore(settings)
    reload_task = asyncio.create_task(settings_store.watch())
    dispatcher = AlertDispatcher(
        client,
        min_interval_seconds=settings.alert_min_interval_seconds,
        max_queue_size=settings.max_alert_queue_size,
    )
    await dispatcher.start()
    handler = build_handler(settings_store, dispatcher)
    client.add_event_handler(handler, events.NewMessage(incoming=True))

    if settings.bot_token:
        logging.info("Iniciando como Bot (token)")
        await client.start(bot_token=settings.bot_token)
    else:
        logging.info("Iniciando como conta de usuário (telefone)")
        await client.start(phone=settings.phone)

    # Pre-resolve target user so send_message works later
    me = await client.get_me()
    if me.id == settings.main_user_id:
        settings_store.alert_target = "me"
        logging.info("Alertas → Mensagens Salvas (própria conta)")
    else:
        resolved = False
        # Try by numeric ID
        try:
            entity = await client.get_input_entity(settings.main_user_id)
            settings_store.alert_target = entity
            resolved = True
        except ValueError:
            pass
        # Try by username from env
        if not resolved:
            username = os.environ.get("MAIN_USERNAME", "").strip().lstrip("@")
            if username:
                try:
                    entity = await client.get_input_entity(username)
                    settings_store.alert_target = entity
                    resolved = True
                    logging.info("Alertas → @%s", username)
                except ValueError:
                    pass
        if not resolved:
            settings_store.alert_target = "me"
            logging.warning("Não resolveu MAIN_USER_ID=%d — alertas irão para Mensagens Salvas", settings.main_user_id)

    group_str = "TODOS os grupos" if settings.chat_groups == "all" else f"{len(settings.chat_groups)} grupos"
    kw_count = len(settings.keywords)
    prod_count = len(settings.products)
    logging.info("✓ Bot iniciado — monitorando %s | %d produto(s) | %d palavra(s)-chave", group_str, prod_count, kw_count)
    for p in settings.products:
        logging.info("  • [%.2f] %s", p.max_price, ", ".join(p.keywords))
    try:
        await client.run_until_disconnected()
    finally:
        reload_task.cancel()
        with suppress(asyncio.CancelledError):
            await reload_task
        await dispatcher.stop()


if __name__ == "__main__":
    asyncio.run(run())
