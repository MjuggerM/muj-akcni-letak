"""
Parses Kupi search pages into the flat Offer shape the frontend consumes.

Kupi groups results BY PRODUCT, with parallel arrays for each shop carrying
it, e.g.:

    {
        "name": "Vejce M 10ks",
        "shops":      ["Lidl", "Albert hypermarket"],
        "prices":     ["49,90 Kč", "29,90 Kč"],
        "amounts":    ["10 ks", "10 ks"],
        "validities": ["po 10. 8. - ne 16. 8.", "platí do úterý 11. 8."]
    }

shops[i] / prices[i] / amounts[i] / validities[i] all describe the same
offer at index i - they must be zipped together, not treated as separate
lists. This module flattens that into one Offer per (product, shop) pair.

Kupi does not provide the following as structured values:
  - a store ID or logo (only the free-text shop name) -> see config.STORES
  - a machine-parsable date for "validity" (it's phrases like "dnes
    končí" / "po 10. 8. - ne 16. 8.") -> we pass it through as-is rather
    than guessing a date format that will eventually break.
"""

import asyncio
import json
import re
import time
import unicodedata
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from starlette.concurrency import run_in_threadpool

from .config import CACHE_TTL_SECONDS, DEFAULT_MAX_PAGES, STORES
from .product_matching import score_product
from .schemas import TrackingRule

KUPI_BASE_URL = "https://www.kupi.cz"
KUPI_SEARCH_URL = f"{KUPI_BASE_URL}/hledej"
KUPI_REQUEST_TIMEOUT_SECONDS = 15

# Very small in-memory cache: {search_term: (timestamp, offers)}.
# Fine for a single-user local app; swap for Redis if this ever runs
# multi-user/multi-process.
_cache: dict[str, tuple[float, list[dict]]] = {}


def _match_store_id(shop_name: str) -> str | None:
    lowered = shop_name.lower()
    for store_id, meta in STORES.items():
        if any(token in lowered for token in meta["match"]):
            return store_id
    return None


def _normalized_text(value: str | None) -> str:
    """Compare product names independent of casing and Czech accents."""
    return " ".join(
        unicodedata.normalize("NFD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .split()
    )


def _matches_rule(product_name: str | None, rule: TrackingRule) -> bool:
    return score_product(
        rule.query,
        product_name,
        match_mode=rule.match_mode,
        exact_product_name=rule.exact_product_name or rule.label,
        excluded_terms=rule.excluded_terms,
        excluded_products=rule.excluded_products,
    )["confidence"] != "none"


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value.replace("\u00a0", " "))
    return float(match.group(0).replace(",", ".")) if match else None


def _unit_price(price: str | None, amount: str | None) -> tuple[float | None, str | None]:
    """Return a comparable price and its unit from the textual Kupi amount."""
    price_value = _number(price)
    if price_value is None or not amount:
        return None, None

    normalized = amount.lower().replace("\u00a0", " ")
    match = re.search(
        r"(?:(\d+(?:[.,]\d+)?)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*"
        r"(kg|g|ml|l|ks|kus(?:ů|y)?|bal(?:ení)?)\b",
        normalized,
    )
    if not match:
        return None, None

    multiplier = float((match.group(1) or "1").replace(",", "."))
    quantity = float(match.group(2).replace(",", ".")) * multiplier
    raw_unit = match.group(3)
    if raw_unit == "kg":
        return round(price_value / quantity, 2), "kg"
    if raw_unit == "g":
        return round(price_value / (quantity / 1000), 2), "kg"
    if raw_unit == "l":
        return round(price_value / quantity, 2), "l"
    if raw_unit == "ml":
        return round(price_value / (quantity / 1000), 2), "l"
    return round(price_value / quantity, 2), "ks"


def _image_url(product: dict) -> str | None:
    """Read an optional image field while accepting multiple source shapes."""
    candidate_keys = (
        "image_front_url",
        "image_url",
        "image",
        "image_src",
        "src",
        "data_src",
        "data-src",
        "thumbnail",
        "thumbnail_url",
    )

    def extract(candidate: object) -> str | None:
        if isinstance(candidate, str) and candidate:
            return candidate
        if isinstance(candidate, dict):
            for nested_key in ("url", "src", "image", "image_url", "image_front_url", "data-src", "data_src"):
                nested_value = candidate.get(nested_key)
                if isinstance(nested_value, str) and nested_value:
                    return nested_value
        return None

    for key in candidate_keys:
        image = extract(product.get(key))
        if image:
            return f"https:{image}" if image.startswith("//") else image

    for key in ("image_urls", "images", "image_list"):
        images = product.get(key) or []
        if isinstance(images, list):
            for item in images:
                image = extract(item)
                if image:
                    return f"https:{image}" if image.startswith("//") else image

    return None


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\u00a0", " ").replace("\n", "").split())
    if cleaned.startswith("/"):
        cleaned = cleaned[1:].strip()
    return cleaned or None


