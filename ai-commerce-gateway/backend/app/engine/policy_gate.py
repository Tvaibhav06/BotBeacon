"""
Policy Gate — §8.3.
Deterministic merchant-side rule enforcement.

Checks (in order):
  1. Stock:      every item's quantity <= live stock (re-checked live, not from build_cart snapshot)
  2. Margin:     every item's (price - cost) / price * 100 >= rules.min_margin_pct
  3. Discount:   applied discount % <= rules.max_ai_discount_pct
  4. Threshold:  cart.total <= rules.approval_threshold_amount
                 (if above → block with "merchant approval required for autonomous purchase")
                 This is an AUTONOMY BOUNDARY — not a maximum sales/payment ceiling.

Pure function — no side effects, no DB writes, no LLM. Easily unit-tested.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CartItemForGate:
    """Cart item data needed by policy_gate — resolved live at gate time."""
    product_id: str
    quantity: int
    unit_price: float          # snapshotted price from build_cart
    role: str
    # Live product data (re-fetched at gate time — §8.3 "don't trust build_cart's snapshot for stock")
    live_price: float          # current live price
    live_cost: float           # current live cost (for margin check)
    live_stock: int            # current live stock
    applied_discount_pct: float = 0.0   # discount % applied to this item (0 = no discount)


@dataclass
class MerchantRulesForGate:
    """Merchant rules data needed by policy_gate."""
    max_ai_discount_pct: float = 0.0
    min_margin_pct: float = 10.0
    approval_threshold_amount: float | None = None   # None = no threshold (always auto-approve)


@dataclass
class CartForGate:
    """Cart data needed by policy_gate."""
    id: str
    total: float
    items: list[CartItemForGate]


def policy_gate(
    cart: CartForGate,
    rules: MerchantRulesForGate,
) -> tuple[bool, list[str]]:
    """
    Run all §8.3 policy gate checks against the cart.

    Returns:
        (passed: bool, reasons: list[str])
        reasons is empty when passed=True.
        Each failed check appends one or more specific reason strings.
    """
    reasons: list[str] = []

    for item in cart.items:
        # ── Check 1: Stock ────────────────────────────────────────────────
        # Re-check live stock, not build_cart snapshot (§8.3 explicit requirement).
        if item.quantity > item.live_stock:
            reasons.append(
                f"insufficient stock for '{item.product_id}': "
                f"need {item.quantity}, live stock is {item.live_stock}"
            )

        # ── Check 2: Margin floor ─────────────────────────────────────────
        # (price - cost) / price * 100 >= min_margin_pct
        if item.live_price > 0:
            margin_pct = (item.live_price - item.live_cost) / item.live_price * 100
            if margin_pct < rules.min_margin_pct:
                reasons.append(
                    f"margin below floor for '{item.product_id}': "
                    f"{margin_pct:.1f}% < {rules.min_margin_pct}% minimum"
                )

        # ── Check 3: Discount limit ───────────────────────────────────────
        # Any applied discount % > rules.max_ai_discount_pct → fail
        if item.applied_discount_pct > rules.max_ai_discount_pct:
            reasons.append(
                f"discount exceeds limit for '{item.product_id}': "
                f"{item.applied_discount_pct:.1f}% > {rules.max_ai_discount_pct:.1f}% allowed"
            )

    # ── Check 4: Autonomous approval threshold ────────────────────────────
    # If cart.total > approval_threshold_amount, the AI cannot autonomously execute.
    # This is an autonomy boundary, NOT a maximum sales/payment ceiling (§2, §8.3).
    # A human-approval workflow would clear this — not in MVP scope.
    if (
        rules.approval_threshold_amount is not None
        and cart.total > rules.approval_threshold_amount
    ):
        reasons.append(
            f"merchant approval required for autonomous purchase "
            f"(₹{cart.total:,.0f} > threshold ₹{rules.approval_threshold_amount:,.0f})"
        )

    passed = len(reasons) == 0
    return passed, reasons
