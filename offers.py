from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from verifier import normalize_price


CURRENCY_PRICE_RE = re.compile(
    r"(?:R\$\s*|BRL\s*)(?P<prefix>[0-9][0-9.,\s]{0,14}[0-9])"
    r"|(?P<suffix>[0-9][0-9.,\s]{0,14}[0-9])\s*(?:reais|R\$)",
    re.IGNORECASE,
)
LABELED_PRICE_RE = re.compile(
    r"\b(?:por|valor|pre[cç]o|saindo a|sai por)\s*:?\s*(?:R\$\s*)?"
    r"(?P<value>[0-9][0-9.,\s]{0,14}[0-9])",
    re.IGNORECASE,
)
DE_POR_RE = re.compile(
    r"\bde\s*(?:R\$\s*)?(?P<old>[0-9][0-9.,\s]{0,14}[0-9])"
    r".{0,35}?\bpor\s*(?:R\$\s*)?(?P<current>[0-9][0-9.,\s]{0,14}[0-9])",
    re.IGNORECASE | re.DOTALL,
)
LINK_CLEAN_RE = re.compile(r"https?://\S+", re.IGNORECASE)
BRACKET_PREFIX_RE = re.compile(r"^\s*\[[^\]]{2,40}\]\s*")
LEADING_MARKERS_RE = re.compile(r"^[\s\-:;|>•*#✅✔️🔥🚀👉➡️‼️😱🥉🥈🟠🛒💥💰💵🎟️🏷📲🌟👌]+")
PRICE_FRAGMENT_RE = re.compile(
    r"\b(?:de|por|valor|pre[cç]o|pix|avista|a vista|à vista|saindo a|sai por|acima de|compras acima|off)\b.*$",
    re.IGNORECASE,
)
PERCENT_DISCOUNT_PREFIX_RE = re.compile(
    r"^\s*(?:\d{1,3}\s*%\s*(?:off|desconto)|r\$\s*[0-9][0-9.,\s]*\s*off)\s*(?:[|:;\-]+)?\s*",
    re.IGNORECASE,
)

OFFER_TERMS = (
    "por r$",
    "por:",
    "por ",
    "pix",
    "frete gratis",
    "frete grátis",
    "a vista",
    "à vista",
    "saindo a",
    "sai por",
    "valor:",
    "preco",
    "preço",
    "baixou",
    "oferta",
    "promocao",
    "promoção",
)
COUPON_ONLY_TERMS = (
    "cupom shopee liberado",
    "cupom liberado",
    "cuponzao",
    "cuponzão",
    "cupons ativos",
    "resgate aqui",
    "ative rapido",
    "ative rápido",
    "off acima",
    "em compras acima",
)
DISCOUNT_CONTEXT_TERMS = (
    "off",
    "desconto",
    "cashback",
    "acima de",
    "compras acima",
    "cupom de",
    "cupom:",
)
GENERIC_TITLE_PREFIXES = (
    "olhe esse",
    "olha esse",
    "olha essa",
    "olhem esse",
    "corre que",
    "corree",
    "versao de",
    "versão de",
    "ainda ativo",
    "baixou mais",
    "um dos melhores",
    "exclusivo para membros",
    "e hoje",
    "é hoje",
    "ja ate anunciei",
    "já até anunciei",
)
GENERIC_TITLE_EXACT = {
    "olhe esse",
    "olha esse",
    "olha essa",
    "corre",
    "corree",
    "pasta",
    "oferta",
    "ofertas",
    "promocao",
    "promoção",
    "promo",
    "imperdivel",
    "imperdível",
    "barato",
    "baixou",
}
GENERIC_TITLE_TERMS = (
    "cupom",
    "cupons",
    "resgate",
    "ative",
    "grupo",
    "canal",
    "whatsapp",
    "telegram",
    "frete gratis",
    "frete grátis",
)
MARKETPLACE_HOSTS = {
    "shopee.com.br": "Shopee",
    "s.shopee.com.br": "Shopee",
    "shope.ee": "Shopee",
    "mercadolivre.com": "Mercado Livre",
    "mercadolivre.com.br": "Mercado Livre",
    "mercadolivre.com.co": "Mercado Livre",
    "meli.la": "Mercado Livre",
    "amazon.com.br": "Amazon",
    "amzn.to": "Amazon",
    "magazineluiza.com.br": "Magalu",
    "magalu.com": "Magalu",
    "kabum.com.br": "KaBuM",
    "terabyteshop.com.br": "Terabyte",
    "pichau.com.br": "Pichau",
    "aliexpress.com": "AliExpress",
    "s.click.aliexpress.com": "AliExpress",
}


