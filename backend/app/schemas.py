from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StoreOut(BaseModel):
    id: str
    label: str


class TrackingRule(BaseModel):
    """A persisted user choice, from a broad phrase to an exact Kupi product."""

    id: str
    query: str
    label: str
    match_mode: Literal["broad", "exact"] = "broad"
    exact_product_name: str | None = None
    excluded_terms: list[str] = Field(default_factory=list)
    visual_key: str | None = None


class TrackedItem(BaseModel):
    keyword: str
    blacklist: list[str] = Field(default_factory=list)
    temporary: bool = False


class Offer(BaseModel):
    """One (product, shop) offer, flattened out of kupiapi's grouped result."""

    product_name: str | None = None
    shop_raw: str  # shop name exactly as scraped, e.g. "Albert hypermarket"
    store_id: str | None = None  # our normalized ID, or None if unrecognized
    price: str | None = None  # raw display string, e.g. "29,90 Kč"
    amount: str | None = None  # raw display string, e.g. "10 ks"
    validity: str | None = None  # raw display string, e.g. "dnes končí"
    tracked_item: TrackedItem
    on_sale: bool = True
    temporary: bool = False
    tracking_rule_id: str | None = None
    visual_key: str | None = None
    image_url: str | None = None
    unit_price: float | None = None
    unit: str | None = None
    unit_price_label: str | None = None
    is_best_deal: bool = False
    saving_vs_next_percent: int | None = None
    historical_best_unit_price: float | None = None
    is_historical_best: bool = False
    better_deal: "BetterDeal | None" = None


class BetterDeal(BaseModel):
    shop_name: str
    price: str | None = None
    amount: str | None = None
    unit_price_label: str | None = None


class StoreSummary(BaseModel):
    id: str | None = None
    label: str
    offer_count: int
    coverage_count: int = 0
    best_deal_count: int = 0
    recommendation_score: int = 0
    is_recommended: bool = False


class OffersResponse(BaseModel):
    items: list[Offer]
    store_summaries: list[StoreSummary] = []
    top_hits: list[Offer] = []
    fetched_at: datetime
    errors: list[str] = []
