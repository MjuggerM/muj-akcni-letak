from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class StoreOut(BaseModel):
    id: str
    label: str


class TrackingRule(BaseModel):
    """A persisted smart or exact product search and its user exclusions."""

    id: str
    query: str
    label: str
    match_mode: Literal["smart", "exact"] = "smart"
    exact_product_name: str | None = None
    excluded_terms: list[str] = Field(default_factory=list)
    excluded_products: list[str] = Field(default_factory=list)

    @field_validator("match_mode", mode="before")
    @classmethod
    def migrate_broad_mode(cls, value: object) -> object:
        # Keep older saved preferences and clients working while exposing one
        # canonical broad-search mode to new code.
        return "smart" if value == "broad" else value

    @model_validator(mode="before")
    @classmethod
    def merge_legacy_blacklist(cls, value: object) -> object:
        if not isinstance(value, dict) or "blacklist" not in value:
            return value
        data = dict(value)
        legacy_terms = data.pop("blacklist", [])
        current_terms = data.get("excluded_terms", [])
        current_terms = current_terms if isinstance(current_terms, list) else []
        legacy_terms = legacy_terms if isinstance(legacy_terms, list) else []
        data["excluded_terms"] = list(dict.fromkeys([
            term for term in [*current_terms, *legacy_terms] if isinstance(term, str)
        ]))
        return data


class PreferencesUpdate(BaseModel):
    tracking_rules: list[TrackingRule] = Field(default_factory=list)
    default_stores: list[str] | None = None


class TrackedItem(BaseModel):
    keyword: str
    label: str | None = None
    excluded_terms: list[str] = Field(default_factory=list)
    excluded_products: list[str] = Field(default_factory=list)
    temporary: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_blacklist(cls, value: object) -> object:
        if not isinstance(value, dict) or "blacklist" not in value:
            return value
        data = dict(value)
        legacy_terms = data.pop("blacklist", [])
        current_terms = data.get("excluded_terms", [])
        current_terms = current_terms if isinstance(current_terms, list) else []
        legacy_terms = legacy_terms if isinstance(legacy_terms, list) else []
        data["excluded_terms"] = list(dict.fromkeys([
            term for term in [*current_terms, *legacy_terms] if isinstance(term, str)
        ]))
        return data


class Offer(BaseModel):
    """One (product, shop) offer, flattened out of Kupi's grouped result."""

    product_name: str | None = None
    shop_raw: str  # shop name exactly as scraped, e.g. "Albert hypermarket"
    store_id: str | None = None  # our normalized ID, or None if unrecognized
    price: str | None = None  # raw display string, e.g. "29,90 Kč"
    amount: str | None = None  # raw display string, e.g. "10 ks"
    validity: str | None = None  # raw display string, e.g. "dnes končí"
    tracked_item: TrackedItem | str
    on_sale: bool = True
    temporary: bool = False
    tracking_rule_id: str | None = None
    image_url: str | None = None
    unit_price: float | None = None
    unit: str | None = None
    unit_price_label: str | None = None
    is_best_deal: bool = False
    confidence: Literal["high", "medium", "low"] = "high"
    match_reason: str | None = None
    suggested_exclusion_term: str | None = None


class ProductPreview(BaseModel):
    product_name: str
    confidence: Literal["high", "medium", "low"]
    match_reason: str | None = None
    suggested_exclusion_term: str | None = None


class RuleExclusionUpdate(BaseModel):
    type: Literal["term", "product"]
    value: str = Field(min_length=1, max_length=250)

    @field_validator("value")
    @classmethod
    def trim_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Exclusion value must not be blank.")
        return value


class OffersResponse(BaseModel):
    items: list[Offer]
    fetched_at: datetime
    errors: list[str] = Field(default_factory=list)
