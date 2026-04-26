from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Iterable, Protocol


LINK_RE = re.compile(r"https?://[^\s<>)\"']+", re.IGNORECASE)
PRICE_RE = re.compile(r"R\$\s*([0-9,.]+)", re.IGNORECASE)
COUPON_RE = re.compile(
    r"(?:cupom|coupon|codigo|c[oó]digo|use)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_\-]{3,24})",
    re.IGNORECASE,
)


class ProductLike(Protocol):
    keyword: str
    min_price: float
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


def extract_links(text: str) -> list[str]:
    return [match.group(0).rstrip(".,;]") for match in LINK_RE.finditer(text or "")]


def extract_coupons(text: str) -> list[str]:
    seen: set[str] = set()
    coupons: list[str] = []
    for match in COUPON_RE.finditer(text or ""):
        coupon = match.group(1).upper()
        if coupon not in seen:
            seen.add(coupon)
            coupons.append(coupon)
    return coupons


def parse_price(text: str) -> float | None:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1)
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw.replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def extract_prices(text: str) -> list[float]:
    prices: list[float] = []
    for match in PRICE_RE.finditer(text or ""):
        raw = match.group(1)
        normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw.replace(",", ".")
        try:
            prices.append(float(normalized))
        except ValueError:
            continue
    return prices


def check_price_range(text: str, products: Iterable[ProductLike]) -> tuple[float | None, bool]:
    prices = extract_prices(text)
    first_price = prices[0] if prices else None
    lowered = (text or "").lower()
    for product in products:
        keyword = product.keyword.lower()
        if keyword and keyword not in lowered:
            continue
        for price in prices:
            if product.min_price <= price <= product.max_price:
                return price, True
    return first_price, False


async def verify_link(
    session,
    url: str,
    products: Iterable[ProductLike],
    timeout_seconds: int = 12,
) -> VerificationResult:
    import aiohttp
    from bs4 import BeautifulSoup

    try:
        async with session.get(url, timeout=timeout_seconds, allow_redirects=True) as response:
            content_type = response.headers.get("content-type", "")
            body = await response.text(errors="ignore")
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
    matched_keywords = [product.keyword for product in product_list if product.keyword.lower() in lower_text]
    price, price_ok = check_price_range(page_text, product_list)
    status_ok = 200 <= response.status < 400
    ok = status_ok and bool(matched_keywords or title or page_text)
    reason = "matched keywords: " + ", ".join(matched_keywords) if matched_keywords else "reachable"
    if price is not None:
        reason = f"{reason}; price R$ {price:.2f}"
    if price is not None and not price_ok:
        reason = f"{reason}; outside configured ranges"
    if not status_ok:
        reason = f"HTTP {response.status}"

    return VerificationResult(
        url=url,
        ok=ok,
        status=response.status,
        title=title,
        reason=reason,
        price=price,
        price_ok=price_ok,
    )


async def verify_links(urls: Iterable[str], products: Iterable[ProductLike]) -> list[VerificationResult]:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "HaumeaCupons/0.1 (+https://telegram.org)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [verify_link(session, url, products) for url in urls]
        return await asyncio.gather(*tasks) if tasks else []
