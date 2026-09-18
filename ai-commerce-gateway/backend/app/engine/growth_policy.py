"""
Deterministic Growth Policy Gate — §6.4 and §8.3.

A pure function: no database calls, no network, no LLM, no side-effects.
The sole authority on whether an AI-proposed growth action may proceed.

Outcomes:
  - BLOCKED:           hard stop; rule violation; no merchant approval path
  - REQUIRES_APPROVAL: within rule boundaries but above approval threshold (or threshold is None)
  - ALLOWED:           fully within limits and under threshold; autonomous execution

Formulas (§8.3):
  - combined_regular_price = sum(p.price for p in products)
  - combined_cost          = sum(p.cost for p in products)
  - discount_factor        = discount_pct / 100.0 if discount_pct > 1.0 else discount_pct
  - discounted_price       = combined_regular_price * (1.0 - discount_factor)
  - resulting_margin_pct   = (discounted_price - combined_cost) / discounted_price * 100.0
  - estimated_discount_exposure = weekly_units * campaign_duration_weeks * combined_regular_price * discount_factor
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence, Union


# Canonical outcome constants
BLOCKED = "blocked"
REQUIRES_APPROVAL = "requires_approval"
ALLOWED = "allowed"

PolicyOutcome = Literal["blocked", "requires_approval", "allowed"]


@dataclass
class ProductForGrowthGate:
    """Product details evaluated by the growth policy gate."""
    id: str
    price: float
    cost: float
    stock: int
    status: str = "active"


@dataclass
class ActionForGrowthGate:
    """Proposed growth action to be evaluated."""
    type: str = "discount_bundle"
    discount_pct: float = 0.0
    campaign_duration_weeks: int = 1
    estimated_discount_exposure: float = 0.0
    products: list[ProductForGrowthGate] = field(default_factory=list)
    audience: str = "configured_demo_audience"


@dataclass
class MerchantRulesForGrowthGate:
    """Merchant rules used for growth policy evaluation."""
    growth_actions_enabled: bool = False
    max_ai_discount_pct: float = 0.0
    min_margin_pct: float = 10.0
    growth_approval_threshold_amount: float | None = None  # None = always require approval


def calculate_discount_exposure(
    weekly_units: float,
    campaign_duration_weeks: int,
    products: Sequence[ProductForGrowthGate],
    discount_pct: float,
) -> float:
    """
    Calculate estimated discount exposure (§8.3):
      avg_recent_weekly_units_sold(primary_product)
      × campaign_duration_weeks
      × combined_regular_price_of_all_discounted_products_in_the_bundle
      × discount_pct
    """
    if weekly_units <= 0 or campaign_duration_weeks <= 0 or discount_pct <= 0:
        return 0.0

    regular_price_sum = sum(p.price for p in products)
    discount_factor = discount_pct / 100.0 if discount_pct > 1.0 else discount_pct
    exposure = weekly_units * campaign_duration_weeks * regular_price_sum * discount_factor
    return round(float(exposure), 2)


def calculate_bundle_margin(
    products: Sequence[ProductForGrowthGate],
    discount_pct: float,
) -> float:
    """
    Calculate resulting bundle margin % on selling price (§8.3):
      combined_discounted_price = (regular_price_sum) × (1 − discount_pct)
      resulting_margin_pct = (combined_discounted_price − combined_cost) / combined_discounted_price × 100
    """
    regular_price_sum = sum(p.price for p in products)
    cost_sum = sum(p.cost for p in products)

    if regular_price_sum <= 0:
        return 0.0

    discount_factor = discount_pct / 100.0 if discount_pct > 1.0 else discount_pct
    discounted_price = regular_price_sum * (1.0 - discount_factor)

    if discounted_price <= 0:
        return 0.0

    margin_pct = (discounted_price - cost_sum) / discounted_price * 100.0
    return round(float(margin_pct), 2)


def growth_policy_gate(
    action: ActionForGrowthGate,
    rules: MerchantRulesForGrowthGate,
) -> tuple[PolicyOutcome, list[str]]:
    """
    Pure deterministic evaluation of a proposed growth action against merchant rules (§6.4).

    Returns:
        (outcome, reasons)
        - outcome: 'blocked' | 'requires_approval' | 'allowed'
        - reasons: list of explanatory strings explaining the outcome
    """
    reasons: list[str] = []

    # ── Check 1: Feature opt-in ──────────────────────────────────────────
    # growth_actions_enabled must be explicitly True (opt-in safe default)
    if not rules.growth_actions_enabled:
        reasons.append("growth actions are disabled in merchant rules")

    # ── Check 2: Target products validity and stock ──────────────────────
    if not action.products:
        reasons.append("no target products specified for growth action")
    else:
        for p in action.products:
            if p.status != "active":
                reasons.append(f"target product '{p.id}' is inactive")
            if p.stock <= 0:
                reasons.append(f"target product '{p.id}' is out of stock (stock: {p.stock})")

    # ── Check 3: Maximum discount ceiling ────────────────────────────────
    # Any requested discount % > max_ai_discount_pct is BLOCKED
    if action.discount_pct > rules.max_ai_discount_pct:
        reasons.append(
            f"requested discount {action.discount_pct:.1f}% exceeds maximum allowed "
            f"{rules.max_ai_discount_pct:.1f}%"
        )

    # ── Check 4: Minimum margin floor ────────────────────────────────────
    # Resulting bundle margin % must satisfy min_margin_pct
    if action.products:
        bundle_margin = calculate_bundle_margin(action.products, action.discount_pct)
        if bundle_margin < rules.min_margin_pct:
            reasons.append(
                f"resulting bundle margin {bundle_margin:.1f}% is below minimum floor "
                f"{rules.min_margin_pct:.1f}%"
            )

    # If any hard constraint failed, action is BLOCKED. No approval path.
    if reasons:
        return BLOCKED, reasons

    # ── Check 5: Human approval threshold ────────────────────────────────
    # If rules.growth_approval_threshold_amount is None:
    # safe default means "always require approval" (§6.4, §8.2)
    if rules.growth_approval_threshold_amount is None:
        return REQUIRES_APPROVAL, ["merchant approval required (no autonomous threshold configured)"]

    # If estimated_discount_exposure > threshold, requires merchant approval
    if action.estimated_discount_exposure > rules.growth_approval_threshold_amount:
        return REQUIRES_APPROVAL, [
            f"estimated discount exposure ₹{action.estimated_discount_exposure:,.2f} "
            f"exceeds autonomous approval threshold ₹{rules.growth_approval_threshold_amount:,.2f}"
        ]

    # ── Check 6: Autonomous execution permitted ──────────────────────────
    # When fully within rules and exposure <= threshold
    return ALLOWED, []
