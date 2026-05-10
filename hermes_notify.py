from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Mapping

import aiohttp

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HermesWebhookSettings:
    url: str
    secret: str
    timeout_seconds: float = 5.0

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.secret)


def load_hermes_webhook_settings(env: Mapping[str, str] | None = None) -> HermesWebhookSettings:
    source = env if env is not None else os.environ
    timeout_raw = str(source.get("HAUMEA_HERMES_WEBHOOK_TIMEOUT_SECONDS", "5")).strip()
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 5.0
    return HermesWebhookSettings(
        url=str(source.get("HAUMEA_HERMES_WEBHOOK_URL", "")).strip(),
        secret=str(source.get("HAUMEA_HERMES_WEBHOOK_SECRET", "")).strip(),
        timeout_seconds=max(1.0, min(timeout_seconds, 15.0)),
    )


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_hmac_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def notify_hermes_finding(
    payload: Mapping[str, Any],
    *,
    request_id: str,
    settings: HermesWebhookSettings | None = None,
    attempts: int = 2,
) -> bool:
    cfg = settings or load_hermes_webhook_settings()
    if not cfg.enabled:
        logger.info("Hermes webhook desabilitado; defina URL e secret para enviar alerta")
        return False

    body = canonical_json_bytes(payload)
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": build_hmac_signature(body, cfg.secret),
        "X-Request-ID": request_id,
    }
    timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
    last_status = None

    for attempt in range(1, max(1, attempts) + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(cfg.url, data=body, headers=headers) as response:
                    last_status = response.status
                    if 200 <= response.status < 300:
                        logger.info("Alerta entregue ao Hermes via webhook")
                        return True
                    logger.warning("Hermes webhook respondeu status %s", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.warning("Falha ao enviar alerta ao Hermes via webhook")
        except Exception:
            logger.exception("Erro inesperado no envio do alerta ao Hermes")
            return False

        if attempt < max(1, attempts):
            await asyncio.sleep(0.5)

    if last_status is not None:
        logger.warning("Alerta Hermes nao entregue apos retries; ultimo status %s", last_status)
    return False
