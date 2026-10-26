import asyncio
import json

import pytest
from fastapi import HTTPException

from app.config import MAX_TRACKED_ITEMS
from app import kupi_service
from app.kupi_service import _flatten, _matches_rule, enrich_offer_insights, get_offers_for_rules
from app.main import exclude_from_rule, offers as offers_endpoint, set_preferences
from app.main import parse_tracked_items
from app.product_matching import score_product
from app.schemas import PreferencesUpdate, RuleExclusionUpdate, TrackedItem, TrackingRule


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


def test_kupi_page_parser_extracts_offer_data_and_lazy_image_url():
    html = """
    <div class="group_discounts">
      <div class="product_image">
        <img src="/img/no_img/no_discounts.png"
             data-src="https://img.kupi.cz/kupi/thumbs/vejce-m_170_340.jpg">
      </div>
      <div class="product_name"><strong>Vejce M</strong></div>
      <div class="discounts_table">
        <span class="discounts_shop_name">Lidl</span>
        <div class="discount_row">
          <span class="discount_price_value">29,90 Kč</span>
          <span class="discount_amount">10 ks</span>
          <div class="discounts_validity">do neděle</div>
        </div>
      </div>
    </div>
    """

    products = kupi_service._parse_search_page(html)

    assert products == [{
        "name": "Vejce M",
        "shops": ["Lidl"],
        "prices": ["29,90 Kč"],
        "amounts": ["10 ks"],
        "validities": ["do neděle"],
        "image_url": "https://img.kupi.cz/kupi/thumbs/vejce-m_170_340.jpg",
    }]


def test_kupi_page_parser_ignores_placeholder_and_untrusted_image_urls():
    html = """
    <div class="group_discounts">
      <div class="product_image"><img src="/img/no_img/no_discounts.png"></div>
      <div class="product_name"><strong>Vejce M</strong></div>
      <div class="discounts_table"><span class="discounts_shop_name">Lidl</span></div>
    </div>
    <div class="group_discounts">
      <div class="product_image"><img data-src="https://other.example/image.jpg"></div>
      <div class="product_name"><strong>Vejce L</strong></div>
      <div class="discounts_table"><span class="discounts_shop_name">Albert</span></div>
    </div>
    """

    products = kupi_service._parse_search_page(html)

    assert [product["image_url"] for product in products] == [None, None]


def test_fetch_one_sync_attaches_kupi_image_from_the_same_page_response(monkeypatch):
    html = """
    <div class="group_discounts">
      <div class="product_image"><img src="/img/no_img/no_discounts.png"
           data-src="https://img.kupi.cz/kupi/thumbs/vejce-m_170_340.jpg"></div>
      <div class="product_name"><strong>Vejce M</strong></div>
      <div class="discounts_table">
        <span class="discounts_shop_name">Lidl</span>
        <div class="discount_row"><span class="discount_price_value">29,90 Kč</span>
          <span class="discount_amount">10 ks</span></div>
      </div>
    </div>
    """

    class Response:
        status_code = 200

        def __init__(self, content):
            self.content = content

    responses = iter([Response(html), Response(b"")])
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs["params"]))
        return next(responses)

    monkeypatch.setattr(kupi_service, "_cache", {})
    monkeypatch.setattr(kupi_service.requests, "get", fake_get)

    offers = kupi_service._fetch_one_sync("vejce")

    assert offers[0]["product_name"] == "Vejce M"
    assert offers[0]["image_url"] == "https://img.kupi.cz/kupi/thumbs/vejce-m_170_340.jpg"
    assert calls == [
        (kupi_service.KUPI_SEARCH_URL, {"f": "vejce", "vse": "0"}),
        (kupi_service.KUPI_SEARCH_URL, {"f": "vejce", "vse": "0", "page": "2"}),
    ]


