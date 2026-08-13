import asyncio
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import MAX_TRACKED_ITEMS, STORES
from .image_cache import clear_empty_negative_cache, get_cached_image_url, store_cached_image_url
from .kupi_service import build_store_summaries, build_top_hits, get_offers_for_rules, get_product_suggestions
from .schemas import Offer, OffersResponse, StoreOut, StoreSummary, TrackingRule
from pydantic import TypeAdapter, ValidationError

# ------------------------------------------------------------------------------
# KONFIGURACE LOGOVÁNÍ
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("akcni_letak.proxy")

app = FastAPI(title="Muj akcni letak API")

# Při startu backendu promažeme staré prázdné záznamy
clear_empty_negative_cache()

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
    except Exception as exc:
        logger.warning(f"Chyba při čtení preferences.json: {exc}")
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
        logger.error(f"Chyba při zápisu preferences.json: {exc}")
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


# --- Čištění a validace dotazů pro vyhledávání obrázků --------------------

def clean_search_query(query: str) -> str:
    """Odstraní z názvu akčního letáku názvy supermarketů, značky a balení."""
    if not query:
        return ""

    q = query.lower()
    stop_words = [
        "albertovo uzenářství", "albertovo uzenarstvi", "kostelecké uzeniny", "kostelecke uzeniny",
        "řezníkův talíř", "reznikov talir", "reznikuv talir", "srdce domova", "jihočeský", "jihocesky",
        "nature's promise", "natures promise", "billa bonvia", "karlova koruna", "česká farma", "ceska farma",
        "jaroměřický", "jaromericky", "delikátní", "delikatni", "yes plants", "grill party",
        "madeta", "olma", "milko", "albert", "billa", "penny", "lidl", "pilos", "pikok", "le&co", "le & co",
        "idema", "president", "kupi", "dětská", "detska",
        "nejvyšší jakosti", "nejvyssi jakosti", "výběrová", "vyberova", "standard", "poctivá", "poctiva",
        "z podestýlky", "z podestylky", "z poděbrad", "z podebrad", "od kosti", "na rohlik", "na rohlík",
        "akce", "sleva", "balení", "baleni"
    ]

    for word in stop_words:
        q = q.replace(word, " ")

    q = re.sub(r'\b[a-z0-9]\b', ' ', q)
    cleaned = " ".join(q.split())
    return cleaned if len(cleaned) >= 2 else query


