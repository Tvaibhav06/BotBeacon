"""
Mandate Check — §8.2.
Deterministic buyer-authority validation.
Lives in backend/app/engine/ — called by check_policy MCP tool.

Rule (§8.2):
  passed = (cart.total <= mandate.max_amount)
         AND (mandate.category_scope is empty
              OR every cart item's category ⊆ mandate.category_scope)
         AND (now < mandate.expires_at)

Each failed condition appends a specific reason string.
Pure function — no side effects, no DB writes, easily unit-tested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CartItemForCheck:
    """Minimal cart item data needed by mandate_check — avoids ORM coupling in tests."""
    product_id: str
    quantity: int
    unit_price: float
    role: str
    category: str  # resolved from Product at call time in check_policy


@dataclass
class MandateForCheck:
    """Minimal mandate data needed by mandate_check — avoids ORM coupling in tests."""
    id: str
    buyer_id: str
    max_amount: float
    category_scope: list[str]  # empty = unscoped (any category allowed)
    expires_at: datetime


@dataclass
class CartForCheck:
    """Minimal cart data needed by mandate_check."""
    id: str
    total: float
    items: list[CartItemForCheck]


def mandate_check(
    cart: CartForCheck,
    mandate: MandateForCheck,
    now: datetime | None = None,
) -> tuple[bool, list[str]]:
    """
    Run the §8.2 mandate check.

    Args:
        cart:    Cart to validate (total + items with categories resolved)
        mandate: Buyer mandate to check against
        now:     Current time (injectable for testing; defaults to UTC now)

    Returns:
        (passed: bool, reasons: list[str])
        reasons is empty when passed=True.
        Each failed condition appends one specific reason string.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    reasons: list[str] = []

    # ── Condition 1: amount ────────────────────────────────────────────────
    if cart.total > mandate.max_amount:
        reasons.append(
            f"exceeds buyer limit (₹{cart.total:,.0f} > ₹{mandate.max_amount:,.0f})"
        )

    # ── Condition 2: category scope ────────────────────────────────────────
    # Empty category_scope means unscoped — any category is allowed.
    if mandate.category_scope:
        scope_lower = [c.lower() for c in mandate.category_scope]
        out_of_scope = [
            item for item in cart.items
            if item.category.lower() not in scope_lower
        ]
        if out_of_scope:
            bad_cats = list({item.category for item in out_of_scope})
            bad_cats_str = ", ".join(bad_cats)
            scope_str = ", ".join(mandate.category_scope)
            reasons.append(
                f"category out of scope ({bad_cats_str!r} not in [{scope_str}])"
            )

    # ── Condition 3: expiry ────────────────────────────────────────────────
    # Ensure both datetimes are timezone-aware for comparison
    expires = mandate.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now >= expires:
        reasons.append(
            f"mandate expired (expired {expires.strftime('%Y-%m-%d %H:%M UTC')})"
        )

    passed = len(reasons) == 0
    return passed, reasons
