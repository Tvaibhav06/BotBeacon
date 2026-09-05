"""
Decision Engine — §8.1.
Lives entirely in buyer-client/. NO backend imports.
Communicates with the Gateway only through the 5 MCP tools.

Steps (§8.1):
  1. Gemini: intent → structured filter {category, max_price, keywords}
  2. MCP search_catalog (deterministic, Gateway-side)
  3. Hybrid scoring: deterministic pre-filter + fit scoring
  4. Upsell selection from complement_categories
  5. Build the DecisionReceipt payload

Key invariants:
  - Merchant preferences (preferred_categories) influence RANKING only.
    They never override buyer budget/mandate constraints or eligibility.
  - Merchant cost/margin data is never received here (ProductPublic excludes it).
  - considered_count is the count BEFORE limit, not after.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from gemini_client import parse_intent, generate_why_bullets
from mcp_client import MCPClient


# ── Demo constants ─────────────────────────────────────────────────────────
MERCHANT_ID = "merchant_velocity_sports"
BUYER_ID = "demo-buyer-1"
MANDATE_ID = "mandate_demo_buyer_1"


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class ScoredProduct:
    product: dict
    score: float
    score_breakdown: dict = field(default_factory=dict)


@dataclass
class EngineResult:
    """Full output of the decision engine — used to build the DecisionReceipt."""
    intent: str
    structured_filter: dict
    considered_count: int
    selected: dict | None
    selected_score_breakdown: dict
    why: list[str]
    upsell: dict | None
    cart: dict | None
    policy_decision: dict | None
    transaction: dict | None


# ── Step 3: Hybrid Scoring ──────────────────────────────────────────────────

def _score_product(
    product: dict,
    keywords: list[str],
    max_price: float | None,
    preferred_categories: list[str],
    mandate_max: float,
) -> ScoredProduct:
    """
    Score a product for a buyer intent.
    Returns a ScoredProduct with a float score and a breakdown dict.

    Scoring components (§8.1):
      - keyword / tag fit with buyer intent
      - product suitability (name match quality)
      - availability (in-stock)
      - merchant preferred_categories as a ranking PREFERENCE (not a constraint)

    Hard eligibility (pre-filtered before scoring, but double-checked here):
      - price <= max_price (if set)
      - price <= mandate_max
      - stock > 0
    """
    score = 0.0
    breakdown: dict[str, Any] = {}

    price = product.get("price", 0.0)
    stock = product.get("stock", 0)
    name = product.get("name", "").lower()
    description = product.get("description", "").lower()
    tags: list[str] = [t.lower() for t in product.get("tags", [])]
    category = product.get("category", "").lower()

    # Hard eligibility checks
    # Note: mandate_max is used for price_efficiency scoring only — NOT as a hard block.
    # The mandate ceiling is enforced by the check_policy gate (mandate_check.py), not here.
    # Blocking at the engine level would prevent the "BLOCKED — Razorpay was never called"
    # demo scenario from ever reaching the gate.
    within_budget = (max_price is None or price <= max_price)
    in_stock = stock > 0
    breakdown["within_budget"] = within_budget
    breakdown["in_stock"] = in_stock

    if not within_budget or not in_stock:
        return ScoredProduct(product=product, score=-1.0, score_breakdown=breakdown)

    # Keyword fit — name + description + tags vs. parsed keywords
    kw_lower = [kw.lower() for kw in keywords]
    name_hits = sum(1 for kw in kw_lower if kw in name)
    desc_hits = sum(1 for kw in kw_lower if kw in description)
    tag_hits = sum(1 for kw in kw_lower if any(kw in t for t in tags))

    keyword_score = name_hits * 3 + tag_hits * 2 + desc_hits * 1
    breakdown["keyword_score"] = keyword_score
    breakdown["tag_score"] = tag_hits
    score += keyword_score

    # Suitability bonus: "running" in both name and tags → stronger signal
    if "running" in name and "running" in tags:
        score += 2
        breakdown["suitability_bonus"] = 2

    # Availability score: reward healthy stock
    avail_score = min(stock / 50.0, 1.0)  # caps at 1.0 for stock >= 50
    score += avail_score
    breakdown["availability_score"] = round(avail_score, 3)

    # Merchant preferred_categories ranking boost (preference, not constraint)
    preferred_bonus = 1.0 if category in [p.lower() for p in preferred_categories] else 0.0
    score += preferred_bonus
    breakdown["preferred_category"] = preferred_bonus > 0

    # Price efficiency: within budget, closer to mandate ceiling (but not over) → slight preference
    # This rewards "best value" without exceeding budget
    if mandate_max > 0:
        price_efficiency = price / mandate_max  # 0..1; higher = more of budget used = better value
        score += price_efficiency * 0.5
        breakdown["price_efficiency"] = round(price_efficiency, 3)

    return ScoredProduct(product=product, score=round(score, 4), score_breakdown=breakdown)


def _select_upsell(
    primary: dict,
    all_products: list[dict],
    mandate_headroom: float,
    preferred_categories: list[str],
) -> dict | None:
    """
    §8.1 step 4: If upsell_enabled and mandate has headroom after primary,
    pick the highest-price in-budget product whose category is in
    primary's complement_categories.
    """
    complement_cats = [c.lower() for c in primary.get("complement_categories", [])]
    if not complement_cats:
        return None

    candidates = [
        p for p in all_products
        if p["category"].lower() in complement_cats
        and p["price"] <= mandate_headroom
        and p["stock"] > 0
    ]

    if not candidates:
        return None

    # Highest-price eligible complement (§8.1 spec: "highest-price in-budget complement")
    return max(candidates, key=lambda p: p["price"])


# ── Main engine entry point ─────────────────────────────────────────────────

def run_decision_engine(
    intent: str,
    mcp: MCPClient,
    mandate_max_amount: float = 6000.0,
    mandate_category_scope: list[str] | None = None,
    upsell_enabled: bool = True,
    preferred_categories: list[str] | None = None,
) -> EngineResult:
    """
    Full §8.1 decision engine pipeline.

    Args:
        intent: Free-text buyer request
        mcp: MCPClient instance (no backend imports)
        mandate_max_amount: Buyer's spending limit
        mandate_category_scope: Allowed categories (empty = any)
        upsell_enabled: Whether merchant allows upsell
        preferred_categories: Merchant-preferred categories for ranking boost

    Returns:
        EngineResult with all data needed to build the DecisionReceipt
    """
    preferred_categories = preferred_categories or ["footwear", "accessories"]
    mandate_category_scope = mandate_category_scope or []

    print(f"\n[decision_engine] Intent: {intent!r}")

    # ── Step 1: Gemini intent → structured filter ──────────────────────────
    print("[decision_engine] Step 1: Gemini intent parsing...")
    structured_filter = parse_intent(intent)
    category = structured_filter.get("category")
    max_price = structured_filter.get("max_price")
    keywords = structured_filter.get("keywords", [])

    # Use Gemini's max_price directly for search — the mandate ceiling is enforced
    # by check_policy (mandate_check.py), not by the decision engine's pre-filter.
    # This allows "Buy the ₹8,999 version" to select prod_002 so the gate can block it.
    effective_max_price = max_price  # may be None (no upper bound from Gemini)

    print(f"[decision_engine]   filter: category={category}, max_price={max_price}, keywords={keywords}")

    # ── Step 2: MCP search_catalog (deterministic, Gateway-side) ──────────
    print("[decision_engine] Step 2: search_catalog via MCP...")
    search_result = mcp.search_catalog(
        query=" ".join(keywords) if keywords else intent,
        max_price=effective_max_price,
        category=category,
        limit=50,  # fetch more than needed; we score and rank locally
    )
    products: list[dict] = search_result.get("products", [])
    considered_count: int = search_result.get("considered_count", len(products))
    print(f"[decision_engine]   {considered_count} products considered, {len(products)} returned")

    if not products:
        print("[decision_engine] No products returned from catalog search")
        return EngineResult(
            intent=intent,
            structured_filter=structured_filter,
            considered_count=considered_count,
            selected=None,
            selected_score_breakdown={},
            why=["No products found matching intent"],
            upsell=None,
            cart=None,
            policy_decision=None,
            transaction=None,
        )

    # ── Step 3: Hybrid scoring ─────────────────────────────────────────────
    print("[decision_engine] Step 3: Hybrid scoring...")
    scored = [
        _score_product(
            product=p,
            keywords=keywords,
            max_price=effective_max_price,
            preferred_categories=preferred_categories,
            mandate_max=mandate_max_amount,
        )
        for p in products
    ]

    # Filter out ineligible products (score == -1)
    eligible = [s for s in scored if s.score >= 0]
    if not eligible:
        print("[decision_engine] No eligible products after scoring")
        return EngineResult(
            intent=intent,
            structured_filter=structured_filter,
            considered_count=considered_count,
            selected=None,
            selected_score_breakdown={},
            why=["No eligible products within budget"],
            upsell=None,
            cart=None,
            policy_decision=None,
            transaction=None,
        )

    # Sort by score descending; tiebreak: higher price preferred (better value)
    eligible.sort(key=lambda s: (s.score, s.product["price"]), reverse=True)
    best = eligible[0]
    selected = best.product
    print(f"[decision_engine]   Selected: {selected['name']} @ ₹{selected['price']} (score={best.score})")

    # ── Step 4: Upsell selection ──────────────────────────────────────────
    upsell_product: dict | None = None
    mandate_headroom = mandate_max_amount - selected["price"]

    if upsell_enabled and mandate_headroom > 0:
        print("[decision_engine] Step 4: Upsell selection...")
        # Search for complement category products (accessories)
        complement_cats = selected.get("complement_categories", [])
        if complement_cats:
            # Fetch accessories to find upsell candidates
            upsell_search = mcp.search_catalog(
                query="",
                category=complement_cats[0] if len(complement_cats) == 1 else None,
                max_price=mandate_headroom,
                limit=50,
            )
            all_candidates = upsell_search.get("products", [])
            upsell_product = _select_upsell(
                primary=selected,
                all_products=all_candidates,
                mandate_headroom=mandate_headroom,
                preferred_categories=preferred_categories,
            )
            if upsell_product:
                print(f"[decision_engine]   Upsell: {upsell_product['name']} @ ₹{upsell_product['price']}")

    # ── Step 5: "Why" bullet generation ───────────────────────────────────
    print("[decision_engine] Step 5: Why-bullet generation...")
    why_bullets = generate_why_bullets(
        intent=intent,
        selected_product=selected,
        score_breakdown=best.score_breakdown,
    )
    print(f"[decision_engine]   Why: {why_bullets}")

    return EngineResult(
        intent=intent,
        structured_filter=structured_filter,
        considered_count=considered_count,
        selected=selected,
        selected_score_breakdown=best.score_breakdown,
        why=why_bullets,
        upsell=upsell_product,
        cart=None,           # filled by scripted_buyer after engine returns
        policy_decision=None,
        transaction=None,
    )
