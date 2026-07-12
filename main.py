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
from firebase_setup import save_finding as firestore_save_finding
from hermes_notify import notify_hermes_finding
from offers import OfferCandidate, classify_offer_message
from storage import (
    add_finding,
    add_message_event,
    enqueue_sync_outbox,
    finding_exists,
    get_pending_sync_outbox,
    init_findings_db,
    mark_sync_outbox_done,
    mark_sync_outbox_failed,
    migrate_alerts_jsonl,
)
from verifier import (
    VerificationResult,
    extract_coupons,
    extract_links,
    match_price_range,
    match_product_term,
    price_in_range,
    product_allows_merchant,
    term_in_text,
    verify_links,
)


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
    return any(term_in_text(keyword, text) for keyword in keywords)


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

    searchable = f"{text} {result.title} {result.reason}"
    for product in settings.products:
        matched_term = match_product_term(searchable, product)
        if not matched_term:
            continue
        if result.price is None or price_in_range(result.price, product):
            return product.primary_keyword or matched_term
    return ""


def matched_rule_for_message(text: str, offer: OfferCandidate, settings: Settings) -> tuple[Any | None, str]:
    searchable = f"{text}\n{offer.product_title}\n{offer.merchant}"
    for product in settings.products:
        if not product_allows_merchant(product, offer.merchant):
            continue
        matched_term = match_product_term(searchable, product)
        if matched_term:
            return product, matched_term
    return None, ""


def _rule_name(product: Any | None, fallback: str = "") -> str:
    if product is None:
        return fallback
    return str(getattr(product, "primary_keyword", "") or fallback)


def _rule_id(product: Any | None) -> str:
    if product is None:
        return ""
    return str(getattr(product, "rule_id", "") or getattr(product, "id", "") or getattr(product, "primary_keyword", ""))


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


def _split_env_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _product_notify_enabled(product: Any) -> bool:
    if getattr(product, "notify_hermes_explicit", False):
        return bool(getattr(product, "notify_hermes", False))

    notify_email = str(getattr(product, "notify_email", "") or "").strip().lower()
    if not notify_email:
        return False
    return notify_email in _split_env_set("HAUMEA_NOTIFY_EMAIL_ALLOWLIST")


def _price_text(price: float | None) -> str:
    if price is None:
        return ""
    return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_hermes_payload(
    *,
    message_hash: str,
    product: str,
    price: float | None,
    url: str,
    source: str,
    timestamp: str,
    coupons: list[str],
    links: list[str],
) -> dict[str, Any]:
    return {
        "id": message_hash,
        "product": product,
        "price": price,
        "price_text": _price_text(price),
        "url": url,
        "source": source,
        "timestamp": timestamp,
        "coupon_summary": ", ".join(coupons) if coupons else "sem cupom",
        "coupons": coupons,
        "links": links,
    }


_firestore_sync_semaphore = asyncio.Semaphore(2)


async def sync_finding_to_firestore_async(finding_payload: dict[str, Any], *, user_id: str, request_id: str) -> None:
    timeout_seconds = float(os.getenv("FIRESTORE_SYNC_TIMEOUT_SECONDS", "8") or "8")
    async with _firestore_sync_semaphore:
        doc_id = await asyncio.wait_for(
            asyncio.to_thread(firestore_save_finding, finding_payload, user_id=user_id),
            timeout=max(1.0, min(timeout_seconds, 30.0)),
        )
        if doc_id is None:
            raise RuntimeError("Firestore indisponivel")


async def process_firestore_outbox_once(db_path: Path) -> int:
    processed = 0
    for item in get_pending_sync_outbox(target="firestore_finding", limit=20, db_path=db_path):
        try:
            await sync_finding_to_firestore_async(
                item["payload"],
                user_id=str(item["payload"].get("user_id") or "bot"),
                request_id=str(item.get("dedupe_key") or item["id"]),
            )
        except Exception as exc:
            mark_sync_outbox_failed(item_id=item["id"], error=str(exc), db_path=db_path)
            logging.warning("Firestore sync pendente falhou; ficara na outbox (%s)", exc)
        else:
            mark_sync_outbox_done(item_id=item["id"], db_path=db_path)
            processed += 1
    return processed


