"""
Commerce Passport validation — §8.6.
Merchant data is ground truth. Only structural/range checks apply.
No confidence scoring on Mode 1 data.

error   → blocks passport activation
warning → flagged but does not block
"""
from app.schemas import ValidationIssue, MerchantRules
from app.models import ProductModel


def validate_product(product: ProductModel, rules: MerchantRules | None) -> list[ValidationIssue]:
    """
    Run all §8.6 checks on a single product.
    Returns a (possibly empty) list of ValidationIssue.
    """
    issues: list[ValidationIssue] = []

    # --- ERROR checks (block activation) ---

    if not product.name or not product.name.strip():
        issues.append(ValidationIssue(
            product_id=product.id,
            field="name",
            message="Product name is required",
            severity="error",
        ))

    if not product.category or not product.category.strip():
        issues.append(ValidationIssue(
            product_id=product.id,
            field="category",
            message="Category is required",
            severity="error",
        ))

    if product.price <= 0:
        issues.append(ValidationIssue(
            product_id=product.id,
            field="price",
            message=f"Price must be > 0 (got {product.price})",
            severity="error",
        ))

    if product.stock < 0:
        issues.append(ValidationIssue(
            product_id=product.id,
            field="stock",
            message=f"Stock cannot be negative (got {product.stock})",
            severity="error",
        ))

    # --- WARNING checks (flagged, does not block) ---

    if rules and product.price > 0:
        # Warn if price < cost * (1 + min_margin_pct / 100)
        # i.e. (price - cost) / price * 100 < min_margin_pct
        if product.price > 0:
            margin_pct = (product.price - product.cost) / product.price * 100
            if margin_pct < rules.min_margin_pct:
                issues.append(ValidationIssue(
                    product_id=product.id,
                    field="price",
                    message=(
                        f"Margin {margin_pct:.1f}% is below merchant's stated minimum "
                        f"{rules.min_margin_pct}% "
                        f"(price ₹{product.price}, cost ₹{product.cost})"
                    ),
                    severity="warning",
                ))

    return issues


def validate_catalog(
    products: list[ProductModel],
    rules: MerchantRules | None,
) -> tuple[list[ValidationIssue], bool]:
    """
    Validate all products in a merchant's catalog.

    Returns:
        (all_issues, can_activate)
        can_activate is True only when there are no error-severity issues.
    """
    all_issues: list[ValidationIssue] = []
    for product in products:
        if product.status == "active":
            all_issues.extend(validate_product(product, rules))

    can_activate = not any(i.severity == "error" for i in all_issues)
    return all_issues, can_activate
