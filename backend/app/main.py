import asyncio
import time
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import MAX_TRACKED_ITEMS, STORES
from .image_cache import get_cached_image_url, store_cached_image_url
from .kupi_service import build_store_summaries, build_top_hits, get_offers_for_rules, get_product_suggestions
from .schemas import Offer, OffersResponse, StoreOut, StoreSummary, TrackingRule
from pydantic import TypeAdapter, ValidationError

app = FastAPI(title="Muj akcni letak API")

# Dev-friendly CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/stores", response_model=list[StoreOut])
def list_stores() -> list[dict]:
    return [{"id": store_id, "label": meta["label"]} for store_id, meta in STORES.items()]


@app.get("/api/preferences")
def get_preferences() -> dict:
    prefs_path = Path(__file__).parent / "preferences.json"
    if not prefs_path.exists():
        return {"tracking_rules": [], "default_stores": list(STORES.keys())}
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
        rules = data.get("tracking_rules") or []
        return {"tracking_rules": rules, "default_stores": data.get("default_stores", list(STORES.keys()))}
    except Exception:
        return {"tracking_rules": [], "default_stores": list(STORES.keys())}


@app.post("/api/preferences")
def set_preferences(prefs: dict) -> dict:
    prefs_path = Path(__file__).parent / "preferences.json"
    try:
        if not isinstance(prefs, dict):
            raise ValueError("Invalid payload")
        tracking_rules = prefs.get("tracking_rules", [])
        default_stores = prefs.get("default_stores", list(STORES.keys()))
        prefs_path.write_text(
            json.dumps({"tracking_rules": tracking_rules, "default_stores": default_stores}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def parse_tracked_items(items: str) -> list[str]:
    item_list = [item.strip() for item in items.split(",") if item.strip()]
    if not item_list:
        raise HTTPException(status_code=422, detail="Zadejte alespoň jednu sledovanou položku.")
    if len(item_list) > MAX_TRACKED_ITEMS:
        raise HTTPException(
            status_code=422,
            detail=f"Lze sledovat nejvýše {MAX_TRACKED_ITEMS} položek.",
        )
    return item_list


def parse_tracking_rules(items: str, rules: str | None) -> list[TrackingRule]:
    if not rules:
        return [TrackingRule(id=item, query=item, label=item) for item in parse_tracked_items(items)]
    try:
        parsed = TypeAdapter(list[TrackingRule]).validate_python(json.loads(rules))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Neplatné sledovací pravidlo: {exc}") from exc
    if not parsed:
        raise HTTPException(status_code=422, detail="Zadejte alespoň jednu sledovanou položku.")
    if len(parsed) > MAX_TRACKED_ITEMS:
        raise HTTPException(status_code=422, detail=f"Lze sledovat nejvýše {MAX_TRACKED_ITEMS} položek.")
    return parsed


@app.get("/api/product-suggestions", response_model=list[str])
async def product_suggestions(query: str = Query(..., min_length=2, max_length=80)) -> list[str]:
    return await get_product_suggestions(query.strip())


# --- Open Food Facts image proxy -------------------------------------------
_off_request_lock = asyncio.Lock()
_off_last_request_at = 0.0
# Zkráceno z 6.5s na rozumný interval, aby požadavky neumíraly na timeout
_OFF_MIN_INTERVAL_SECONDS = 1.0  

_OFF_USER_AGENT = "MujAkcniLetak/1.0 (personal project; contact: replace-with-your-email@example.com)"


async def _throttled_off_get(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    global _off_last_request_at
    # Přidán timeout pro získávaní zámku (max 3 sekundy čekání ve frontě)
    try:
        async with asyncio.timeout(3.0):
            async with _off_request_lock:
                wait = _OFF_MIN_INTERVAL_SECONDS - (time.monotonic() - _off_last_request_at)
                if wait > 0:
                    await asyncio.sleep(wait)
                _off_last_request_at = time.monotonic()
                return await client.get(url, params=params)
    except TimeoutError:
        # Pokud je ve frontě moc požadavků, vyhodíme výjimku a vrátíme None (placeholder v UI)
        raise httpx.RequestError("Fronta požadavků na obrázky je plná.")


@app.get("/api/proxy-image")
async def proxy_image(
    query: str | None = Query(None, min_length=2, max_length=120),
    code: str | None = Query(None, min_length=8, max_length=32),
) -> dict:
    normalized_query = " ".join(query.split()) if query else None
    normalized_code = "".join(code.split()) if code else None
    if not normalized_code and not normalized_query:
        raise HTTPException(status_code=422, detail="Zadejte query nebo code.")

    cache_key = f"ean:{normalized_code}" if normalized_code else f"name:{(normalized_query or '').lower()}"
    cached_image_url = get_cached_image_url(cache_key)

    if cached_image_url is not None:
        return {"image_url": cached_image_url or None}

    if normalized_code:
        target_url = "https://world.openfoodfacts.org/api/v2/search"
        request_params = {
            "code": normalized_code,
            "fields": "product_name,image_front_url,image_url",
        }
    else:
        target_url = "https://world.openfoodfacts.org/cgi/search.pl"
        request_params = {
            "search_terms": normalized_query,
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": "1",
            "fields": "product_name,image_front_url,image_url",
        }

    try:
        headers = {"User-Agent": _OFF_USER_AGENT}
        # Krátký timeout 5s na samotný požadavek
        async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:
            response = await _throttled_off_get(client, target_url, request_params)

            if response.status_code in (429, 503, 502, 500):
                print(f"⚠️ Open Food Facts nestíhá (Status {response.status_code}) pro: {normalized_query or normalized_code}")
                # Uložíme prázdný výsledek do cache, ať to na stejný produkt znovu nezkouší
                store_cached_image_url(cache_key, normalized_query or normalized_code or "", None)
                return {"image_url": None}

            response.raise_for_status()
            payload = response.json()

    except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
        print(f"⚠️ Chyba při získávání obrázku pro '{normalized_query or normalized_code}': {exc}")
        # Při chybě uložíme prázdný záznam do cache, aby nepohřbil další požadavky v pořadí
        store_cached_image_url(cache_key, normalized_query or normalized_code or "", None)
        return {"image_url": None}

    products = payload.get("products") or []
    product = next((item for item in products if item.get("image_front_url") or item.get("image_url")), None)
    image_url = (product.get("image_front_url") or product.get("image_url")) if product else None
    store_cached_image_url(cache_key, normalized_query or normalized_code or "", image_url)

    return {"image_url": image_url}


@app.get("/api/offers", response_model=OffersResponse)
async def offers(
    items: str = Query(
        "", description="Legacy comma-separated tracked items, e.g. 'vejce,kureci prsa'"
    ),
    rules: str | None = Query(None, description="JSON array of broad or exact tracking rules."),
    stores: str = Query(
        "", description="Comma-separated store IDs, e.g. 'lidl,albert'. Empty = no filter."
    ),
    include_missing: bool = Query(False, description="Include items not currently on sale as explicit entries."),
) -> dict:
    tracking_rules = parse_tracking_rules(items, rules)
    store_ids = {s.strip() for s in stores.split(",") if s.strip()} or None

    flat, errors = await get_offers_for_rules(tracking_rules, store_ids)

    if include_missing:
        considered_stores = list(store_ids) if store_ids else list(STORES.keys())
        for rule in tracking_rules:
            for sid in considered_stores:
                found = any(
                    (o.get("store_id") == sid)
                    and (
                        (isinstance(o.get("tracked_item"), dict) and o.get("tracked_item").get("keyword") == rule.query)
                        or (o.get("tracked_item") == rule.label)
                    )
                    for o in flat
                )
                if not found:
                    flat.append(
                        {
                            "product_name": None,
                            "shop_raw": STORES[sid]["label"] if sid in STORES else sid,
                            "store_id": sid,
                            "price": None,
                            "amount": None,
                            "validity": None,
                            "tracked_item": {"keyword": rule.query, "blacklist": rule.excluded_terms or [], "temporary": False},
                            "tracking_rule_id": rule.id,
                            "visual_key": rule.visual_key,
                            "on_sale": False,
                            "temporary": False,
                        }
                    )

    summaries = build_store_summaries(flat)
    store_order = {summary["id"] or f"raw:{summary['label']}": index for index, summary in enumerate(summaries)}
    flat.sort(key=lambda offer: store_order.get(offer.get("store_id") or f"raw:{offer['shop_raw']}", len(store_order)))

    return {
        "items": [Offer(**o) for o in flat],
        "store_summaries": [StoreSummary(**summary) for summary in summaries],
        "top_hits": [Offer(**offer) for offer in build_top_hits(flat)],
        "fetched_at": datetime.now(timezone.utc),
        "errors": errors,
    }