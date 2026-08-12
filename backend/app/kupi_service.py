"""
Wraps the kupiapi library (KupiScraper) and turns its output into the
flat Offer shape the frontend consumes.

kupiapi's get_discounts_by_search() returns JSON grouped BY PRODUCT, with
parallel arrays for each shop carrying it, e.g.:

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

Two things kupiapi does NOT give us, by design of the source site's HTML:
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

from kupiapi.scraper import KupiScraper
from starlette.concurrency import run_in_threadpool

from .config import CACHE_TTL_SECONDS, DEFAULT_MAX_PAGES, STORES
from .price_history import annotate_historical_bests
from .schemas import TrackingRule

_scraper = KupiScraper()

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
    name = _normalized_text(product_name)
    if not name:
        return False
    if any(_normalized_text(term) in name for term in rule.excluded_terms if term.strip()):
        return False
    if rule.match_mode == "exact":
        exact_name = _normalized_text(rule.exact_product_name or rule.label)
        # Kupi can append a size or a retailer modifier. Keeping the chosen
        # product phrase intact still avoids unrelated results such as aspic.
        return exact_name in name
    return True


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
    """Read optional image fields from kupiapi without relying on one version.

    kupiapi 1.0.11 does not currently scrape image tags. This keeps the API
    forward-compatible with an upgraded or locally extended scraper and lets
    the UI switch to real photos automatically once they are available.
    """
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
                "saving_vs_next_percent": None,
                "better_deal": None,
            })

    return offers


def enrich_offer_insights(offers: list[dict]) -> list[dict]:
    """Mark the cheapest comparable offer for every tracked phrase and unit."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for offer in offers:
        if offer.get("unit_price") is not None and offer.get("unit"):
            # tracked_item may be a structured object; derive a stable key
            tracked = offer.get("tracked_item")
            rule_key = offer.get("tracking_rule_id") or (
                tracked["keyword"] if isinstance(tracked, dict) and tracked.get("keyword") else tracked
            )
            groups.setdefault((rule_key, offer["unit"]), []).append(offer)

    for group in groups.values():
        # Compare shops, not duplicate package variants inside one shop.
        # A cheap Lidl egg pack must not create a misleading "go to Lidl"
        # tip on another Lidl egg pack.
        by_shop: dict[str, list[dict]] = {}
        for offer in group:
            by_shop.setdefault(offer["shop_raw"], []).append(offer)
        shop_winners = [min(shop_offers, key=lambda offer: offer["unit_price"]) for shop_offers in by_shop.values()]
        ranked = sorted(shop_winners, key=lambda offer: offer["unit_price"])
        winner = ranked[0]
        winner["is_best_deal"] = True
        if len(ranked) > 1 and ranked[1]["unit_price"] > winner["unit_price"]:
            winner["saving_vs_next_percent"] = round(
                (ranked[1]["unit_price"] - winner["unit_price"]) / ranked[1]["unit_price"] * 100
            )
        for shop_winner in ranked[1:]:
            if shop_winner["unit_price"] <= winner["unit_price"]:
                shop_winner["is_best_deal"] = True
                continue
            for offer in by_shop[shop_winner["shop_raw"]]:
                if offer["unit_price"] > winner["unit_price"]:
                    offer["better_deal"] = {
                        "shop_name": winner["shop_raw"],
                        "price": winner.get("price"),
                        "amount": winner.get("amount"),
                        "unit_price_label": winner.get("unit_price_label"),
                    }

    annotate_historical_bests(offers)
    return offers


def build_store_summaries(offers: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for offer in offers:
        key = offer.get("store_id") or f"raw:{offer['shop_raw']}"
        if key not in grouped:
            store_id = offer.get("store_id")
            grouped[key] = {
                "id": store_id,
                "label": STORES[store_id]["label"] if store_id in STORES else offer["shop_raw"],
                "offer_count": 0,
                "coverage_count": 0,
                "best_deal_count": 0,
                "recommendation_score": 0,
                "is_recommended": False,
                "_covered_rules": set(),
                "_best_rules": set(),
            }
        grouped[key]["offer_count"] += 1
        tracked = offer.get("tracked_item")
        tracked_key = tracked["keyword"] if isinstance(tracked, dict) and tracked.get("keyword") else tracked
        rule_key = offer.get("tracking_rule_id") or tracked_key or offer["shop_raw"]
        grouped[key]["_covered_rules"].add(rule_key)
        if offer.get("is_best_deal"):
            grouped[key]["_best_rules"].add(rule_key)

    for summary in grouped.values():
        summary["coverage_count"] = len(summary.pop("_covered_rules"))
        summary["best_deal_count"] = len(summary.pop("_best_rules"))
        # One-stop coverage matters most; winning the unit-price comparison is
        # a meaningful secondary tie breaker. Raw sale percentage is omitted:
        # it is often marketing noise rather than a useful shopping signal.
        summary["recommendation_score"] = summary["coverage_count"] * 100 + summary["best_deal_count"] * 25

    summaries = sorted(
        grouped.values(),
        key=lambda summary: (
            -summary["recommendation_score"],
            -summary["coverage_count"],
            -summary["best_deal_count"],
            -summary["offer_count"],
            summary["label"],
        ),
    )
    if summaries:
        summaries[0]["is_recommended"] = True
    return summaries


def build_top_hits(offers: list[dict], limit: int = 3) -> list[dict]:
    winners = [offer for offer in offers if offer.get("is_best_deal") and offer.get("unit_price") is not None]
    return sorted(
        winners,
        key=lambda offer: (
            not offer.get("is_historical_best", False),
            -(offer.get("saving_vs_next_percent") or 0),
            (offer.get("tracked_item") or {}).get("keyword") if isinstance(offer.get("tracked_item"), dict) else offer.get("tracked_item"),
        ),
    )[:limit]


def _fetch_one_sync(item: str) -> list[dict]:
    """Blocking call - runs kupiapi's scraper. Only call via run_in_threadpool."""
    now = time.time()
    cached = _cache.get(item)
    if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    raw_json = _scraper.get_discounts_by_search(item, max_pages=DEFAULT_MAX_PAGES)
    offers = _flatten(raw_json, item)
    _cache[item] = (now, offers)
    return offers


async def get_offers_for_items(
    items: list[str], store_ids: set[str] | None
) -> tuple[list[dict], list[str]]:
    """
    Fetches (and flattens) offers for every tracked item concurrently,
    then filters by the requested store IDs.

    A failure while scraping one item is not fatal for the others - it's
    collected into `errors` and returned alongside whatever did succeed.
    """
    rules = [TrackingRule(id=item, query=item, label=item) for item in items]
    return await get_offers_for_rules(rules, store_ids)


async def get_offers_for_rules(
    rules: list[TrackingRule], store_ids: set[str] | None
) -> tuple[list[dict], list[str]]:
    """Fetch offers for the user's broad/exact tracking rules."""
    errors: list[str] = []

    async def fetch(rule: TrackingRule) -> list[dict]:
        try:
            found = await run_in_threadpool(_fetch_one_sync, rule.query)
            results = []
            for offer in found:
                if not _matches_rule(offer.get("product_name"), rule):
                    continue
                tracked = {
                    "keyword": rule.query,
                    "label": rule.label,
                    "blacklist": rule.excluded_terms or [],
                    "temporary": str(rule.id).startswith("tmp-"),
                }
                results.append({
                    **offer,
                    "tracked_item": tracked,
                    "tracking_rule_id": rule.id,
                    "visual_key": rule.visual_key,
                    "on_sale": True,
                    "temporary": False,
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