def normalize_str(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower()


def is_relevant_product(query: str, product_name: str) -> bool:
    """Ověří, zda nalezený produkt v OFF odpovídá hledanému zboží."""
    if not product_name:
        return False

    q_norm = normalize_str(query)
    p_norm = normalize_str(product_name)

    # Odmítneme tyčinky/snacky pouze pokud se v dotazu výslovně nehledá tyčinka
    mismatch_keywords = ["tycinka", "snack", "krekr", "cracker", "chips", "protein bar"]
    for bad in mismatch_keywords:
        if bad in p_norm and bad not in q_norm:
            logger.info(f"  └─ ❌ [BE Filter] Produkt '{product_name}' zamítnut (obsahuje '{bad}')")
            return False

    q_words = [w for w in q_norm.split() if len(w) >= 3]
    if q_words:
        has_match = any(w in p_norm for w in q_words)
        if not has_match:
            logger.info(f"  └─ ❌ [BE Filter] Produkt '{product_name}' zamítnut (žádné ze slov {q_words} nebylo v názvu)")
            return False

    logger.info(f"  └─ ✅ [BE Filter] Produkt '{product_name}' schválen!")
    return True


# --- Open Food Facts image proxy -------------------------------------------
_off_request_lock = asyncio.Lock()
_off_last_request_at = 0.0
_OFF_MIN_INTERVAL_SECONDS = 0.4
_OFF_USER_AGENT = "MujAkcniLetak/1.0 (personal project; contact: replace-with-your-email@example.com)"


async def _throttled_off_get(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    global _off_last_request_at

    async def _acquire_and_fetch():
        async with _off_request_lock:
            wait = _OFF_MIN_INTERVAL_SECONDS - (time.monotonic() - _off_last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            _off_last_request_at = time.monotonic()
            return await client.get(url, params=params)

    return await asyncio.wait_for(_acquire_and_fetch(), timeout=4.0)


async def fetch_off_image(client: httpx.AsyncClient, search_term: str, original_query: str) -> str | None:
    target_url = "https://world.openfoodfacts.org/cgi/search.pl"
    request_params = {
        "search_terms": search_term,
        "search_simple": "1",
        "action": "process",
        "json": "1",
        "page_size": "5",
        "fields": "product_name,image_front_url,image_url",
    }

    try:
        logger.info(f"📡 [BE OFF Fetch] Odesílám dotaz na Open Food Facts pro: '{search_term}'")
        response = await _throttled_off_get(client, target_url, request_params)

        if response.status_code != 200:
            logger.warning(f"⚠️ [BE OFF Fetch] OFF vrátil status {response.status_code}")
            return None

        payload = response.json()
        products = payload.get("products") or []
        logger.info(f"📦 [BE OFF Fetch] Získán seznam {len(products)} produktů z OFF pro '{search_term}'")

        for index, prod in enumerate(products, 1):
            pname = prod.get("product_name", "Bez názvu")
            img = prod.get("image_front_url") or prod.get("image_url")
            logger.info(f"  ├─ Candidate #{index}: '{pname}' (Image: {'Ano' if img else 'Ne'})")

            if img and is_relevant_product(original_query, pname):
                return img

    except Exception as exc:
        logger.warning(f"⚠️ [BE OFF Fetch] Výjimka při vyhledávání '{search_term}': {exc}")

    return None


@app.get("/api/proxy-image")
async def proxy_image(
    query: str | None = Query(None, min_length=2, max_length=120),
    code: str | None = Query(None, min_length=8, max_length=32),
) -> dict:
    start_time = time.monotonic()
    search_label = query or code or "neznámý"
    logger.info(f"🚀 [BE Endpoint] PŘIJAT POŽADAVEK -> Query: '{query}', Code: '{code}'")

    try:
        normalized_query = " ".join(query.split()) if query else None
        normalized_code = "".join(code.split()) if code else None

        if not normalized_code and not normalized_query:
            return {"image_url": None}

        cache_key = f"ean:{normalized_code}" if normalized_code else f"name:{(normalized_query or '').lower()}"

        cached_image_url = get_cached_image_url(cache_key)

        if cached_image_url is not None:
            elapsed = round((time.monotonic() - start_time) * 1000)
            if cached_image_url != "":
                logger.info(f"⚡ [BE Cache HIT] Vráceno z databáze za {elapsed} ms -> '{cached_image_url}'")
                return {"image_url": cached_image_url}
            else:
                logger.info(f"🛡️ [BE Cache FRESH NEGATIVE] V databázi je čerstvý negativní záznam. Vráceno za {elapsed} ms -> None")
                return {"image_url": None}

        cleaned_query = clean_search_query(normalized_query) if normalized_query else None
        logger.info(f"🧹 [BE Clean] Původní: '{normalized_query}' -> Vyčištěno: '{cleaned_query}'")

        headers = {"User-Agent": _OFF_USER_AGENT}
        matched_image_url = None

        async with httpx.AsyncClient(timeout=4.0, headers=headers) as client:
            # 1. Pokus: Vyčištěný název
            if cleaned_query:
                matched_image_url = await fetch_off_image(client, cleaned_query, normalized_query or "")

            # 2. Pokus: První hlavní slovo (fallback)
            if not matched_image_url and cleaned_query:
                first_word = cleaned_query.split()[0]
                if len(first_word) >= 3 and first_word != cleaned_query:
                    logger.info(f"🔄 [BE Fallback] Zkouším hledat pouze slovo '{first_word}'")
                    matched_image_url = await fetch_off_image(client, first_word, normalized_query or "")

        elapsed = round((time.monotonic() - start_time) * 1000)
        logger.info(f"💾 [BE Store & Return] Hotovo za {elapsed} ms. Výsledek '{matched_image_url or 'NULL'}' uložím do keše.")
        store_cached_image_url(cache_key, normalized_query or normalized_code or "", matched_image_url)

        return {"image_url": matched_image_url}

    except Exception as exc:
        logger.error(f"❌ [BE ERROR] Chyba proxy_image pro '{search_label}': {exc}", exc_info=True)
        return {"image_url": None}


@app.get("/api/offers", response_model=OffersResponse)
async def offers(
    items: str = Query("", description="Legacy comma-separated tracked items"),
    rules: str | None = Query(None, description="JSON array of broad or exact tracking rules."),
    stores: str = Query("", description="Comma-separated store IDs"),
    include_missing: bool = Query(False, description="Include items not currently on sale"),
) -> dict:
    logger.info(f"📊 [Offers] Načítám nabídky pro rules='{rules or items}', stores='{stores}'")
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