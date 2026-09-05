"""
Phase 3 tests — Decision Engine unit tests (§14, §11).
All tests run without a live backend or Gemini API key.
MCP calls are mocked; Gemini falls back to the deterministic heuristic.

Key DoD assertions (§12 Phase 3):
  - "Find me running shoes under ₹6,000" → selects prod_001 + prod_006 upsell
  - considered_count is threaded correctly
  - Upsell selection uses complement_categories + mandate headroom
  - Score ordering is deterministic and matches §11's expected outcome
"""
from __future__ import annotations

import sys
import os

# Add buyer-client to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "buyer-client"))

import pytest
from unittest.mock import MagicMock, patch

from decision_engine import (
    run_decision_engine,
    _score_product,
    _select_upsell,
    ScoredProduct,
)
from gemini_client import _parse_intent_heuristic, _generate_why_deterministic


# ── Seed product fixtures (§11) ────────────────────────────────────────────

def _p(id, name, category, price, stock, tags=None, complement_categories=None, description=""):
    return {
        "id": id, "name": name, "category": category, "price": price, "stock": stock,
        "tags": tags or [], "complement_categories": complement_categories or [],
        "description": description,
    }

SEED_PRODUCTS_FOOTWEAR = [
    _p("prod_001", "Velocity Pro",          "footwear", 5499, 40, ["running","men","performance"], ["accessories"], "High-performance running shoe"),
    _p("prod_002", "Velocity Pro (Premium)","footwear", 8999, 15, ["running","men","premium"],     ["accessories"], "Premium edition with carbon-fibre"),
    _p("prod_003", "Trail Runner X",        "footwear", 4999, 25, ["trail","running","unisex"],    ["accessories"], "Aggressive outsole for off-road"),
    _p("prod_004", "Court Classic",         "footwear", 3499, 60, ["court","casual","unisex"],     ["accessories"], "Clean silhouette for court"),
    _p("prod_005", "Everyday Sneaker",      "footwear", 2999, 80, ["casual","unisex","everyday"],  ["accessories"], "Lightweight everyday trainer"),
]

SEED_PRODUCTS_ACCESSORIES = [
    _p("prod_006", "Performance Socks (2-pack)", "accessories", 499,  200, ["socks","running","unisex"], [], "Moisture-wicking running socks"),
    _p("prod_007", "Cushion Insoles",            "accessories", 699,  90,  ["insoles","comfort","unisex"], [], "Gel-cushion insoles"),
    _p("prod_008", "Running Cap",                "accessories", 599,  70,  ["cap","running","unisex"],  [], "Lightweight reflective cap"),
]

ALL_SEED_PRODUCTS = SEED_PRODUCTS_FOOTWEAR + SEED_PRODUCTS_ACCESSORIES


# ── Heuristic intent parsing ───────────────────────────────────────────────

class TestIntentParsing:

    def test_running_shoes_under_6000(self):
        result = _parse_intent_heuristic("Find me running shoes under 6000")
        assert result["category"] == "footwear"
        assert result["max_price"] == 6000.0
        assert "running" in result["keywords"]

    def test_premium_version_8999(self):
        result = _parse_intent_heuristic("Buy the 8999 version instead")
        # Should NOT return 6000 as max_price — it's not specified as a ceiling
        assert result["max_price"] == 8999.0 or result["max_price"] is None

    def test_accessories_intent(self):
        result = _parse_intent_heuristic("Get me some running socks")
        assert result["category"] == "accessories"

    def test_price_extraction_inr_symbol(self):
        result = _parse_intent_heuristic("I want shoes under ₹5,000")
        assert result["max_price"] == 5000.0

    def test_no_price_returns_none(self):
        result = _parse_intent_heuristic("Find me good running shoes")
        assert result["max_price"] is None or isinstance(result["max_price"], float)

    def test_keywords_filtered(self):
        result = _parse_intent_heuristic("Find me running shoes")
        assert "find" not in result["keywords"]
        assert "me" not in result["keywords"]
        assert "running" in result["keywords"]


# ── Scoring ────────────────────────────────────────────────────────────────

