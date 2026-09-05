"""
Phase 1 tests — Validation logic (§8.6 and §14).
These are pure-function tests; no database required.
"""
import pytest
from unittest.mock import MagicMock

from app.engine.validation import validate_product, validate_catalog
from app.schemas import MerchantRules


def _make_product(**kwargs):
    """Create a mock ProductModel for testing."""
    defaults = {
        "id": "test_prod",
        "name": "Test Product",
        "category": "footwear",
        "price": 5000.0,
        "cost": 2000.0,
        "stock": 10,
        "status": "active",
    }
    defaults.update(kwargs)
    p = MagicMock()
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


RULES = MerchantRules(min_margin_pct=15.0)


class TestValidateProduct:

    def test_valid_product_no_issues(self):
        product = _make_product(price=5499.0, cost=3200.0)
        # margin = (5499 - 3200) / 5499 * 100 ≈ 41.8% > 15% → no warning
        issues = validate_product(product, RULES)
        assert issues == []

    def test_price_zero_is_error(self):
        product = _make_product(price=0.0)
        issues = validate_product(product, RULES)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert errors[0].field == "price"

    def test_price_negative_is_error(self):
        product = _make_product(price=-100.0)
        issues = validate_product(product, RULES)
        errors = [i for i in issues if i.severity == "error"]
        assert any(i.field == "price" for i in errors)

    def test_stock_negative_is_error(self):
        product = _make_product(stock=-1)
        issues = validate_product(product, RULES)
        errors = [i for i in issues if i.severity == "error"]
        assert any(i.field == "stock" for i in errors)

    def test_missing_name_is_error(self):
        product = _make_product(name="")
        issues = validate_product(product, RULES)
        errors = [i for i in issues if i.severity == "error"]
        assert any(i.field == "name" for i in errors)

    def test_missing_category_is_error(self):
        product = _make_product(category="")
        issues = validate_product(product, RULES)
        errors = [i for i in issues if i.severity == "error"]
        assert any(i.field == "category" for i in errors)

    def test_below_margin_is_warning_not_error(self):
        # price=1000, cost=900 → margin=10% < 15% min_margin_pct → warning
        product = _make_product(price=1000.0, cost=900.0)
        issues = validate_product(product, RULES)
        warnings = [i for i in issues if i.severity == "warning"]
        errors = [i for i in issues if i.severity == "error"]
        assert len(warnings) == 1
        assert warnings[0].field == "price"
        assert errors == []  # warning does NOT block activation

    def test_exactly_at_margin_threshold_no_warning(self):
        # margin exactly 15%: price=100, cost=85 → (100-85)/100*100 = 15% → no warning
        product = _make_product(price=100.0, cost=85.0)
        issues = validate_product(product, RULES)
        assert issues == []


class TestValidateCatalog:

    def test_no_errors_can_activate(self):
        products = [_make_product(id=f"p{i}", price=5000.0, cost=2000.0) for i in range(3)]
        issues, can_activate = validate_catalog(products, RULES)
        assert can_activate is True

    def test_one_error_blocks_activation(self):
        products = [
            _make_product(id="p1", price=5000.0, cost=2000.0),
            _make_product(id="p2", price=0.0, cost=0.0),  # error: price=0
        ]
        issues, can_activate = validate_catalog(products, RULES)
        assert can_activate is False
        assert any(i.severity == "error" for i in issues)

    def test_only_warnings_can_activate(self):
        # All products have price > 0 but below margin threshold → warnings only
        products = [_make_product(id=f"p{i}", price=100.0, cost=90.0) for i in range(2)]
        issues, can_activate = validate_catalog(products, RULES)
        assert can_activate is True  # warnings never block
        assert all(i.severity == "warning" for i in issues)

    def test_inactive_products_skipped(self):
        # inactive product with price=0 should not produce an error
        products = [_make_product(id="p1", price=0.0, status="inactive")]
        issues, can_activate = validate_catalog(products, RULES)
        assert can_activate is True
        assert issues == []

    def test_demo_seed_products_pass_validation(self):
        """
        The 8 named seed products (§11) must all pass validation with no errors.
        prod_001 Velocity Pro: price=5499, cost=3200, margin≈41.8% ✓
        prod_006 Performance Socks: price=499, cost=220, margin≈55.9% ✓
        """
        seed_products = [
            _make_product(id="prod_001", name="Velocity Pro",              price=5499, cost=3200, category="footwear"),
            _make_product(id="prod_002", name="Velocity Pro (Premium)",    price=8999, cost=5200, category="footwear"),
            _make_product(id="prod_003", name="Trail Runner X",            price=4999, cost=2800, category="footwear"),
            _make_product(id="prod_004", name="Court Classic",             price=3499, cost=1900, category="footwear"),
            _make_product(id="prod_005", name="Everyday Sneaker",          price=2999, cost=1600, category="footwear"),
            _make_product(id="prod_006", name="Performance Socks (2-pack)",price=499,  cost=220,  category="accessories"),
            _make_product(id="prod_007", name="Cushion Insoles",           price=699,  cost=300,  category="accessories"),
            _make_product(id="prod_008", name="Running Cap",               price=599,  cost=260,  category="accessories"),
        ]
        issues, can_activate = validate_catalog(seed_products, RULES)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"Seed products have errors: {errors}"
        assert can_activate is True
