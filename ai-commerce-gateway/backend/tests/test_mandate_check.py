"""
Phase 4 tests — Mandate Check (§8.2, §14).

Pure function tests — no database, no MCP, no Gemini.
Tests the exact §11 demo scenarios and every condition branch.

§14 specifies: "Unit tests for mandate_check() against §11's two demo carts —
these are pure functions, cheap to test, and they're what 'explainable by design'
actually rests on."
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.engine.mandate_check import (
    mandate_check,
    CartForCheck,
    CartItemForCheck,
    MandateForCheck,
)

# ── Fixtures ────────────────────────────────────────────────────────────────

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
PAST   = datetime.now(timezone.utc) - timedelta(seconds=1)

DEMO_MANDATE = MandateForCheck(
    id="mandate_demo_buyer_1",
    buyer_id="demo-buyer-1",
    max_amount=6000.0,
    category_scope=["footwear", "accessories"],
    expires_at=FUTURE,
)


def _item(product_id: str, price: float, category: str, qty: int = 1) -> CartItemForCheck:
    return CartItemForCheck(
        product_id=product_id,
        quantity=qty,
        unit_price=price,
        role="primary",
        category=category,
    )


def _cart(total: float, items: list[CartItemForCheck]) -> CartForCheck:
    return CartForCheck(id="cart_test", total=total, items=items)


# ── §11 Demo scenario 1 — APPROVE ───────────────────────────────────────────

class TestDemoScenario1:
    """
    "Find me running shoes under ₹6,000"
    → prod_001 (₹5,499) + prod_006 upsell (₹499) = ₹5,998 total
    → MUST PASS
    """

    def test_happy_path_passes(self):
        cart = _cart(5998.0, [
            _item("prod_001", 5499.0, "footwear"),
            _item("prod_006",  499.0, "accessories"),
        ])
        passed, reasons = mandate_check(cart, DEMO_MANDATE)
        assert passed is True
        assert reasons == []

    def test_total_at_exact_limit_passes(self):
        """₹6,000 == ₹6,000 limit → should PASS (≤ not <)"""
        cart = _cart(6000.0, [_item("prod_x", 6000.0, "footwear")])
        passed, reasons = mandate_check(cart, DEMO_MANDATE)
        assert passed is True
        assert reasons == []


# ── §11 Demo scenario 2 — BLOCK ─────────────────────────────────────────────

class TestDemoScenario2:
    """
    "Buy the ₹8,999 version instead"
    → prod_002 (₹8,999) alone
    → MUST FAIL with the exact §8.2 reason string
    """

    def test_over_limit_is_blocked(self):
        cart = _cart(8999.0, [_item("prod_002", 8999.0, "footwear")])
        passed, reasons = mandate_check(cart, DEMO_MANDATE)
        assert passed is False

    def test_over_limit_reason_contains_amounts(self):
        """§8.2 example: "exceeds buyer limit (₹8,999 > ₹6,000)" """
        cart = _cart(8999.0, [_item("prod_002", 8999.0, "footwear")])
        _, reasons = mandate_check(cart, DEMO_MANDATE)
        assert len(reasons) >= 1
        reason = reasons[0]
        assert "8,999" in reason or "8999" in reason, f"Expected ₹8,999 in reason: {reason!r}"
        assert "6,000" in reason or "6000" in reason, f"Expected ₹6,000 in reason: {reason!r}"
        assert "exceed" in reason.lower() or "limit" in reason.lower(), \
            f"Expected 'exceeds' or 'limit' in reason: {reason!r}"


# ── Condition 1: amount ──────────────────────────────────────────────────────

class TestAmountCondition:

    def test_one_rupee_over_fails(self):
        cart = _cart(6001.0, [_item("p", 6001.0, "footwear")])
        passed, reasons = mandate_check(cart, DEMO_MANDATE)
        assert passed is False
        assert any("exceed" in r.lower() or "limit" in r.lower() for r in reasons)

    def test_one_rupee_under_passes(self):
        cart = _cart(5999.0, [_item("p", 5999.0, "footwear")])
        passed, _ = mandate_check(cart, DEMO_MANDATE)
        assert passed is True

    def test_zero_total_passes(self):
        cart = _cart(0.0, [])
        passed, _ = mandate_check(cart, DEMO_MANDATE)
        assert passed is True


# ── Condition 2: category scope ──────────────────────────────────────────────

class TestCategoryScope:

    def test_in_scope_category_passes(self):
        cart = _cart(1000.0, [_item("p", 1000.0, "footwear")])
        passed, _ = mandate_check(cart, DEMO_MANDATE)
        assert passed is True

    def test_out_of_scope_category_fails(self):
        cart = _cart(500.0, [_item("p", 500.0, "electronics")])
        passed, reasons = mandate_check(cart, DEMO_MANDATE)
        assert passed is False
        assert any("scope" in r.lower() or "categor" in r.lower() for r in reasons)

    def test_empty_scope_allows_any_category(self):
        """Empty category_scope = unscoped — any category is allowed."""
        unscoped_mandate = MandateForCheck(
            id="m", buyer_id="b", max_amount=9999.0,
            category_scope=[],   # empty = allow all
            expires_at=FUTURE,
        )
        cart = _cart(500.0, [_item("p", 500.0, "electronics")])
        passed, reasons = mandate_check(cart, unscoped_mandate)
        assert passed is True
        assert reasons == []

    def test_mixed_items_one_out_of_scope_fails(self):
        """All items must be in scope — one out-of-scope item fails the whole cart."""
        cart = _cart(1500.0, [
            _item("p1", 1000.0, "footwear"),    # in scope
            _item("p2",  500.0, "electronics"), # out of scope
        ])
        passed, reasons = mandate_check(cart, DEMO_MANDATE)
        assert passed is False

    def test_category_scope_case_insensitive(self):
        """Category matching must be case-insensitive."""
        cart = _cart(1000.0, [_item("p", 1000.0, "Footwear")])  # uppercase F
        passed, _ = mandate_check(cart, DEMO_MANDATE)
        assert passed is True

    def test_both_demo_categories_pass(self):
        """footwear + accessories in same cart must pass."""
        cart = _cart(5998.0, [
            _item("prod_001", 5499.0, "footwear"),
            _item("prod_006",  499.0, "accessories"),
        ])
        passed, _ = mandate_check(cart, DEMO_MANDATE)
        assert passed is True


# ── Condition 3: expiry ──────────────────────────────────────────────────────

class TestExpiry:

    def test_expired_mandate_fails(self):
        expired_mandate = MandateForCheck(
            id="m", buyer_id="b", max_amount=9999.0,
            category_scope=[],
            expires_at=PAST,
        )
        cart = _cart(100.0, [_item("p", 100.0, "footwear")])
        passed, reasons = mandate_check(cart, expired_mandate)
        assert passed is False
        assert any("expir" in r.lower() for r in reasons)

    def test_future_mandate_passes(self):
        cart = _cart(100.0, [_item("p", 100.0, "footwear")])
        passed, _ = mandate_check(cart, DEMO_MANDATE)
        assert passed is True

    def test_injectable_now_allows_time_travel(self):
        """now parameter is injectable — lets tests control time without mocking datetime."""
        fixed_mandate = MandateForCheck(
            id="m", buyer_id="b", max_amount=9999.0,
            category_scope=[],
            expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        cart = _cart(100.0, [])

        # Before expiry
        passed, _ = mandate_check(cart, fixed_mandate,
                                  now=datetime(2029, 12, 31, tzinfo=timezone.utc))
        assert passed is True

        # After expiry
        passed, _ = mandate_check(cart, fixed_mandate,
                                  now=datetime(2030, 1, 2, tzinfo=timezone.utc))
        assert passed is False

    def test_naive_datetime_handled(self):
        """Naive expires_at (no tzinfo) should not crash — treated as UTC."""
        naive_mandate = MandateForCheck(
            id="m", buyer_id="b", max_amount=9999.0,
            category_scope=[],
            expires_at=datetime(2099, 1, 1),  # naive — no tzinfo
        )
        cart = _cart(100.0, [])
        passed, _ = mandate_check(cart, naive_mandate)
        assert passed is True


# ── Multiple failures ────────────────────────────────────────────────────────

class TestMultipleFailures:

    def test_all_three_conditions_fail_appends_three_reasons(self):
        bad_mandate = MandateForCheck(
            id="m", buyer_id="b",
            max_amount=100.0,
            category_scope=["footwear"],
            expires_at=PAST,
        )
        cart = _cart(9999.0, [_item("p", 9999.0, "electronics")])
        passed, reasons = mandate_check(cart, bad_mandate)
        assert passed is False
        assert len(reasons) == 3, f"Expected 3 failure reasons, got {len(reasons)}: {reasons}"

    def test_amount_and_expiry_fail(self):
        expired_low = MandateForCheck(
            id="m", buyer_id="b",
            max_amount=100.0,
            category_scope=[],
            expires_at=PAST,
        )
        cart = _cart(500.0, [_item("p", 500.0, "anything")])
        passed, reasons = mandate_check(cart, expired_low)
        assert passed is False
        assert len(reasons) == 2