async def firestore_outbox_worker(settings_store: "SettingsStore") -> None:
    while True:
        await asyncio.sleep(5)
        if os.getenv("FIRESTORE_SYNC_FINDINGS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            continue
        try:
            await process_firestore_outbox_once(settings_store.settings.logs_dir / "findings.sqlite3")
        except Exception:
            logging.exception("Falha no worker de outbox Firestore")


def _detection_acceptance(settings: Settings, keyword_hit: bool, offer: OfferCandidate) -> tuple[bool, str]:
    mode = getattr(settings, "detection_mode", "hybrid")
    if mode == "keywords":
        return keyword_hit, "accepted_by_keyword" if keyword_hit else "missing_keyword"
    if mode == "signals":
        return offer.accepted, offer.reason
    if keyword_hit:
        return True, "accepted_by_keyword"
    return offer.accepted, offer.reason


def _raw_message_for_storage(settings: Settings, text: str) -> str:
    return text if getattr(settings, "store_raw_messages", False) else ""


def _record_message_event(
    *,
    settings: Settings,
    db_path: Path,
    source_group: str,
    source_chat_id: str,
    source_message_id: str,
    message_hash: str,
    decision: str,
    reason: str,
    offer: OfferCandidate,
    links_count: int,
    coupons_count: int,
    text: str,
) -> None:
    if not getattr(settings, "message_audit_enabled", True):
        return
    preview = " ".join(text.split())[:240] if getattr(settings, "store_raw_messages", False) else ""
    try:
        add_message_event(
            source_group=source_group,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            decision=decision,
            reason=reason,
            message_type=offer.message_type,
            product_title=offer.product_title,
            merchant=offer.merchant,
            price_found=offer.price,
            confidence=offer.confidence,
            links_count=links_count,
            coupons_count=coupons_count,
            raw_preview=preview,
            db_path=db_path,
        )
    except Exception:
        logging.exception("Falha ao registrar auditoria de mensagem")


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
    logging.info("Envio Telegram desativado; alerta nao enviado")
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
        self.dedupe_cache = DedupeCache(getattr(settings, "dedupe_ttl_seconds", 1800))
        self._mtime = self._current_mtime()
        self._fingerprint = self._settings_fingerprint(settings)

    def _current_mtime(self) -> float | None:
        try:
            return self.data_file.stat().st_mtime
        except FileNotFoundError:
            return None

    @staticmethod
    def _settings_fingerprint(settings: Settings) -> tuple[Any, ...]:
        products = tuple(
            (
                tuple(product.keywords),
                float(product.max_price),
                getattr(product, "id", ""),
                getattr(product, "name", ""),
                getattr(product, "min_price", None),
                tuple(getattr(product, "exclude_terms", None) or []),
                tuple(getattr(product, "merchants", None) or []),
                getattr(product, "category", ""),
                bool(getattr(product, "auto_approve", True)),
                bool(getattr(product, "notify_hermes", False)),
                str(getattr(product, "notify_email", "")),
            )
            for product in settings.products
        )
        chat_groups = settings.chat_groups if isinstance(settings.chat_groups, str) else tuple(settings.chat_groups)
        return (
            chat_groups,
            products,
            tuple(settings.keywords),
            getattr(settings, "detection_mode", "hybrid"),
            getattr(settings, "min_offer_confidence", 0.62),
            getattr(settings, "message_audit_enabled", True),
            getattr(settings, "store_raw_messages", False),
            getattr(settings, "dedupe_ttl_seconds", 1800),
            getattr(settings, "signal_only_max_price", 0.0),
        )

    def reload_if_changed(self) -> bool:
        current_mtime = self._current_mtime()
        next_settings = load_settings()
        next_fingerprint = self._settings_fingerprint(next_settings)
        if current_mtime == self._mtime and next_fingerprint == self._fingerprint:
            return False

        self.settings = next_settings
        self._mtime = current_mtime
        self._fingerprint = next_fingerprint
        self.dedupe_cache.ttl_seconds = max(60, int(getattr(next_settings, "dedupe_ttl_seconds", 1800)))
        logging.info("Configuração recarregada de %s/Firestore", self.data_file)
        return True

    async def watch(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await asyncio.to_thread(self.reload_if_changed)
            except Exception:
                logging.exception("Falha ao recarregar configuração")


def build_handler(settings_store: Settings | SettingsStore):
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
        offer = classify_offer_message(
            text,
            links,
            coupons,
            min_confidence=getattr(settings, "min_offer_confidence", 0.62),
        )
        keyword_hit = has_keyword(text, settings.product_keywords)
        matched_rule, matched_term = matched_rule_for_message(text, offer, settings)
        accepted_by_detection, detection_reason = _detection_acceptance(settings, keyword_hit, offer)
        if not accepted_by_detection:
            _record_message_event(
                settings=settings,
                db_path=findings_db,
                source_group=chat_title,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                message_hash=message_hash,
                decision="rejected",
                reason=detection_reason,
                offer=offer,
                links_count=len(links),
                coupons_count=len(coupons),
                text=text,
            )
            return

        store_review_findings = os.getenv("STORE_REVIEW_FINDINGS", "").strip().lower() in {"1", "true", "yes", "on"}
        signal_only_auto_enabled = float(getattr(settings, "signal_only_max_price", 0.0) or 0.0) > 0
        if not keyword_hit and matched_rule is None and not store_review_findings and not signal_only_auto_enabled:
            _record_message_event(
                settings=settings,
                db_path=findings_db,
                source_group=chat_title,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                message_hash=message_hash,
                decision="ignored_signal_without_rule",
                reason="signal_without_matching_rule_disabled",
                offer=offer,
                links_count=len(links),
                coupons_count=len(coupons),
                text=text,
            )
            return

        if store.dedupe_cache.seen(message_hash) or finding_exists(
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            db_path=findings_db,
        ):
            _record_message_event(
                settings=settings,
                db_path=findings_db,
                source_group=chat_title,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                message_hash=message_hash,
                decision="duplicate",
                reason="message_already_seen",
                offer=offer,
                links_count=len(links),
                coupons_count=len(coupons),
                text=text,
            )
            logging.info("Mensagem duplicada ignorada de %s", chat_title)
            return
        store.dedupe_cache.mark(message_hash)

        _record_message_event(
            settings=settings,
            db_path=findings_db,
            source_group=chat_title,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            decision="candidate",
            reason=detection_reason,
            offer=offer,
            links_count=len(links),
            coupons_count=len(coupons),
            text=text,
        )

        logging.info(
            "→ Candidato de %s | %d link(s) | %d cupom(ns) | tipo=%s | conf=%.2f | produto: %.80s",
            chat_title,
            len(links),
            len(coupons),
            offer.message_type,
            offer.confidence,
            (text if getattr(settings, "store_raw_messages", False) else offer.product_title or offer.message_type).replace('\n', ' '),
        )

        # Check price in the message text itself (most reliable in deal groups)
        msg_price, msg_price_ok, msg_kw = match_price_range(text, settings.products, merchant=offer.merchant)

        results = await verify_links(links, settings.products)
        page_ok_result = next((result for result in results if result.ok and result.price_ok), None)
        page_price_ok = page_ok_result is not None
        detection_mode = getattr(settings, "detection_mode", "hybrid")
        signal_detection_can_price = detection_mode == "signals" or (
            detection_mode == "hybrid" and (not keyword_hit or not settings.products)
        )
        signal_offer_has_price = signal_detection_can_price and offer.accepted and offer.price is not None

        if page_ok_result is not None and matched_rule is None:
            for product in settings.products:
                if page_ok_result.product_keyword in product.keywords:
                    matched_rule = product
                    matched_term = page_ok_result.product_keyword
                    break

        decision = "approved"
        decision_reason = detection_reason
        price_source = ""
        reason_codes = [detection_reason]
        accepted_price: float | None = None
        accepted_kw = ""

        if msg_price_ok:
            accepted_price = msg_price
            accepted_kw = _rule_name(matched_rule, msg_kw or matched_term)
            price_source = "message_text_rule"
            reason_codes.append("price_matched_message_rule")
        elif page_ok_result is not None:
            accepted_price = page_ok_result.price
            accepted_kw = _rule_name(matched_rule, finding_keyword(text, page_ok_result, settings))
            price_source = "page_rule"
            reason_codes.append("price_matched_page_rule")
        elif signal_offer_has_price:
            accepted_price = offer.price
            accepted_kw = offer.product_title or offer.message_type
            global_ceiling = float(getattr(settings, "signal_only_max_price", 0.0) or 0.0)
            if global_ceiling > 0 and offer.price is not None and offer.price <= global_ceiling:
                price_source = "signal_global_ceiling"
                decision_reason = "accepted_by_signal_global_ceiling"
                reason_codes.append("signal_price_under_global_ceiling")
            else:
                decision = "review"
                price_source = "signal_extracted_price"
                decision_reason = "review_signal_without_matching_rule"
                reason_codes.append("missing_matching_price_rule")
        else:
            prices_found = [r.price for r in results if r.price is not None]
            if offer.price is not None:
                prices_found.insert(0, offer.price)
            elif msg_price is not None:
                prices_found.insert(0, msg_price)
            _record_message_event(
                settings=settings,
                db_path=findings_db,
                source_group=chat_title,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                message_hash=message_hash,
                decision="rejected_price",
                reason="price_outside_rules_or_missing",
                offer=offer,
                links_count=len(links),
                coupons_count=len(coupons),
                text=text,
            )
            logging.info("  ✗ Preço fora do limite (encontrados: %s)", prices_found or "nenhum")
            return

        if matched_rule is not None and not bool(getattr(matched_rule, "auto_approve", True)):
            decision = "review"
            decision_reason = "review_rule_requires_manual_approval"
            reason_codes.append("rule_auto_approve_disabled")

        # Use message/signal price if page didn't find one
        if accepted_price is not None and not page_price_ok:
            if decision == "approved":
                logging.info("  ✓ Preço R$ %.2f aceito via %s (%s)", accepted_price, price_source, accepted_kw or offer.message_type)
            else:
                logging.info("  ? Oferta enviada para revisão | preço R$ %.2f via %s (%s)", accepted_price, price_source, accepted_kw or offer.message_type)
            results = [
                VerificationResult(
                    url=r.url, ok=r.ok, status=r.status, title=r.title,
                    reason=r.reason, price=accepted_price, price_ok=(decision == "approved"), product_keyword=accepted_kw,
                )
                if r.price is None else r
                for r in results
            ]

        _record_message_event(
            settings=settings,
            db_path=findings_db,
            source_group=chat_title,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            decision=decision,
            reason=decision_reason,
            offer=offer,
            links_count=len(links),
            coupons_count=len(coupons),
            text=text,
        )

        if decision != "approved" and not store_review_findings:
            logging.info("  Revisão registrada apenas na auditoria; finding não salvo (%s)", decision_reason)
            return

        if decision == "approved" and matched_rule is None and price_source != "signal_global_ceiling":
            logging.warning("  Aprovação sem regra/teto global bloqueada por segurança")
            return

        # Save ONE finding per message (all links + coupons together)
        timestamp = datetime.now(timezone.utc).isoformat()
        best_price = accepted_price
        best_kw = accepted_kw
        all_links = [r.url for r in results] or links
        if not best_kw:
            for result in results:
                kw = finding_keyword(text, result, settings)
                if kw:
                    best_kw = kw
                    break
        if not best_kw:
            best_kw = offer.product_title or offer.message_type
        if best_price is None:
            for result in results:
                if result.price is not None:
                    best_price = result.price
                    break
        finding_payload = {
            "timestamp": timestamp,
            "product_keyword": best_kw,
            "url": all_links[0] if all_links else "",
            "price_found": best_price,
            "price_ok": decision == "approved",
            "source_group": chat_title,
            "coupons": coupons,
            "links": all_links,
            "source_chat_id": source_chat_id,
            "source_message_id": source_message_id,
            "raw_message": _raw_message_for_storage(settings, text),
            "product_title": offer.product_title,
            "merchant": offer.merchant,
            "message_type": offer.message_type,
            "match_reason": decision_reason,
            "confidence": offer.confidence,
            "message_hash": message_hash,
            "url_hash": _hash_value("|".join(sorted(all_links)) or "|".join(coupons) or text[:200]),
            "decision": decision,
            "matched_rule_id": _rule_id(matched_rule),
            "rule_name": _rule_name(matched_rule),
            "detected_title": offer.product_title,
            "price_source": price_source,
            "reason_codes": reason_codes,
            "score_breakdown": offer.score_breakdown,
        }
        add_finding(
            timestamp=timestamp,
            product_keyword=best_kw,
            url=all_links[0] if all_links else "",
            price_found=best_price,
            price_ok=decision == "approved",
            source_group=chat_title,
            coupons=coupons,
            links=all_links,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            message_hash=message_hash,
            url_hash=_hash_value("|".join(sorted(all_links)) or "|".join(coupons) or text[:200]),
            product_title=offer.product_title,
            merchant=offer.merchant,
            message_type=offer.message_type,
            match_reason=decision_reason,
            confidence=offer.confidence,
            raw_message=_raw_message_for_storage(settings, text),
            decision=decision,
            matched_rule_id=_rule_id(matched_rule),
            rule_name=_rule_name(matched_rule),
            detected_title=offer.product_title,
            price_source=price_source,
            reason_codes=reason_codes,
            score_breakdown=offer.score_breakdown,
            db_path=findings_db,
        )
        if os.getenv("FIRESTORE_SYNC_FINDINGS", "").strip().lower() in {"1", "true", "yes", "on"}:
            enqueue_sync_outbox(
                target="firestore_finding",
                payload={**finding_payload, "user_id": "bot"},
                dedupe_key=message_hash,
                db_path=findings_db,
            )

        if decision == "approved" and best_kw and settings.products:
            for product in settings.products:
                if (best_kw in product.keywords or best_kw == product.primary_keyword) and _product_notify_enabled(product):
                    hermes_payload = build_hermes_payload(
                        message_hash=message_hash,
                        product=best_kw,
                        price=best_price,
                        url=all_links[0] if all_links else "",
                        source=chat_title,
                        timestamp=timestamp,
                        coupons=coupons,
                        links=all_links,
                    )
                    try:
                        await notify_hermes_finding(hermes_payload, request_id=message_hash)
                    except Exception:
                        logging.exception("Falha inesperada ao notificar Hermes; finding ja foi salvo")
                    break

        logging.info("  Finding salvo no banco (%s)", decision)

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
    firestore_sync_task = asyncio.create_task(firestore_outbox_worker(settings_store))
    handler = build_handler(settings_store)
    client.add_event_handler(handler, events.NewMessage(incoming=True))

    if settings.bot_token:
        logging.info("Iniciando como Bot (token)")
        await client.start(bot_token=settings.bot_token)
    else:
        logging.info("Iniciando como conta de usuário (telefone)")
        await client.start(phone=settings.phone)

    group_str = "TODOS os grupos" if settings.chat_groups == "all" else f"{len(settings.chat_groups)} grupos"
    kw_count = len(settings.keywords)
    prod_count = len(settings.products)
    logging.info("✓ Bot iniciado — monitorando %s | %d produto(s) | %d palavra(s)-chave", group_str, prod_count, kw_count)
    logging.info("Envio Telegram direto desativado; alertas Hermes usam webhook quando habilitados por produto")
    for p in settings.products:
        logging.info("  • [%.2f] %s", p.max_price, ", ".join(p.keywords))
    try:
        await client.run_until_disconnected()
    finally:
        reload_task.cancel()
        firestore_sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await reload_task
        with suppress(asyncio.CancelledError):
            await firestore_sync_task


if __name__ == "__main__":
    asyncio.run(run())