@dataclass(frozen=True)
class PriceCandidate:
    value: float | None
    old_value: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class OfferCandidate:
    accepted: bool
    confidence: float
    message_type: str
    product_title: str = ""
    price: float | None = None
    old_price: float | None = None
    merchant: str = ""
    reason: str = ""
    signals: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)


def extract_hosts(links: list[str]) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    for link in links:
        host = (urlsplit(link).hostname or "").lower().removeprefix("www.")
        if not host or host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return hosts


def identify_merchant(hosts: list[str]) -> str:
    for host in hosts:
        if host in MARKETPLACE_HOSTS:
            return MARKETPLACE_HOSTS[host]
        for known_host, merchant in MARKETPLACE_HOSTS.items():
            if host.endswith("." + known_host):
                return merchant
    return ""


def _price_tokens(text: str) -> list[tuple[float, int, int]]:
    tokens: list[tuple[float, int, int]] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in (CURRENCY_PRICE_RE, LABELED_PRICE_RE):
        for match in pattern.finditer(text or ""):
            raw_value = match.groupdict().get("value") or match.groupdict().get("prefix") or match.groupdict().get("suffix") or ""
            value = normalize_price(raw_value)
            if value is None:
                continue
            span = (match.start(), match.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            tokens.append((value, match.start(), match.end()))
    tokens.sort(key=lambda item: item[1])
    return tokens


def _discount_context(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 24):start].lower()
    after = text[end:min(len(text), end + 28)].lower()
    context = f"{before} {after}"
    if "por" in before[-8:] and "off" not in after[:8]:
        return False
    return any(term in context for term in DISCOUNT_CONTEXT_TERMS)


def select_current_price(text: str) -> PriceCandidate:
    raw_text = text or ""
    pair = DE_POR_RE.search(raw_text)
    if pair:
        old_price = normalize_price(pair.group("old") or "")
        current_price = normalize_price(pair.group("current") or "")
        if current_price is not None:
            return PriceCandidate(current_price, old_price, "de_por")

    tokens = _price_tokens(raw_text)
    if not tokens:
        return PriceCandidate(None, None, "no_price")

    contextual: list[tuple[float, int, int, str]] = []
    fallback: list[tuple[float, int, int, str]] = []
    lowered = raw_text.lower()
    for value, start, end in tokens:
        before = lowered[max(0, start - 34):start]
        after = lowered[end:min(len(lowered), end + 24)]
        if _discount_context(lowered, start, end):
            continue
        reason = ""
        if any(term in before for term in ("por", "saindo", "valor", "preco", "preço", "pix", "vista", "boleto")):
            reason = "label_before"
        elif any(term in after for term in ("no pix", "pix", "a vista", "à vista", "frete")):
            reason = "label_after"
        if reason:
            contextual.append((value, start, end, reason))
        else:
            fallback.append((value, start, end, "single_price"))

    if contextual:
        value, _, _, reason = contextual[-1]
        return PriceCandidate(value, None, reason)
    if len(fallback) == 1:
        value, _, _, reason = fallback[0]
        return PriceCandidate(value, None, reason)
    if fallback:
        value, _, _, reason = fallback[-1]
        return PriceCandidate(value, None, reason)
    return PriceCandidate(tokens[0][0], None, "discount_only")


def _clean_line(line: str) -> str:
    line = LINK_CLEAN_RE.sub("", line or "")
    line = BRACKET_PREFIX_RE.sub("", line)
    line = LEADING_MARKERS_RE.sub("", line)
    line = PERCENT_DISCOUNT_PREFIX_RE.sub("", line)
    line = PRICE_FRAGMENT_RE.sub("", line)
    line = re.sub(r"\s+", " ", line).strip(" -:;|")
    return line.strip()


