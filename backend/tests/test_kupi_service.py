import asyncio
import json

import pytest
from fastapi import HTTPException

from app.kupi_service import _flatten, _matches_rule, build_store_summaries, enrich_offer_insights, get_offers_for_items
from app.main import offers as offers_endpoint
from app.main import parse_tracked_items
from app.schemas import TrackingRule


def test_flatten_keeps_the_fields_from_the_same_shop_index():
    raw = json.dumps(
        [
            {
                "name": "Vejce M 10 ks",
                "shops": ["Lidl", "Albert hypermarket"],
                "prices": ["49,90 Kč", "29,90 Kč"],
                "amounts": ["10 ks", "10 ks"],
                "validities": ["do neděle", "dnes končí"],
                "image_urls": ["https://cdn.example.test/eggs.jpg"],
            }
        ]
    )

    offers = _flatten(raw, "vejce")

    assert offers[0]["shop_raw"] == "Lidl"
    assert offers[0]["price"] == "49,90 Kč"
    assert offers[0]["unit_price"] == 4.99
    assert offers[0]["unit_price_label"] == "4.99 Kč/ks"
    assert offers[0]["image_url"] == "https://cdn.example.test/eggs.jpg"
    assert offers[1]["shop_raw"] == "Albert hypermarket"
    assert offers[1]["unit_price"] == 2.99
    assert offers[1]["image_url"] == "https://cdn.example.test/eggs.jpg"


def test_cheaper_offer_has_no_tip_and_marks_more_expensive_offer(monkeypatch):
    monkeypatch.setattr("app.kupi_service.annotate_historical_bests", lambda _: None)
    offers = [
        {"tracked_item": "vejce", "shop_raw": "Lidl", "price": "49,90 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 4.99, "unit_price_label": "4.99 Kč/ks"},
        {"tracked_item": "vejce", "shop_raw": "Albert", "price": "29,90 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 2.99, "unit_price_label": "2.99 Kč/ks"},
    ]

    enriched = enrich_offer_insights(offers)

    assert enriched[1]["is_best_deal"] is True
    assert enriched[0]["better_deal"] == {
        "shop_name": "Albert",
        "price": "29,90 Kč",
        "amount": "10 ks",
        "unit_price_label": "2.99 Kč/ks",
    }


def test_store_summaries_use_distinct_covered_rules_not_raw_offer_count():
    summaries = build_store_summaries(
        [
            {"store_id": "albert", "shop_raw": "Albert", "tracked_item": "vejce", "tracking_rule_id": "eggs", "is_best_deal": True},
            {"store_id": "lidl", "shop_raw": "Lidl", "tracked_item": "vejce", "tracking_rule_id": "eggs", "is_best_deal": False},
            {"store_id": "lidl", "shop_raw": "Lidl", "tracked_item": "vejce", "tracking_rule_id": "eggs", "is_best_deal": False},
            {"store_id": "lidl", "shop_raw": "Lidl", "tracked_item": "banány", "tracking_rule_id": "bananas", "is_best_deal": True},
            {"store_id": "lidl", "shop_raw": "Lidl", "tracked_item": "brambory", "tracking_rule_id": "potatoes", "is_best_deal": True},
        ]
    )

    assert summaries[0]["id"] == "lidl"
    assert summaries[0]["coverage_count"] == 3
    assert summaries[0]["best_deal_count"] == 2
    assert summaries[0]["is_recommended"] is True


def test_endpoint_serializes_insights_and_top_hits(monkeypatch):
    async def fake_get_offers(*_):
        return [
            {
                "product_name": "Vejce M",
                "shop_raw": "Lidl",
                "store_id": "lidl",
                "price": "29,90 Kč",
                "amount": "10 ks",
                "tracked_item": "vejce",
                "unit_price": 2.99,
                "unit": "ks",
                "unit_price_label": "2.99 Kč/ks",
                "is_best_deal": True,
                "is_historical_best": True,
                "better_deal": None,
            }
        ], []

    monkeypatch.setattr("app.main.get_offers_for_rules", fake_get_offers)
    response = asyncio.run(offers_endpoint(items="vejce", rules=None, stores=""))

    assert response["top_hits"][0].unit_price_label == "2.99 Kč/ks"
    assert response["store_summaries"][0].is_recommended is True


def test_offers_are_filtered_by_the_selected_store(monkeypatch):
    monkeypatch.setattr(
        "app.kupi_service._fetch_one_sync",
        lambda _: [
            {"store_id": "lidl", "shop_raw": "Lidl", "product_name": "Vejce M"},
            {"store_id": "albert", "shop_raw": "Albert", "product_name": "Vejce M"},
        ],
    )

    offers, errors = asyncio.run(get_offers_for_items(["vejce"], {"lidl"}))

    assert errors == []
    assert len(offers) == 1
    assert offers[0]["store_id"] == "lidl"


def test_empty_store_filter_means_all_stores(monkeypatch):
    monkeypatch.setattr(
        "app.kupi_service._fetch_one_sync",
        lambda _: [{"store_id": "lidl", "shop_raw": "Lidl", "product_name": "Vejce M"}, {"store_id": "albert", "shop_raw": "Albert", "product_name": "Vejce M"}],
    )

    offers, _ = asyncio.run(get_offers_for_items(["vejce"], None))

    assert len(offers) == 2


def test_broad_rule_excludes_aspic_but_keeps_ordinary_eggs():
    rule = TrackingRule(id="eggs", query="vejce", label="Vejce", excluded_terms=["aspik"])

    assert _matches_rule("Bio vejce M 10 ks", rule) is True
    assert _matches_rule("Vejce v aspiku", rule) is False


def test_exact_rule_uses_product_phrase_not_a_fragile_full_string_match():
    rule = TrackingRule(id="eggs-m", query="vejce", label="Vejce M", match_mode="exact", exact_product_name="Vejce M")

    assert _matches_rule("Bio Vejce M 10 ks", rule) is True
    assert _matches_rule("Vejce L 10 ks", rule) is False


def test_same_shop_variants_do_not_recommend_the_same_shop(monkeypatch):
    monkeypatch.setattr("app.kupi_service.annotate_historical_bests", lambda _: None)
    offers = [
        {"tracked_item": "vejce", "tracking_rule_id": "eggs", "shop_raw": "Lidl", "price": "30 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 3.0, "unit_price_label": "3.00 Kč/ks"},
        {"tracked_item": "vejce", "tracking_rule_id": "eggs", "shop_raw": "Lidl", "price": "40 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 4.0, "unit_price_label": "4.00 Kč/ks"},
        {"tracked_item": "vejce", "tracking_rule_id": "eggs", "shop_raw": "Albert", "price": "35 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 3.5, "unit_price_label": "3.50 Kč/ks"},
    ]

    enriched = enrich_offer_insights(offers)

    assert enriched[1]["better_deal"] is None
    assert enriched[2]["better_deal"]["shop_name"] == "Lidl"


def test_tracked_items_are_limited_to_twenty():
    parsed = parse_tracked_items(",".join(f"položka {index}" for index in range(20)))
    assert len(parsed) == 20

    with pytest.raises(HTTPException, match="nejvýše 20"):
        parse_tracked_items(",".join(f"položka {index}" for index in range(21)))
