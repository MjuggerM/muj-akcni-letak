import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import MAX_TRACKED_ITEMS, STORES
from .image_service import ImageLookupService
from .kupi_service import get_offers_for_rules, get_product_preview, get_product_suggestions
from .schemas import (
    Offer,
    OffersResponse,
    PreferencesUpdate,
    ProductPreview,
    RuleExclusionUpdate,
    StoreOut,
    TrackingRule,
)
from pydantic import TypeAdapter, ValidationError

# ------------------------------------------------------------------------------
# KONFIGURACE LOGOVÁNÍ
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("akcni_letak.proxy")



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Jediný worker, který smí mluvit s Open Food Facts (viz app/image_service.py).
    service = ImageLookupService()
    app.state.image_service = service
    await service.start()
    try:
        yield
    finally:
        await service.stop()


app = FastAPI(title="Muj akcni letak API", lifespan=lifespan)

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
        rules = TypeAdapter(list[TrackingRule]).validate_python(data.get("tracking_rules") or [])
        return {
            "tracking_rules": [rule.model_dump() for rule in rules],
            "default_stores": data.get("default_stores", list(STORES.keys())),
        }
    except Exception as exc:
        logger.warning(f"Chyba při čtení preferences.json: {exc}")
        return {"tracking_rules": [], "default_stores": list(STORES.keys())}


@app.post("/api/preferences")
def set_preferences(prefs: PreferencesUpdate) -> dict:
    prefs_path = Path(__file__).parent / "preferences.json"
    try:
        default_stores = prefs.default_stores
        if default_stores is None:
            default_stores = list(STORES.keys())
        prefs_path.write_text(
            json.dumps(
                {
                    "tracking_rules": [rule.model_dump() for rule in prefs.tracking_rules],
                    "default_stores": default_stores,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8"
        )
        return {"ok": True}
    except OSError as exc:
        logger.error(f"Chyba při zápisu preferences.json: {exc}")
        raise HTTPException(status_code=500, detail="Could not save preferences.") from exc


@app.patch("/api/rules/{rule_id}/exclude")
def exclude_from_rule(rule_id: str, update: RuleExclusionUpdate) -> dict:
    """Persist one product or product-type exclusion for a saved rule."""
    prefs_path = Path(__file__).parent / "preferences.json"
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.exists() else {}
        rules = TypeAdapter(list[TrackingRule]).validate_python(data.get("tracking_rules") or [])
        rule_index = next((index for index, rule in enumerate(rules) if rule.id == rule_id), None)
        if rule_index is None:
            raise HTTPException(status_code=404, detail="Sledovací pravidlo nebylo nalezeno.")

        rule = rules[rule_index]
        value = update.value.strip()
        target = rule.excluded_terms if update.type == "term" else rule.excluded_products
        normalized_value = " ".join(value.casefold().split())
        if not any(" ".join(existing.casefold().split()) == normalized_value for existing in target):
            target.append(value)
        rules[rule_index] = rule
        data["tracking_rules"] = [item.model_dump() for item in rules]
        data.setdefault("default_stores", list(STORES.keys()))
        prefs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "tracking_rule": rule.model_dump()}
    except HTTPException:
        raise
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("Could not update rule exclusion: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the exclusion.") from exc


@app.delete("/api/rules/{rule_id}/exclude")
def remove_rule_exclusion(rule_id: str, update: RuleExclusionUpdate) -> dict:
    """Remove one product or product-type exclusion when the user undoes it."""
    prefs_path = Path(__file__).parent / "preferences.json"
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.exists() else {}
        rules = TypeAdapter(list[TrackingRule]).validate_python(data.get("tracking_rules") or [])
        rule_index = next((index for index, rule in enumerate(rules) if rule.id == rule_id), None)
        if rule_index is None:
            raise HTTPException(status_code=404, detail="Sledovací pravidlo nebylo nalezeno.")

        rule = rules[rule_index]
        value = update.value.strip()
        target = rule.excluded_terms if update.type == "term" else rule.excluded_products
        normalized_value = " ".join(value.casefold().split())
        target[:] = [entry for entry in target if " ".join(entry.casefold().split()) != normalized_value]
        rules[rule_index] = rule
        data["tracking_rules"] = [item.model_dump() for item in rules]
        data.setdefault("default_stores", list(STORES.keys()))
        prefs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "tracking_rule": rule.model_dump()}
    except HTTPException:
        raise
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("Could not remove rule exclusion: %s", exc)
        raise HTTPException(status_code=500, detail="Could not update the exclusion.") from exc


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


@app.get("/api/product-preview", response_model=list[ProductPreview])
async def product_preview(query: str = Query(..., min_length=2, max_length=80)) -> list[dict]:
    return await get_product_preview(query.strip(), limit=10)


# --- Fotky produktů -----------------------------------------------------------
# Veškerá logika (párování, odstup mezi dotazy na OFF, fronta) je v app/image_service.py.

@app.get("/api/proxy-image")
async def proxy_image(
    request: Request,
    query: str = Query(..., min_length=2, max_length=120),
    mode: Literal["legacy", "quality"] = Query("legacy"),
) -> dict:
    """Nikdy nečeká na Open Food Facts.

    status: "found"   -> image_url je fotka TOHOTO produktu
            "missing" -> potvrzeně žádná odpovídající fotka není (placeholder je konečný)
            "pending" -> zařazeno / zpracovává se; zeptej se znovu za `retry_after` sekund
            "error"   -> Open Food Facts je teď nedostupný; zkus to později
    """
    service: ImageLookupService = request.app.state.image_service
    result = service.lookup(query, mode)
    return {"status": result.status, "image_url": result.image_url, "retry_after": result.retry_after}


@app.get("/api/offers", response_model=OffersResponse)
async def offers(
    items: str = Query("", description="Legacy comma-separated tracked items"),
    rules: str | None = Query(None, description="JSON array of broad or exact tracking rules."),
    stores: str = Query("", description="Comma-separated store IDs"),
    include_missing: bool = Query(False, description="Include items not currently on sale"),
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
                            "tracked_item": {
                                "keyword": rule.query,
                                "excluded_terms": rule.excluded_terms or [],
                                "excluded_products": rule.excluded_products or [],
                                "temporary": False,
                            },
                            "tracking_rule_id": rule.id,
                            "visual_key": rule.visual_key,
                            "on_sale": False,
                            "temporary": False,
                        }
                    )

    return {
        "items": [Offer(**o) for o in flat],
        "fetched_at": datetime.now(timezone.utc),
        "errors": errors,
    }
