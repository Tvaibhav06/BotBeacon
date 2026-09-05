"""
Phase 5 tests — Policy Gate (§8.3, §14).

Pure function tests — no database, no MCP, no Gemini.
Tests every §8.3 check (stock, margin floor, discount limit, approval threshold)
and both §11 demo scenarios.
"""
from __future__ import annotations

import pytest

from app.engine.policy_gate import (
    policy_gate,
    CartForGate,
    CartItemForGate,
    MerchantRulesForGate,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

# Seed rules from §11 (velocity_sports)
DEMO_RULES = MerchantRulesForGate(
    max_ai_discount_pct=10.0,
    min_margin_pct=15.0,
    approval_threshold_amount=15000.0,
)


def _item(
    product_id: str,
    quantity: int,
    unit_price: float,
    live_price: float,
    live_cost: float,
    live_stock: int,
    applied_discount_pct: float = 0.0,
    role: str = "primary",
) -> CartItemForGate:
    return CartItemForGate(
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        role=role,
        live_price=live_price,
        live_cost=live_cost,
        live_stock=live_stock,
        applied_discount_pct=applied_discount_pct,
    )


def _cart(total: float, items: list[CartItemForGate]) -> CartForGate:
    return CartForGate(id="cart_test", total=total, items=items)


# ─────────────────────────────────────────────────────────────────────────────
# §11 Demo scenario 1 — APPROVE
# "Find me running shoes under ₹6,000"
# → prod_001 (₹5,499) + prod_006 upsell (₹499) = ₹5,998 total
# ─────────────────────────────────────────────────────────────────────────────

class TestDemoScenario1:
    """Happy path — MUST pass all §8.3 checks."""

    def test_happy_path_passes(self):
        """
        prod_001 (price=5499, cost=3200, stock=40) + prod_006 (price=499, cost=220, stock=200).
        margin prod_001: (5499-3200)/5499*100 ≈ 41.8% ≥ 15%  ✓
        margin prod_006: (499-220)/499*100   ≈ 55.9% ≥ 15%   ✓
        stock: 1 ≤ 40, 1 ≤ 200                               ✓
        discount: 0% ≤ 10%                                    ✓
        threshold: 5998 ≤ 15000                               ✓
        """
        cart = _cart(5998.0, [
            _item("prod_001", 1, 5499.0, 5499.0, 3200.0, 40),
            _item("prod_006", 1,  499.0,  499.0,  220.0, 200, role="upsell"),
        ])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is True
        assert reasons == []


# ─────────────────────────────────────────────────────────────────────────────
# §11 Demo scenario 2 — BLOCK (mandate check already catches this,
#   but policy gate must also pass independently — ₹8,999 is still within
#   the ₹15,000 autonomy threshold, so policy gate approves it; the block
#   comes from mandate check.  This test verifies policy gate independently.)
# ─────────────────────────────────────────────────────────────────────────────

class TestDemoScenario2:
    """
    prod_002 (price=8999, cost=5200, stock=15) alone.
    margin: (8999-5200)/8999*100 ≈ 42.2% ≥ 15%  ✓
    stock: 1 ≤ 15                                ✓
    discount: 0% ≤ 10%                           ✓
    threshold: 8999 ≤ 15000                      ✓
    → Policy gate APPROVES.  Mandate check is what blocks demo scenario 2.
    """

    def test_prod_002_passes_policy_gate(self):
        cart = _cart(8999.0, [
            _item("prod_002", 1, 8999.0, 8999.0, 5200.0, 15),
        ])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is True, f"Policy gate wrongly blocked: {reasons}"


# ─────────────────────────────────────────────────────────────────────────────
# Check 1: Stock
# ─────────────────────────────────────────────────────────────────────────────

class TestStockCheck:

    def test_quantity_at_stock_passes(self):
        cart = _cart(5499.0, [_item("p", 10, 5499.0, 5499.0, 3000.0, 10)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True

    def test_quantity_one_over_stock_fails(self):
        cart = _cart(5499.0, [_item("p", 11, 5499.0, 5499.0, 3000.0, 10)])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is False
        assert any("stock" in r.lower() or "insufficient" in r.lower() for r in reasons)

    def test_zero_stock_with_qty_one_fails(self):
        cart = _cart(5499.0, [_item("p", 1, 5499.0, 5499.0, 3000.0, 0)])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is False

    def test_stock_reason_contains_product_id(self):
        cart = _cart(100.0, [_item("prod_xyz", 5, 100.0, 100.0, 50.0, 2)])
        _, reasons = policy_gate(cart, DEMO_RULES)
        assert any("prod_xyz" in r for r in reasons), f"Reason missing product ID: {reasons}"

    def test_multiple_items_one_out_of_stock_fails(self):
        """All items must pass — one out-of-stock fails the whole cart."""
        cart = _cart(6000.0, [
            _item("p1", 1, 5499.0, 5499.0, 3000.0, 40),  # ok
            _item("p2", 5,  499.0,  499.0,  220.0,  2),   # needs 5, only 2
        ])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is False
        assert any("p2" in r for r in reasons)


# ─────────────────────────────────────────────────────────────────────────────
# Check 2: Margin Floor
# ─────────────────────────────────────────────────────────────────────────────

class TestMarginFloor:

    def test_margin_at_floor_passes(self):
        """margin exactly at min_margin_pct (15%) should pass."""
        # price=100, cost=85 → margin = 15/100*100 = 15.0% — exactly at floor
        cart = _cart(100.0, [_item("p", 1, 100.0, 100.0, 85.0, 99)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True

    def test_margin_just_below_floor_fails(self):
        # price=100, cost=86 → margin = 14/100*100 = 14.0% < 15%
        cart = _cart(100.0, [_item("p", 1, 100.0, 100.0, 86.0, 99)])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is False
        assert any("margin" in r.lower() for r in reasons)

    def test_margin_reason_contains_percentages(self):
        cart = _cart(100.0, [_item("prod_low_margin", 1, 100.0, 100.0, 90.0, 99)])
        _, reasons = policy_gate(cart, DEMO_RULES)
        assert len(reasons) >= 1
        r = reasons[0]
        assert "%" in r, f"Reason should show percentages: {r!r}"

    def test_zero_price_item_skips_margin_check(self):
        """live_price=0 must not cause division by zero."""
        cart = _cart(0.0, [_item("p", 1, 0.0, 0.0, 0.0, 99)])
        # Should not raise, result is irrelevant but must not raise
        try:
            policy_gate(cart, DEMO_RULES)
        except ZeroDivisionError:
            pytest.fail("policy_gate raised ZeroDivisionError on zero-price item")

    def test_high_margin_product_passes(self):
        # prod_001 real data: margin ≈ 41.8%
        cart = _cart(5499.0, [_item("prod_001", 1, 5499.0, 5499.0, 3200.0, 40)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True


# ─────────────────────────────────────────────────────────────────────────────
# Check 3: Discount Limit
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscountLimit:

    def test_no_discount_passes(self):
        cart = _cart(5499.0, [_item("p", 1, 5499.0, 5499.0, 3200.0, 40, applied_discount_pct=0.0)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True

    def test_discount_at_limit_passes(self):
        """10% discount == max_ai_discount_pct=10% → should pass (≤ not <)."""
        cart = _cart(4949.1, [_item("p", 1, 4949.1, 5499.0, 3200.0, 40, applied_discount_pct=10.0)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True

    def test_discount_one_point_over_limit_fails(self):
        cart = _cart(4894.0, [_item("p", 1, 4894.0, 5499.0, 3200.0, 40, applied_discount_pct=10.1)])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is False
        assert any("discount" in r.lower() for r in reasons)

    def test_discount_reason_contains_percentages(self):
        cart = _cart(4000.0, [_item("prod_disc", 1, 4000.0, 5499.0, 3200.0, 40, applied_discount_pct=15.0)])
        _, reasons = policy_gate(cart, DEMO_RULES)
        assert any("%" in r for r in reasons)


# ─────────────────────────────────────────────────────────────────────────────
# Check 4: Autonomous Approval Threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalThreshold:

    def test_total_at_threshold_passes(self):
        """₹15,000 == threshold → should pass (> not ≥)."""
        cart = _cart(15000.0, [_item("p", 1, 15000.0, 15000.0, 8000.0, 10)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True

    def test_total_one_rupee_over_threshold_fails(self):
        cart = _cart(15001.0, [_item("p", 1, 15001.0, 15001.0, 8000.0, 10)])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is False
        assert any("approval" in r.lower() or "threshold" in r.lower() for r in reasons)

    def test_threshold_reason_says_autonomous(self):
        """§8.3: reason must mention 'autonomous' (autonomy boundary)."""
        cart = _cart(20000.0, [_item("p", 1, 20000.0, 20000.0, 8000.0, 10)])
        _, reasons = policy_gate(cart, DEMO_RULES)
        assert any("autonomous" in r.lower() for r in reasons), \
            f"Reason should mention 'autonomous': {reasons}"

    def test_no_threshold_always_passes_check_4(self):
        """approval_threshold_amount=None means no threshold check."""
        no_threshold_rules = MerchantRulesForGate(
            max_ai_discount_pct=10.0,
            min_margin_pct=15.0,
            approval_threshold_amount=None,
        )
        cart = _cart(999999.0, [_item("p", 1, 999999.0, 999999.0, 400000.0, 10)])
        passed, reasons = policy_gate(cart, no_threshold_rules)
        # Only check 4 would fail — with None it should not appear in reasons
        assert not any("approval" in r.lower() or "threshold" in r.lower() for r in reasons), \
            f"Threshold check fired when threshold=None: {reasons}"

    def test_threshold_is_autonomy_boundary_not_payment_ceiling(self):
        """
        Critical invariant (§2, §8.3): the threshold is an autonomy boundary.
        A cart of ₹14,999 < ₹15,000 must be approved by the gate
        even though ₹14,999 is a large purchase.
        """
        cart = _cart(14999.0, [_item("p", 1, 14999.0, 14999.0, 8000.0, 10)])
        passed, _ = policy_gate(cart, DEMO_RULES)
        assert passed is True


# ─────────────────────────────────────────────────────────────────────────────
# Multiple failures
# ─────────────────────────────────────────────────────────────────────────────

class TestMultipleFailures:

    def test_stock_and_margin_both_fail(self):
        cart = _cart(100.0, [_item("p", 5, 100.0, 100.0, 90.0, 2)])  # qty>stock + low margin
        _, reasons = policy_gate(cart, DEMO_RULES)
        assert len(reasons) >= 2

    def test_all_checks_fail_independently(self):
        """
        Construct a cart that trips all four checks:
        - stock: qty=5, live_stock=2
        - margin: live_price=100, live_cost=90 → 10% < 15%
        - discount: 20% > 10%
        - threshold: total=20000 > 15000
        """
        bad_rules = MerchantRulesForGate(
            max_ai_discount_pct=10.0,
            min_margin_pct=15.0,
            approval_threshold_amount=15000.0,
        )
        cart = _cart(20000.0, [_item("p", 5, 80.0, 100.0, 90.0, 2, applied_discount_pct=20.0)])
        passed, reasons = policy_gate(cart, bad_rules)
        assert passed is False
        assert len(reasons) >= 3, f"Expected ≥3 reasons, got {len(reasons)}: {reasons}"

    def test_empty_cart_passes_all_item_checks(self):
        """Empty cart: no items → no per-item checks fire. Threshold check still runs."""
        cart = _cart(0.0, [])
        passed, reasons = policy_gate(cart, DEMO_RULES)
        assert passed is True
        assert reasons == []
