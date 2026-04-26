from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Iterable, Protocol
from urllib.parse import urljoin, urlsplit


LINK_RE = re.compile(r"https?://[^\s<>)\"']+", re.IGNORECASE)
PRICE_RE = re.compile(
    r"(?:R\$\s*|BRL\s*|\bPOR\s*:?\s*)(?P<prefix>[0-9][0-9.,\s]*)"
    r"|(?P<suffix>[0-9][0-9.,\s]*)\s*(?:reais|R\$)",
    re.IGNORECASE,
)
COUPON_RE = re.compile(
    r"(?:cupom|coupon|codigo|c[oó]digo|use)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_\-]{3,24})",
    re.IGNORECASE,
)
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 1_000_000
MAX_CONCURRENT_VERIFICATIONS = 5


class ProductLike(Protocol):
    keywords: list[str]
    max_price: float


@dataclass(frozen=True)
class VerificationResult:
    url: str
    ok: bool
    status: int | None
    title: str
    reason: str
    price: float | None = None
    price_ok: bool = False
    product_keyword: str = ""


def extract_links(text: str) -> list[str]:
    seen: set[str] = set()
    links: list[str] = []
    for match in LINK_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;]")
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
    return links


def extract_coupons(text: str) -> list[str]:
    seen: set[str] = set()
    coupons: list[str] = []
    for match in COUPON_RE.finditer(text or ""):
        coupon = match.group(1).upper()
        if coupon not in seen:
            seen.add(coupon)
            coupons.append(coupon)
    return coupons


def _normalize_price(raw: str) -> float | None:
    value = re.sub(r"\s+", "", raw)
    if not value:
        return None

    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        normalized = value.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in value:
        left, right = value.rsplit(",", 1)
        normalized = left.replace(".", "").replace(",", "")
        normalized = f"{normalized}.{right}" if len(right) <= 2 else f"{normalized}{right}"
    elif "." in value:
        parts = value.split(".")
        if len(parts[-1]) <= 2:
            normalized = "".join(parts[:-1]) + "." + parts[-1] if len(parts) > 2 else value
        else:
            normalized = "".join(parts)
    else:
        normalized = value

    try:
        return float(normalized)
    except ValueError:
        return None


def parse_price(text: str) -> float | None:
    prices = extract_prices(text)
    return prices[0] if prices else None


def extract_prices(text: str) -> list[float]:
    prices: list[float] = []
    for match in PRICE_RE.finditer(text or ""):
        raw = match.group("prefix") or match.group("suffix") or ""
        price = _normalize_price(raw)
        if price is not None:
            prices.append(price)
    return prices


def match_price_range(text: str, products: Iterable[ProductLike]) -> tuple[float | None, bool, str]:
    prices = extract_prices(text)
    first_price = prices[0] if prices else None
    lowered = (text or "").lower()
    for product in products:
        # Match if ANY keyword is found in the text
        matched_kw = next((kw for kw in product.keywords if kw.lower() in lowered), None)
        if not matched_kw:
            continue
        for price in prices:
            if price <= product.max_price:
                return price, True, matched_kw
    return first_price, False, ""


def check_price_range(text: str, products: Iterable[ProductLike]) -> tuple[float | None, bool]:
    price, price_ok, _ = match_price_range(text, products)
    return price, price_ok


def _is_blocked_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


async def validate_public_url(url: str) -> tuple[bool, str]:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "blocked URL scheme"
    if not parsed.hostname:
        return False, "missing URL host"

    host = parsed.hostname.strip().lower()
    if host == "localhost" or host.endswith(".localhost"):
        return False, "blocked local host"
    if _is_blocked_ip(host):
        return False, "blocked private IP"

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError:
        return False, "invalid URL port"
    try:
        loop = asyncio.get_running_loop()
        addresses = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return False, f"DNS resolution failed: {exc}"

    for address in addresses:
        sockaddr = address[4]
        resolved_ip = sockaddr[0]
        if _is_blocked_ip(resolved_ip):
            return False, "blocked private IP"

    return True, ""


class ResponseTooLargeError(RuntimeError):
    pass


async def _read_limited_text(response, max_bytes: int = MAX_RESPONSE_BYTES) -> str:
    body = await response.content.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ResponseTooLargeError("response body exceeds 1MB")
    charset = response.charset or "utf-8"
    return body.decode(charset, errors="ignore")


async def verify_link(
    session,
    url: str,
    products: Iterable[ProductLike],
    timeout_seconds: int = 12,
) -> VerificationResult:
    import aiohttp
    from bs4 import BeautifulSoup

    current_url = url
    response_status: int | None = None
    content_type = ""
    body = ""

    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            allowed, reason = await validate_public_url(current_url)
            if not allowed:
                return VerificationResult(url=url, ok=False, status=None, title="", reason=reason)

            async with session.get(current_url, timeout=timeout_seconds, allow_redirects=False) as response:
                response_status = response.status
                if response.status in {301, 302, 303, 307, 308}:
                    if redirect_count >= MAX_REDIRECTS:
                        return VerificationResult(
                            url=url,
                            ok=False,
                            status=response.status,
                            title="",
                            reason="too many redirects",
                        )
                    location = response.headers.get("location")
                    if not location:
                        return VerificationResult(
                            url=url,
                            ok=False,
                            status=response.status,
                            title="",
                            reason="redirect without location",
                        )
                    current_url = urljoin(str(response.url), location)
                    continue

                content_type = response.headers.get("content-type", "")
                body = await _read_limited_text(response)
                break
        else:
            return VerificationResult(url=url, ok=False, status=None, title="", reason="too many redirects")
    except ResponseTooLargeError as exc:
        return VerificationResult(url=url, ok=False, status=response_status, title="", reason=str(exc))
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return VerificationResult(url=url, ok=False, status=None, title="", reason=str(exc))

    title = ""
    page_text = body[:120_000]
    if "html" in content_type.lower() or "<html" in body[:500].lower():
        soup = BeautifulSoup(body, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        page_text = soup.get_text(" ", strip=True)[:120_000]

    product_list = list(products)
    lower_text = page_text.lower()
    matched_keywords = [kw for product in product_list for kw in product.keywords if kw.lower() in lower_text]
    price, price_ok, product_keyword = match_price_range(page_text, product_list)
    status_ok = response_status is not None and 200 <= response_status < 400
    ok = status_ok and bool(matched_keywords or title or page_text)
    reason = "matched keywords: " + ", ".join(matched_keywords) if matched_keywords else "reachable"
    if price is not None:
        reason = f"{reason}; price R$ {price:.2f}"
    if price is not None and not price_ok:
        reason = f"{reason}; outside configured ranges"
    if not status_ok:
        reason = f"HTTP {response_status}"

    return VerificationResult(
        url=url,
        ok=ok,
        status=response_status,
        title=title,
        reason=reason,
        price=price,
        price_ok=price_ok,
        product_keyword=product_keyword,
    )


async def verify_links(urls: Iterable[str], products: Iterable[ProductLike]) -> list[VerificationResult]:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "HaumeaCupons/0.1 (+https://telegram.org)"}
    deduped_urls = list(dict.fromkeys(urls))
    product_list = list(products)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_VERIFICATIONS)

    async def bounded_verify(session, url: str) -> VerificationResult:
        async with semaphore:
            return await verify_link(session, url, product_list)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [bounded_verify(session, url) for url in deduped_urls]
        return await asyncio.gather(*tasks) if tasks else []