def _is_generic_title(line: str) -> bool:
    lowered = line.lower().strip()
    if not lowered or len(lowered) < 5:
        return True
    normalized = re.sub(r"\s+", " ", lowered.strip(" -:;|"))
    if normalized in GENERIC_TITLE_EXACT:
        return True
    if re.fullmatch(r"(?:\d{1,3}%\s*off|r\$\s*[0-9.,]+\s*off)", normalized):
        return True
    if any(lowered.startswith(prefix) for prefix in GENERIC_TITLE_PREFIXES):
        return True
    if len(line.split()) <= 3 and any(term in lowered for term in GENERIC_TITLE_TERMS):
        return True
    if any(term in lowered for term in COUPON_ONLY_TERMS):
        return True
    return False


def extract_product_title(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        lines = [text or ""]

    candidates: list[str] = []
    for line in lines[:8]:
        cleaned = _clean_line(line)
        if _is_generic_title(cleaned):
            continue
        if len(cleaned) > 140:
            cleaned = cleaned[:140].rstrip()
        candidates.append(cleaned)

    if candidates:
        return candidates[0]
    return ""


def _looks_like_coupon_only(text: str, title: str) -> bool:
    lowered = (text or "").lower()
    if any(term in lowered for term in COUPON_ONLY_TERMS) and not title:
        return True
    if title and title.lower() in {"cupom", "cupom shopee", "cupons ativos"}:
        return True
    return False


def classify_offer_message(
    text: str,
    links: list[str],
    coupons: list[str],
    *,
    min_confidence: float = 0.62,
) -> OfferCandidate:
    hosts = extract_hosts(links)
    merchant = identify_merchant(hosts)
    price = select_current_price(text)
    title = extract_product_title(text)
    lowered = (text or "").lower()
    signals: list[str] = []
    score_breakdown: dict[str, float] = {}
    score = 0.0

    def add_signal(name: str, weight: float) -> None:
        nonlocal score
        signals.append(name)
        score += weight
        score_breakdown[name] = round(score_breakdown.get(name, 0.0) + weight, 4)

    if links:
        add_signal("has_link", 0.18)
    if coupons:
        add_signal("has_coupon", 0.06)
    if merchant:
        add_signal(f"merchant:{merchant}", 0.22)
    if price.value is not None and price.reason != "discount_only":
        add_signal(f"price:{price.reason}", 0.24)
    if any(term in lowered for term in OFFER_TERMS):
        add_signal("offer_terms", 0.13)
    if title:
        add_signal("product_title", 0.17)
    if len(links) > 1:
        add_signal("multi_link", 0.02)

    coupon_only = _looks_like_coupon_only(text, title)
    if coupon_only:
        add_signal("coupon_only_penalty", -0.35)
    if price.reason == "discount_only":
        add_signal("discount_price_penalty", -0.22)
    if not title and price.value is not None:
        add_signal("missing_product_title_penalty", -0.18)
    if not links and not coupons:
        add_signal("not_actionable", -0.40)

    score = max(0.0, min(1.0, score))
    if coupon_only:
        message_type = "coupon_only"
    elif coupons and len(links) > 3 and not title:
        message_type = "coupon_bundle"
    elif title and price.value is not None:
        message_type = "product_offer"
    elif title and links:
        message_type = "link_offer"
    else:
        message_type = "unknown"

    accepted = (
        message_type == "product_offer"
        and score >= min_confidence
        and price.value is not None
        and price.reason != "discount_only"
    )
    reason = "accepted_by_offer_signals" if accepted else "insufficient_offer_signals"
    if coupon_only:
        reason = "coupon_only_without_product"

    return OfferCandidate(
        accepted=accepted,
        confidence=round(score, 4),
        message_type=message_type,
        product_title=title,
        price=price.value if price.reason != "discount_only" else None,
        old_price=price.old_value,
        merchant=merchant,
        reason=reason,
        signals=signals,
        score_breakdown=score_breakdown,
    )