class TestScoring:

    PREFERRED = ["footwear", "accessories"]
    MANDATE_MAX = 6000.0

    def test_prod_001_scores_higher_than_prod_003(self):
        """
        §11 DoD: prod_001 (Velocity Pro) must rank above prod_003 (Trail Runner X)
        for intent "running shoes".
        Velocity Pro: tags=["running","men","performance"], name has "running" concept
        Trail Runner X: tags=["trail","running","unisex"], name has "trail" not "running"
        """
        keywords = ["running", "shoes"]
        s001 = _score_product(SEED_PRODUCTS_FOOTWEAR[0], keywords, 6000, self.PREFERRED, 6000)
        s003 = _score_product(SEED_PRODUCTS_FOOTWEAR[2], keywords, 6000, self.PREFERRED, 6000)
        assert s001.score > s003.score, (
            f"prod_001 score {s001.score} should beat prod_003 score {s003.score}"
        )

    def test_over_budget_product_gets_negative_score(self):
        """prod_002 (₹8,999) must be ineligible when max_price=6000"""
        s = _score_product(SEED_PRODUCTS_FOOTWEAR[1], ["running"], 6000, self.PREFERRED, 6000)
        assert s.score < 0, f"prod_002 should be ineligible but got score {s.score}"

    def test_zero_stock_gets_negative_score(self):
        p = _p("test", "Out of stock shoe", "footwear", 3000, 0, ["running"])
        s = _score_product(p, ["running"], 6000, self.PREFERRED, 6000)
        assert s.score < 0

    def test_preferred_category_gives_bonus(self):
        in_preferred = _p("a", "Running Shoe", "footwear", 3000, 10, ["running"])
        not_preferred = _p("b", "Running Shoe", "electronics", 3000, 10, ["running"])
        s_pref = _score_product(in_preferred, ["running"], 6000, ["footwear"], 6000)
        s_notpref = _score_product(not_preferred, ["running"], 6000, ["footwear"], 6000)
        assert s_pref.score > s_notpref.score

    def test_score_breakdown_has_required_keys(self):
        s = _score_product(SEED_PRODUCTS_FOOTWEAR[0], ["running"], 6000, self.PREFERRED, 6000)
        assert "within_budget" in s.score_breakdown
        assert "in_stock" in s.score_breakdown
        assert "keyword_score" in s.score_breakdown


# ── Upsell selection ───────────────────────────────────────────────────────

class TestUpsellSelection:

    def test_selects_highest_price_complement(self):
        """
        §8.1 step 4: upsell = highest-price complement within mandate headroom.
        prod_001 selected (₹5499), mandate ₹6000 → headroom ₹501.
        prod_006 (₹499) fits, prod_007 (₹699) does NOT fit.
        prod_008 (₹599) does NOT fit.
        → Expected: prod_006 (₹499, highest fitting)
        """
        primary = SEED_PRODUCTS_FOOTWEAR[0]  # prod_001, price=5499
        headroom = 6000.0 - primary["price"]  # 501.0
        all_products = SEED_PRODUCTS_ACCESSORIES

        upsell = _select_upsell(
            primary=primary,
            all_products=all_products,
            mandate_headroom=headroom,
            preferred_categories=["accessories"],
        )
        assert upsell is not None, "Expected an upsell candidate"
        assert upsell["id"] == "prod_006", (
            f"Expected prod_006 (Performance Socks, ₹499) but got {upsell['id']} ({upsell['name']}, ₹{upsell['price']})"
        )

    def test_no_upsell_when_no_headroom(self):
        primary = _p("px", "Expensive Shoe", "footwear", 6000, 10, [], ["accessories"])
        headroom = 0.0
        upsell = _select_upsell(primary, SEED_PRODUCTS_ACCESSORIES, headroom, ["accessories"])
        assert upsell is None

    def test_no_upsell_when_no_complement_categories(self):
        primary = _p("px", "Shoe", "footwear", 3000, 10, [], complement_categories=[])
        upsell = _select_upsell(primary, SEED_PRODUCTS_ACCESSORIES, 3000.0, ["accessories"])
        assert upsell is None

    def test_upsell_respects_headroom(self):
        """prod_007 (₹699) should not be selected when headroom < 699"""
        primary = SEED_PRODUCTS_FOOTWEAR[0]  # prod_001 ₹5499 → headroom ₹501
        upsell = _select_upsell(
            primary=primary,
            all_products=[SEED_PRODUCTS_ACCESSORIES[1]],  # only prod_007 ₹699
            mandate_headroom=501.0,
            preferred_categories=["accessories"],
        )
        assert upsell is None, "prod_007 (₹699) should not fit in ₹501 headroom"


# ── Full engine — DoD test (§12 Phase 3) ──────────────────────────────────