def _product_image(product_node) -> str | None:
    image = product_node.select_one(".product_image img")
    if image is None:
        return None

    # Kupi puts a generic placeholder in `src` and the real image in `data-src`.
    for attribute in ("data-src", "data-original", "src"):
        candidate = image.get(attribute)
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate = candidate.strip()
        if "/no_img/" in candidate.lower() or "no-image" in candidate.lower():
            continue

        resolved = urljoin(KUPI_BASE_URL, candidate)
        parsed = urlparse(resolved)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme in {"http", "https"} and (hostname == "kupi.cz" or hostname.endswith(".kupi.cz")):
            return resolved
    return None


def _parse_search_page(html: bytes | str) -> list[dict]:
    """Parse Kupi products, offers and thumbnails from the same search response."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[dict] = []

    for product_node in soup.find_all("div", class_="group_discounts"):
        name_node = product_node.select_one(".product_name strong")
        if name_node is None:
            continue

        discounts_table = product_node.find("div", class_="discounts_table")
        if discounts_table is None:
            break

        shops = discounts_table.find_all("span", class_="discounts_shop_name")
        if not shops:
            break

        product_data = discounts_table.find_all("div", class_="discount_row")
        prices: list[str | None] = []
        amounts: list[str | None] = []
        validities: list[str | None] = []
        for row in product_data:
            price = row.find(class_="discount_price_value")
            amount = row.find(class_="discount_amount")
            validity = row.find("div", class_="discounts_validity")
            prices.append(_clean_text(price.get_text() if price else None))
            amounts.append(_clean_text(amount.get_text() if amount else None))
            validities.append(_clean_text(validity.get_text() if validity else None))

        products.append({
            "name": _clean_text(name_node.get_text()),
            "shops": [_clean_text(shop.get_text()) for shop in shops],
            "prices": prices,
            "amounts": amounts,
            "validities": validities,
            "image_url": _product_image(product_node),
        })

    return products


def _fetch_search_results(item: str) -> str:
    """Fetch Kupi pages once and parse both existing offer data and product photos."""
    products: list[dict] = []
    page = 1
    while DEFAULT_MAX_PAGES == 0 or page <= DEFAULT_MAX_PAGES:
        params = {"f": item, "vse": "0"}
        if page > 1:
            params["page"] = str(page)
        response = requests.get(
            KUPI_SEARCH_URL,
            params=params,
            timeout=KUPI_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            if page == 1:
                return "[]"
            break

        page_products = _parse_search_page(response.content)
        if not page_products:
            break
        products.extend(page_products)
        page += 1

    return json.dumps(products, ensure_ascii=False)


def _flatten(raw_json: str, tracked_item: str) -> list[dict]:
    products = json.loads(raw_json)
    offers: list[dict] = []

    for product in products:
        shops = product.get("shops") or []
        prices = product.get("prices") or []
        amounts = product.get("amounts") or []
        validities = product.get("validities") or []

        for i, shop in enumerate(shops):
            price = prices[i] if i < len(prices) else None
            amount = amounts[i] if i < len(amounts) else None
            unit_price, unit = _unit_price(price, amount)
            offers.append({
                "product_name": product.get("name"),
                "shop_raw": shop,
                "store_id": _match_store_id(shop),
                "price": price,
                "amount": amount,
                "validity": validities[i] if i < len(validities) else None,
                "tracked_item": tracked_item,
                "tracking_rule_id": None,
                "visual_key": None,
                "image_url": _image_url(product),
                "unit_price": unit_price,
                "unit": unit,
                "unit_price_label": f"{unit_price:.2f} Kč/{unit}" if unit_price is not None else None,
                "is_best_deal": False,
            })

    return offers


def enrich_offer_insights(offers: list[dict]) -> list[dict]:
    """Mark the cheapest comparable package for each tracking rule and unit."""
    for offer in offers:
        offer["is_best_deal"] = False

    groups: dict[tuple[str, str], list[dict]] = {}
    for offer in offers:
        if offer.get("unit_price") is not None and offer.get("unit"):
            tracked = offer.get("tracked_item")
            rule_key = offer.get("tracking_rule_id") or (
                tracked["keyword"] if isinstance(tracked, dict) and tracked.get("keyword") else tracked
            )
            groups.setdefault((rule_key, offer["unit"]), []).append(offer)

    for group in groups.values():
        by_shop: dict[str, list[dict]] = {}
        for offer in group:
            by_shop.setdefault(offer["shop_raw"], []).append(offer)
        shop_winners = {
            shop: min(shop_offers, key=lambda offer: offer["unit_price"])
            for shop, shop_offers in by_shop.items()
        }
        lowest_unit_price = min(offer["unit_price"] for offer in shop_winners.values())
        for winner in shop_winners.values():
            if winner["unit_price"] == lowest_unit_price:
                winner["is_best_deal"] = True

    return offers


def _fetch_one_sync(item: str) -> list[dict]:
    """Blocking Kupi request; only call through run_in_threadpool."""
    now = time.time()
    cached = _cache.get(item)
    if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    raw_json = _fetch_search_results(item)
    offers = _flatten(raw_json, item)
    _cache[item] = (now, offers)
    return offers


async def get_offers_for_rules(
    rules: list[TrackingRule], store_ids: set[str] | None
) -> tuple[list[dict], list[str]]:
    """Fetch offers and confidence metadata for the user's smart/exact rules."""
    errors: list[str] = []

    async def fetch(rule: TrackingRule) -> list[dict]:
        try:
            found = await run_in_threadpool(_fetch_one_sync, rule.query)
            results = []
            for offer in found:
                match = score_product(
                    rule.query,
                    offer.get("product_name"),
                    match_mode=rule.match_mode,
                    exact_product_name=rule.exact_product_name or rule.label,
                    excluded_terms=rule.excluded_terms,
                    excluded_products=rule.excluded_products,
                )
                if match["confidence"] == "none":
                    continue
                tracked = {
                    "keyword": rule.query,
                    "label": rule.label,
                    "excluded_terms": rule.excluded_terms or [],
                    "excluded_products": rule.excluded_products or [],
                    "temporary": str(rule.id).startswith("tmp-"),
                }
                results.append({
                    **offer,
                    "tracked_item": tracked,
                    "tracking_rule_id": rule.id,
                    "visual_key": rule.visual_key,
                    "on_sale": True,
                    "temporary": str(rule.id).startswith("tmp-"),
                    "confidence": match["confidence"],
                    "match_reason": match["match_reason"],
                    "suggested_exclusion_term": match["suggested_exclusion_term"],
                })
            return results
        except Exception as exc:  # kupi.cz layout change, network hiccup, etc.
            errors.append(f"{rule.label}: {exc}")
            return []

    results = await asyncio.gather(*(fetch(rule) for rule in rules))
    flat = [offer for sublist in results for offer in sublist]

    if store_ids:
        flat = [o for o in flat if o["store_id"] in store_ids]

    return enrich_offer_insights(flat), errors


async def get_product_suggestions(query: str, limit: int = 12) -> list[str]:
    """Return distinct discounted Kupi product names for a precise-rule picker."""
    offers = await run_in_threadpool(_fetch_one_sync, query)
    names: list[str] = []
    seen: set[str] = set()
    for offer in offers:
        name = (offer.get("product_name") or "").strip()
        key = _normalized_text(name)
        if name and key not in seen:
            seen.add(key)
            names.append(name)
        if len(names) >= limit:
            break
    return names


async def get_product_preview(query: str, limit: int = 10) -> list[dict]:
    """Return the first distinct smart matches for the add-rule preview."""
    offers = await run_in_threadpool(_fetch_one_sync, query)
    previews: list[dict] = []
    seen: set[str] = set()
    for offer in offers:
        name = (offer.get("product_name") or "").strip()
        key = _normalized_text(name)
        if not name or key in seen:
            continue
        seen.add(key)
        match = score_product(query, name)
        if match["confidence"] == "none":
            continue
        previews.append({"product_name": name, **match})
        if len(previews) >= limit:
            break
    return previews