def test_cheapest_unit_price_is_marked_for_each_tracking_rule(monkeypatch):
    offers = [
        {"tracked_item": "vejce", "shop_raw": "Lidl", "price": "49,90 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 4.99, "unit_price_label": "4.99 Kč/ks"},
        {"tracked_item": "vejce", "shop_raw": "Albert", "price": "29,90 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 2.99, "unit_price_label": "2.99 Kč/ks"},
    ]

    enriched = enrich_offer_insights(offers)

    assert enriched[1]["is_best_deal"] is True
    assert enriched[0]["is_best_deal"] is False
    assert enriched[1]["is_best_deal"] is True


def test_endpoint_serializes_offer_items(monkeypatch):
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
            }
        ], []

    monkeypatch.setattr("app.main.get_offers_for_rules", fake_get_offers)
    response = asyncio.run(offers_endpoint(items="vejce", rules=None, stores=""))

    assert response["items"][0].unit_price_label == "2.99 Kč/ks"
    assert response["items"][0].is_best_deal is True


def test_preferences_are_saved_without_touching_project_data(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.Path", lambda *_: tmp_path / "main.py")
    preferences = PreferencesUpdate(
        tracking_rules=[TrackingRule(id="eggs", query="vejce", label="Vejce")],
        default_stores=["lidl"],
    )

    assert set_preferences(preferences) == {"ok": True}
    saved = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert saved["tracking_rules"][0]["query"] == "vejce"
    assert saved["default_stores"] == ["lidl"]


def test_preferences_write_failure_is_an_http_error(monkeypatch):
    class UnwritablePath:
        @property
        def parent(self):
            return self

        def __truediv__(self, _):
            return self

        def write_text(self, *_args, **_kwargs):
            raise OSError("read only")

    monkeypatch.setattr("app.main.Path", lambda *_: UnwritablePath())
    preferences = PreferencesUpdate(tracking_rules=[], default_stores=[])

    with pytest.raises(HTTPException) as error:
        set_preferences(preferences)

    assert error.value.status_code == 500


def test_offers_are_filtered_by_the_selected_store(monkeypatch):
    monkeypatch.setattr(
        "app.kupi_service._fetch_one_sync",
        lambda _: [
            {"store_id": "lidl", "shop_raw": "Lidl", "product_name": "Vejce M"},
            {"store_id": "albert", "shop_raw": "Albert", "product_name": "Vejce M"},
        ],
    )

    rule = TrackingRule(id="eggs", query="vejce", label="vejce")
    offers, errors = asyncio.run(get_offers_for_rules([rule], {"lidl"}))

    assert errors == []
    assert len(offers) == 1
    assert offers[0]["store_id"] == "lidl"


def test_empty_store_filter_means_all_stores(monkeypatch):
    monkeypatch.setattr(
        "app.kupi_service._fetch_one_sync",
        lambda _: [{"store_id": "lidl", "shop_raw": "Lidl", "product_name": "Vejce M"}, {"store_id": "albert", "shop_raw": "Albert", "product_name": "Vejce M"}],
    )

    rule = TrackingRule(id="eggs", query="vejce", label="vejce")
    offers, _ = asyncio.run(get_offers_for_rules([rule], None))

    assert len(offers) == 2


def test_broad_rule_excludes_aspic_but_keeps_ordinary_eggs():
    rule = TrackingRule(id="eggs", query="vejce", label="Vejce", excluded_terms=["aspik"])

    assert _matches_rule("Bio vejce M 10 ks", rule) is True
    assert _matches_rule("Vejce v aspiku", rule) is False


def test_exact_rule_uses_product_phrase_not_a_fragile_full_string_match():
    rule = TrackingRule(id="eggs-m", query="vejce", label="Vejce M", match_mode="exact", exact_product_name="Vejce M")

    assert _matches_rule("Bio Vejce M 10 ks", rule) is True
    assert _matches_rule("Vejce L 10 ks", rule) is False


def test_smart_matching_scores_expected_czech_meat_examples():
    good_match = score_product("kuřecí maso", "Kuřecí prsní řízky 500g")
    uncertain_match = score_product("kuřecí maso", "Kuřecí párky jemné 400g")

    assert good_match["confidence"] == "high"
    assert good_match["match_reason"] is None
    assert uncertain_match["confidence"] == "medium"
    assert uncertain_match["suggested_exclusion_term"] == "párek"
    assert "párek" in uncertain_match["match_reason"]


def test_smart_matching_hides_unrelated_kupi_spillover():
    assert score_product("kuřecí maso", "Vejce M 10 ks")["confidence"] == "none"


def test_unrecognized_extra_word_is_not_reported_as_a_certain_match():
    match = score_product("kuřecí maso", "Kuřecí maso pizza")

    assert match["confidence"] == "medium"
    assert match["suggested_exclusion_term"] is None
    assert "pizza" in match["match_reason"]


def test_exact_product_exclusion_keeps_other_package_sizes_visible():
    rule = TrackingRule(
        id="sausages",
        query="kuřecí maso",
        label="kuřecí maso",
        excluded_products=["Kuřecí párky Striptýz 400g"],
    )

    assert _matches_rule("Kuřecí párky Striptýz 400g", rule) is False
    assert _matches_rule("Kuřecí párky Striptýz 300g", rule) is True


def test_blacklist_migration_merges_and_deduplicates_both_exclusion_fields():
    rule = TrackingRule.model_validate({
        "id": "meat",
        "query": "kuřecí maso",
        "label": "kuřecí maso",
        "match_mode": "broad",
        "excluded_terms": ["párek"],
        "blacklist": ["párek", "játra"],
    })
    item = TrackedItem.model_validate({
        "keyword": "kuřecí maso",
        "excluded_terms": ["párek"],
        "blacklist": ["párek", "játra"],
    })

    assert rule.match_mode == "smart"
    assert rule.excluded_terms == ["párek", "játra"]
    assert item.excluded_terms == ["párek", "játra"]


def test_rule_exclusion_endpoint_saves_one_deduplicated_exclusion(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.Path", lambda *_: tmp_path / "main.py")
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({
        "tracking_rules": [{"id": "meat", "query": "kuřecí maso", "label": "kuřecí maso"}],
        "default_stores": ["lidl"],
    }), encoding="utf-8")

    update = RuleExclusionUpdate(type="term", value="párek")
    first = exclude_from_rule("meat", update)
    second = exclude_from_rule("meat", update)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert first["tracking_rule"]["excluded_terms"] == ["párek"]
    assert second["tracking_rule"]["excluded_terms"] == ["párek"]
    assert saved["default_stores"] == ["lidl"]


def test_best_deal_ignores_more_expensive_package_variants_in_same_shop():
    offers = [
        {"tracked_item": "vejce", "tracking_rule_id": "eggs", "shop_raw": "Lidl", "price": "30 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 3.0, "unit_price_label": "3.00 Kč/ks"},
        {"tracked_item": "vejce", "tracking_rule_id": "eggs", "shop_raw": "Lidl", "price": "40 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 4.0, "unit_price_label": "4.00 Kč/ks"},
        {"tracked_item": "vejce", "tracking_rule_id": "eggs", "shop_raw": "Albert", "price": "35 Kč", "amount": "10 ks", "unit": "ks", "unit_price": 3.5, "unit_price_label": "3.50 Kč/ks"},
    ]

    enriched = enrich_offer_insights(offers)

    assert enriched[0]["is_best_deal"] is True
    assert enriched[1]["is_best_deal"] is False
    assert enriched[2]["is_best_deal"] is False


def test_tracked_items_match_the_configured_limit():
    parsed = parse_tracked_items(",".join(f"položka {index}" for index in range(MAX_TRACKED_ITEMS)))
    assert len(parsed) == MAX_TRACKED_ITEMS

    with pytest.raises(HTTPException):
        parse_tracked_items(",".join(f"položka {index}" for index in range(MAX_TRACKED_ITEMS + 1)))