class TestDecisionEngineDoD:
    """
    THE Phase 3 Definition of Done tests.
    Mocks MCP calls; Gemini falls back to heuristic (no API key).
    """

    def _make_mock_mcp(self, footwear_products, accessory_products, considered_count=18):
        mcp = MagicMock()

        def search_catalog_side_effect(query="", max_price=None, category=None, limit=20):
            if category == "accessories" or (category is None and max_price and max_price < 1000):
                # Upsell search — return accessories
                eligible = [p for p in accessory_products if max_price is None or p["price"] <= max_price]
                return {"products": eligible, "considered_count": len(eligible)}
            else:
                # Primary search — return footwear within budget
                eligible = [p for p in footwear_products if max_price is None or p["price"] <= max_price]
                return {"products": eligible, "considered_count": considered_count}

        mcp.search_catalog.side_effect = search_catalog_side_effect
        return mcp

    def test_happy_path_selects_prod_001_with_prod_006_upsell(self):
        """
        §12 Phase 3 DoD:
        "Find me running shoes under ₹6,000" → prod_001 + prod_006 upsell.
        This is the exact §11 demo scenario 1.
        """
        mcp = self._make_mock_mcp(
            footwear_products=SEED_PRODUCTS_FOOTWEAR,
            accessory_products=SEED_PRODUCTS_ACCESSORIES,
            considered_count=18,
        )

        result = run_decision_engine(
            intent="Find me running shoes under 6000",
            mcp=mcp,
            mandate_max_amount=6000.0,
            mandate_category_scope=["footwear", "accessories"],
            upsell_enabled=True,
            preferred_categories=["footwear", "accessories"],
        )

        assert result.selected is not None, "Expected a product to be selected"
        assert result.selected["id"] == "prod_001", (
            f"Expected prod_001 (Velocity Pro) but got {result.selected['id']} ({result.selected['name']})"
        )
        assert result.upsell is not None, "Expected an upsell to be selected"
        assert result.upsell["id"] == "prod_006", (
            f"Expected prod_006 (Performance Socks) but got {result.upsell['id']} ({result.upsell['name']})"
        )
        assert result.considered_count == 18, f"Expected 18 considered, got {result.considered_count}"
        assert len(result.why) > 0, "Expected why bullets"

    def test_considered_count_threaded_correctly(self):
        """considered_count must be the total before limit, not the returned count."""
        mcp = self._make_mock_mcp(SEED_PRODUCTS_FOOTWEAR, SEED_PRODUCTS_ACCESSORIES, considered_count=18)
        result = run_decision_engine(
            intent="running shoes",
            mcp=mcp,
            mandate_max_amount=6000.0,
        )
        assert result.considered_count == 18

    def test_over_budget_product_not_selected(self):
        """
        §11 demo scenario 2: "Buy the 8999 version instead"
        prod_002 (₹8999) exceeds mandate max ₹6000 → should not be selected by engine.
        The engine caps max_price at mandate_max_amount.
        """
        mcp = self._make_mock_mcp(
            footwear_products=SEED_PRODUCTS_FOOTWEAR,
            accessory_products=SEED_PRODUCTS_ACCESSORIES,
        )

        result = run_decision_engine(
            intent="Buy the 8999 version instead",
            mcp=mcp,
            mandate_max_amount=6000.0,
            upsell_enabled=False,
        )

        # The engine must not select prod_002 (₹8999 > ₹6000 mandate)
        if result.selected:
            assert result.selected["price"] <= 6000.0, (
                f"Engine should not select a product above mandate limit. "
                f"Got {result.selected['id']} at ₹{result.selected['price']}"
            )

    def test_no_upsell_when_disabled(self):
        mcp = self._make_mock_mcp(SEED_PRODUCTS_FOOTWEAR, SEED_PRODUCTS_ACCESSORIES)
        result = run_decision_engine(
            intent="Find me running shoes under 6000",
            mcp=mcp,
            mandate_max_amount=6000.0,
            upsell_enabled=False,
        )
        assert result.upsell is None

    def test_why_bullets_populated(self):
        mcp = self._make_mock_mcp(SEED_PRODUCTS_FOOTWEAR, SEED_PRODUCTS_ACCESSORIES)
        result = run_decision_engine(
            intent="Find me running shoes under 6000",
            mcp=mcp,
            mandate_max_amount=6000.0,
        )
        assert isinstance(result.why, list)
        assert len(result.why) >= 1


# ── Why bullet generation ──────────────────────────────────────────────────

class TestWhyBullets:

    def test_deterministic_bullets_include_stock_and_budget(self):
        breakdown = {"in_stock": True, "within_budget": True, "keyword_score": 3, "tag_score": 2}
        bullets = _generate_why_deterministic(breakdown)
        assert "In stock" in bullets
        assert "Within budget" in bullets

    def test_best_fit_when_keyword_score_positive(self):
        breakdown = {"in_stock": True, "within_budget": True, "keyword_score": 2, "tag_score": 1}
        bullets = _generate_why_deterministic(breakdown)
        assert "Best fit for intent" in bullets

    def test_fallback_when_no_breakdown(self):
        bullets = _generate_why_deterministic({})
        assert len(bullets) >= 1
