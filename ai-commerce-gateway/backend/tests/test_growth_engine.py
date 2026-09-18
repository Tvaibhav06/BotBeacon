"""
Phase 3 tests — Growth Engine & Deterministic Growth Policy Gate (§6.2, §6.3, §6.4, §8.3).

Tests:
1. Exact formula calculation for discount exposure and bundle margin.
2. Deterministic policy gate with the three exact outcomes: BLOCKED, REQUIRES_APPROVAL, ALLOWED.
3. Enforcement of all rules: actions disabled, discount ceiling, margin floor, inactive/out-of-stock, safe defaults.
4. Mandatory double-check / rule-change regression test.
5. Declining-sales and cross-sell detectors on seeded data.
6. Live sales insights aggregation.
"""
import pytest
from app.engine.growth_policy import (
    growth_policy_gate,
    calculate_discount_exposure,
    calculate_bundle_margin,
    ActionForGrowthGate,
    ProductForGrowthGate,
    MerchantRulesForGrowthGate,
    BLOCKED,
    REQUIRES_APPROVAL,
    ALLOWED,
)


class TestFormulas:
    """Test exact mathematical definitions from PRD §8.3."""

    def test_estimated_discount_exposure_worked_example(self):
        """
        PRD §8.3 Worked Example:
          Velocity Pro (₹5,499) + Performance Socks (₹499)
          5 units/week × 1 week × (₹5,499 + ₹499) × 10% = ₹2,999
        """
        products = [
            ProductForGrowthGate(id="prod_001", price=5499.0, cost=3200.0, stock=40),
            ProductForGrowthGate(id="prod_006", price=499.0, cost=220.0, stock=200),
        ]
        exposure = calculate_discount_exposure(
            weekly_units=5.0,
            campaign_duration_weeks=1,
            products=products,
            discount_pct=10.0,
        )
        assert exposure == 2999.0

    def test_bundle_margin_calculation(self):
        """
        PRD §8.3 Bundle margin on selling price:
          regular_price_sum = 5499 + 499 = 5998
          cost_sum = 3200 + 220 = 3420
          discounted_price = 5998 * 0.90 = 5398.2
          margin = (5398.2 - 3420) / 5398.2 * 100 ≈ 36.65%
        """
        products = [
            ProductForGrowthGate(id="prod_001", price=5499.0, cost=3200.0, stock=40),
            ProductForGrowthGate(id="prod_006", price=499.0, cost=220.0, stock=200),
        ]
        margin = calculate_bundle_margin(products, discount_pct=10.0)
        assert round(margin, 2) == 36.65


class TestGrowthPolicyGate:
    """Deterministic evaluation of growth_policy_gate (§6.4)."""

    @pytest.fixture
    def demo_products(self):
        return [
            ProductForGrowthGate(id="prod_001", price=5499.0, cost=3200.0, stock=40, status="active"),
            ProductForGrowthGate(id="prod_006", price=499.0, cost=220.0, stock=200, status="active"),
        ]

    def test_blocked_when_actions_disabled(self, demo_products):
        """Rules with growth_actions_enabled=False must BLOCK regardless of other values."""
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=10.0,
            estimated_discount_exposure=2999.0,
            products=demo_products,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=False,
            max_ai_discount_pct=15.0,
            min_margin_pct=15.0,
            growth_approval_threshold_amount=5000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == BLOCKED
        assert any("disabled" in r for r in reasons)

    def test_blocked_when_discount_exceeds_max(self, demo_products):
        """Discount 25% > max 15% must be BLOCKED (Golden Demo Path 2)."""
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=25.0,
            estimated_discount_exposure=5000.0,
            products=demo_products,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=15.0,
            growth_approval_threshold_amount=10000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == BLOCKED
        assert any("exceeds maximum allowed" in r for r in reasons)

    def test_blocked_when_margin_below_floor(self):
        """High cost / low margin bundle below min_margin_pct must be BLOCKED."""
        low_margin_products = [
            ProductForGrowthGate(id="prod_low", price=1000.0, cost=950.0, stock=10, status="active")
        ]
        # Margin at 10% discount: price=900, cost=950 -> negative margin (-5.5%)
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=10.0,
            estimated_discount_exposure=100.0,
            products=low_margin_products,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=10.0,
            growth_approval_threshold_amount=1000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == BLOCKED
        assert any("below minimum floor" in r for r in reasons)

    def test_blocked_when_product_out_of_stock(self):
        """Out of stock product must be BLOCKED."""
        oos_product = [
            ProductForGrowthGate(id="prod_oos", price=1000.0, cost=500.0, stock=0, status="active")
        ]
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=5.0,
            estimated_discount_exposure=50.0,
            products=oos_product,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=10.0,
            growth_approval_threshold_amount=1000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == BLOCKED
        assert any("out of stock" in r for r in reasons)

    def test_blocked_when_product_inactive(self):
        """Inactive product must be BLOCKED."""
        inactive_product = [
            ProductForGrowthGate(id="prod_inact", price=1000.0, cost=500.0, stock=10, status="inactive")
        ]
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=5.0,
            estimated_discount_exposure=50.0,
            products=inactive_product,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=10.0,
            growth_approval_threshold_amount=1000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == BLOCKED
        assert any("inactive" in r for r in reasons)

    def test_requires_approval_when_threshold_is_none(self, demo_products):
        """None threshold (safe default) must always return REQUIRES_APPROVAL (§6.4, §8.2)."""
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=10.0,
            estimated_discount_exposure=500.0,  # low exposure
            products=demo_products,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=15.0,
            growth_approval_threshold_amount=None,  # Safe default: always ask human
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == REQUIRES_APPROVAL
        assert any("no autonomous threshold configured" in r for r in reasons)

    def test_requires_approval_when_exposure_exceeds_threshold(self, demo_products):
        """Golden Demo Path 1: ₹2,999 exposure > ₹2,000 threshold -> REQUIRES_APPROVAL."""
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=10.0,
            estimated_discount_exposure=2999.0,
            products=demo_products,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=15.0,
            growth_approval_threshold_amount=2000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == REQUIRES_APPROVAL
        assert any("exceeds autonomous approval threshold" in r for r in reasons)

    def test_allowed_when_exposure_under_threshold(self, demo_products):
        """Exposure <= threshold -> ALLOWED (autonomous execution permitted)."""
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=10.0,
            estimated_discount_exposure=1500.0,  # below 2000
            products=demo_products,
        )
        rules = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=15.0,
            growth_approval_threshold_amount=2000.0,
        )
        outcome, reasons = growth_policy_gate(action, rules)
        assert outcome == ALLOWED
        assert reasons == []

    def test_mandatory_double_check_regression_test(self, demo_products):
        """
        PRD §6.4 & §10 mandatory double-check regression test:
        1. Action created under permissive rules (15% max discount, 2000 threshold) -> REQUIRES_APPROVAL.
        2. Between creation and approval, merchant tightens rules (max discount reduced to 5%).
        3. Re-evaluating against fresh rules immediately returns BLOCKED.
        Proves stored first-check result is never trusted.
        """
        action = ActionForGrowthGate(
            type="discount_bundle",
            discount_pct=10.0,
            estimated_discount_exposure=2999.0,
            products=demo_products,
        )

        # Check 1: At proposal time
        rules_at_proposal = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=15.0,
            min_margin_pct=15.0,
            growth_approval_threshold_amount=2000.0,
        )
        outcome_1, _ = growth_policy_gate(action, rules_at_proposal)
        assert outcome_1 == REQUIRES_APPROVAL

        # Check 2: At approval click time, merchant had tightened max discount to 5%
        rules_at_click = MerchantRulesForGrowthGate(
            growth_actions_enabled=True,
            max_ai_discount_pct=5.0,  # tightened!
            min_margin_pct=15.0,
            growth_approval_threshold_amount=2000.0,
        )
        outcome_2, reasons_2 = growth_policy_gate(action, rules_at_click)
        assert outcome_2 == BLOCKED
        assert any("exceeds maximum allowed" in r for r in reasons_2)


class TestDetectorsAndInsights:
    """Integration test of SQL aggregate detectors on seeded data (§6.2, §10)."""

    @pytest.fixture
    def db_session(self):
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def test_declining_sales_detector_flags_velocity_pro(self, db_session):
        from app.engine.growth_detectors import detect_declining_sales

        declining = detect_declining_sales(db_session, "merchant_velocity_sports", window_days=14)
        assert len(declining) > 0

        # prod_001 (Velocity Pro) must be the primary flagged product
        p1 = next((d for d in declining if d["product_id"] == "prod_001"), None)
        assert p1 is not None
        assert p1["product_name"] == "Velocity Pro"
        assert p1["prior_weekly_units"] == 8.0
        assert p1["recent_weekly_units"] == 5.0
        assert p1["units_drop_pct"] == 37.5  # ~35% drop
        assert p1["evidence"]["recent_weekly_units"] == 5.0

    def test_cross_sell_detector_flags_velocity_pro_and_socks_pair(self, db_session):
        from app.engine.growth_detectors import detect_cross_sell_opportunities

        opps = detect_cross_sell_opportunities(
            db_session, "merchant_velocity_sports", primary_product_id="prod_001"
        )
        assert len(opps) > 0

        socks_pair = next((o for o in opps if o["complement_product_id"] == "prod_006"), None)
        assert socks_pair is not None
        assert socks_pair["primary_product_name"] == "Velocity Pro"
        assert socks_pair["complement_product_name"] == "Performance Socks (2-pack)"
        assert socks_pair["attach_rate_pct"] == 10.0  # 1 co-purchase out of 10 carts

    def test_sales_insights_aggregation(self, db_session):
        from app.engine.growth_detectors import get_sales_insights

        insights = get_sales_insights(db_session, "merchant_velocity_sports", window_days=14)
        assert "trend_pct" in insights
        assert insights["total_units_recent"] > 0
        assert insights["total_revenue_recent"] > 0.0
        assert len(insights["top_products"]) > 0
        assert any(d["product_id"] == "prod_001" for d in insights["declining_products"])

    def test_build_growth_opportunity_proposal(self, db_session):
        from app.engine.growth_detectors import build_growth_opportunity_proposal

        proposal = build_growth_opportunity_proposal(
            db_session,
            merchant_id="merchant_velocity_sports",
            opportunity_type="declining_sales",
            primary_product_id="prod_001",
            complement_product_id="prod_006",
            discount_pct=10.0,
            campaign_duration_weeks=1,
        )

        assert proposal["opportunity_type"] == "declining_sales"
        assert proposal["estimated_discount_exposure"] == 2999.0
        assert proposal["policy_outcome"] == REQUIRES_APPROVAL
        assert proposal["status"] == "pending_approval"
        assert proposal["recommended_action"]["discount_pct"] == 10.0
        assert proposal["recommended_action"]["audience"] == "configured_demo_audience"
