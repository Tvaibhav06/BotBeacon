"""
Growth Engine — §6.2, §6.3, and §8.3.

Implements deterministic opportunity detectors and live sales insights aggregation:
1. Declining-sales detector (pure SQL window aggregation).
2. Cross-sell detector (ProductModel.complement_categories + CartItemModel co-occurrence).
3. Live sales insights aggregator.
4. Proposal builder that assembles a structured GrowthOpportunity with exact exposure and policy evaluation.

Zero LLM involvement in any numeric computation or policy decision.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date
from typing import Optional
from sqlalchemy import func, and_, select
from sqlalchemy.orm import Session

from app.models import (
    MerchantModel,
    MerchantRulesModel,
    ProductModel,
    SalesRecordModel,
    CartModel,
    CartItemModel,
)
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


def detect_declining_sales(
    db: Session,
    merchant_id: str,
    window_days: int = 14,
    reference_date: Optional[date] = None,
) -> list[dict]:
    """
    Compares sales in the recent N-day window vs the immediately preceding equivalent window (§6.2).
    Flags products with declining unit volume. Pure SQL aggregation.

    Returns:
        List of declining opportunity dicts sorted by percentage drop descending.
    """
    ref = reference_date or datetime.now(timezone.utc).date()
    recent_start = ref - timedelta(days=window_days)
    prior_start = ref - timedelta(days=2 * window_days)

    # Aggregate recent window sales: [recent_start, ref]
    recent_rows = (
        db.query(
            SalesRecordModel.product_id,
            func.sum(SalesRecordModel.units_sold).label("units"),
            func.sum(SalesRecordModel.revenue).label("revenue"),
        )
        .filter(
            SalesRecordModel.merchant_id == merchant_id,
            SalesRecordModel.date >= recent_start,
            SalesRecordModel.date <= ref,
        )
        .group_by(SalesRecordModel.product_id)
        .all()
    )
    recent_map = {r[0]: {"units": int(r[1] or 0), "revenue": float(r[2] or 0.0)} for r in recent_rows}

    # Aggregate prior window sales: [prior_start, recent_start - 1 day]
    prior_rows = (
        db.query(
            SalesRecordModel.product_id,
            func.sum(SalesRecordModel.units_sold).label("units"),
            func.sum(SalesRecordModel.revenue).label("revenue"),
        )
        .filter(
            SalesRecordModel.merchant_id == merchant_id,
            SalesRecordModel.date >= prior_start,
            SalesRecordModel.date < recent_start,
        )
        .group_by(SalesRecordModel.product_id)
        .all()
    )
    prior_map = {r[0]: {"units": int(r[1] or 0), "revenue": float(r[2] or 0.0)} for r in prior_rows}

    all_product_ids = set(recent_map.keys()).union(set(prior_map.keys()))
    if not all_product_ids:
        return []

    # Fetch product metadata
    products = {
        p.id: p
        for p in db.query(ProductModel).filter(
            ProductModel.id.in_(list(all_product_ids)),
            ProductModel.merchant_id == merchant_id,
        ).all()
    }

    weeks = window_days / 7.0
    results: list[dict] = []

    for pid in all_product_ids:
        prod = products.get(pid)
        if not prod or prod.status != "active":
            continue

        prior = prior_map.get(pid, {"units": 0, "revenue": 0.0})
        recent = recent_map.get(pid, {"units": 0, "revenue": 0.0})

        prior_units = prior["units"]
        recent_units = recent["units"]

        # Only flag products that had sales previously and saw a decline
        if prior_units > 0 and recent_units < prior_units:
            drop_pct = round(((prior_units - recent_units) / prior_units) * 100.0, 1)
            prior_weekly = round(prior_units / weeks, 1)
            recent_weekly = round(recent_units / weeks, 1)

            results.append({
                "opportunity_type": "declining_sales",
                "product_id": pid,
                "product_name": prod.name,
                "category": prod.category,
                "price": prod.price,
                "cost": prod.cost,
                "stock": prod.stock,
                "complement_categories": prod.complement_categories,
                "prior_units": prior_units,
                "recent_units": recent_units,
                "prior_weekly_units": prior_weekly,
                "recent_weekly_units": recent_weekly,
                "units_drop_pct": drop_pct,
                "prior_revenue": prior["revenue"],
                "recent_revenue": recent["revenue"],
                "evidence": {
                    "product_id": pid,
                    "product_name": prod.name,
                    "prior_window_units": prior_units,
                    "recent_window_units": recent_units,
                    "prior_weekly_units": prior_weekly,
                    "recent_weekly_units": recent_weekly,
                    "units_drop_pct": drop_pct,
                    "window_days": window_days,
                },
            })

    results.sort(key=lambda x: x["units_drop_pct"], reverse=True)
    return results


def detect_cross_sell_opportunities(
    db: Session,
    merchant_id: str,
    primary_product_id: Optional[str] = None,
) -> list[dict]:
    """
    Uses ProductModel.complement_categories + CartItemModel history to find defined complements
    with low historical co-attach rates (§6.2).

    Returns:
        List of cross-sell opportunity dicts sorted by attach rate ascending (lowest attach rate first).
    """
    # Fetch active products with complement_categories defined
    query = db.query(ProductModel).filter(
        ProductModel.merchant_id == merchant_id,
        ProductModel.status == "active",
    )
    if primary_product_id:
        query = query.filter(ProductModel.id == primary_product_id)

    candidates = query.all()
    results: list[dict] = []

    for primary in candidates:
        if not primary.complement_categories:
            continue

        # Find active complementary products in those categories
        complements = db.query(ProductModel).filter(
            ProductModel.merchant_id == merchant_id,
            ProductModel.status == "active",
            ProductModel.category.in_(primary.complement_categories),
            ProductModel.id != primary.id,
            ProductModel.stock > 0,
        ).all()

        if not complements:
            continue

        # Find total carts containing the primary product
        primary_cart_ids = {
            r[0] for r in db.query(CartItemModel.cart_id).filter(
                CartItemModel.product_id == primary.id
            ).distinct().all()
        }
        total_primary_carts = len(primary_cart_ids)

        for comp in complements:
            if total_primary_carts == 0:
                co_carts = 0
                attach_rate = 0.0
            else:
                # Find carts that contain both primary and complement
                co_carts = (
                    db.query(CartItemModel.cart_id)
                    .filter(
                        CartItemModel.cart_id.in_(list(primary_cart_ids)),
                        CartItemModel.product_id == comp.id,
                    )
                    .distinct()
                    .count()
                )
                attach_rate = round((co_carts / total_primary_carts) * 100.0, 1)

            # Flag if low attach rate (<= 25%)
            if attach_rate <= 25.0:
                results.append({
                    "opportunity_type": "cross_sell",
                    "primary_product_id": primary.id,
                    "primary_product_name": primary.name,
                    "primary_category": primary.category,
                    "primary_price": primary.price,
                    "primary_cost": primary.cost,
                    "complement_product_id": comp.id,
                    "complement_product_name": comp.name,
                    "complement_category": comp.category,
                    "complement_price": comp.price,
                    "complement_cost": comp.cost,
                    "total_primary_carts": total_primary_carts,
                    "co_purchased_carts": co_carts,
                    "attach_rate_pct": attach_rate,
                    "evidence": {
                        "primary_product_id": primary.id,
                        "primary_product_name": primary.name,
                        "complement_product_id": comp.id,
                        "complement_product_name": comp.name,
                        "complement_category": comp.category,
                        "primary_cart_count": total_primary_carts,
                        "co_purchased_cart_count": co_carts,
                        "attach_rate_pct": attach_rate,
                    },
                })

    # Sort lowest attach rate first
    results.sort(key=lambda x: x["attach_rate_pct"])
    return results


def get_sales_insights(
    db: Session,
    merchant_id: str,
    window_days: int = 14,
    reference_date: Optional[date] = None,
) -> dict:
    """
    On-demand aggregation of sales trend, top products, and declining products (§6.2).
    Computed live, never persisted as a separate cache table.
    """
    ref = reference_date or datetime.now(timezone.utc).date()
    recent_start = ref - timedelta(days=window_days)
    prior_start = ref - timedelta(days=2 * window_days)

    # Recent totals
    recent_totals = (
        db.query(
            func.coalesce(func.sum(SalesRecordModel.units_sold), 0).label("units"),
            func.coalesce(func.sum(SalesRecordModel.revenue), 0.0).label("revenue"),
        )
        .filter(
            SalesRecordModel.merchant_id == merchant_id,
            SalesRecordModel.date >= recent_start,
            SalesRecordModel.date <= ref,
        )
        .first()
    )
    recent_units = int(recent_totals[0]) if recent_totals else 0
    recent_revenue = float(recent_totals[1]) if recent_totals else 0.0

    # Prior totals
    prior_totals = (
        db.query(
            func.coalesce(func.sum(SalesRecordModel.units_sold), 0).label("units"),
            func.coalesce(func.sum(SalesRecordModel.revenue), 0.0).label("revenue"),
        )
        .filter(
            SalesRecordModel.merchant_id == merchant_id,
            SalesRecordModel.date >= prior_start,
            SalesRecordModel.date < recent_start,
        )
        .first()
    )
    prior_units = int(prior_totals[0]) if prior_totals else 0
    prior_revenue = float(prior_totals[1]) if prior_totals else 0.0

    # Overall revenue trend %
    if prior_revenue > 0:
        trend_pct = round(((recent_revenue - prior_revenue) / prior_revenue) * 100.0, 1)
    else:
        trend_pct = 0.0

    # Product breakdowns
    recent_product_sales = (
        db.query(
            SalesRecordModel.product_id,
            func.sum(SalesRecordModel.units_sold).label("units"),
            func.sum(SalesRecordModel.revenue).label("revenue"),
        )
        .filter(
            SalesRecordModel.merchant_id == merchant_id,
            SalesRecordModel.date >= recent_start,
            SalesRecordModel.date <= ref,
        )
        .group_by(SalesRecordModel.product_id)
        .all()
    )

    prod_names = {
        p.id: p.name
        for p in db.query(ProductModel).filter(ProductModel.merchant_id == merchant_id).all()
    }

    top_products = [
        {
            "product_id": r[0],
            "product_name": prod_names.get(r[0], r[0]),
            "units_sold": int(r[1] or 0),
            "revenue": round(float(r[2] or 0.0), 2),
        }
        for r in sorted(recent_product_sales, key=lambda x: float(x[2] or 0.0), reverse=True)
    ]

    declining = detect_declining_sales(db, merchant_id, window_days=window_days, reference_date=ref)
    declining_summary = [
        {
            "product_id": d["product_id"],
            "product_name": d["product_name"],
            "recent_weekly_units": d["recent_weekly_units"],
            "prior_weekly_units": d["prior_weekly_units"],
            "units_drop_pct": d["units_drop_pct"],
        }
        for d in declining
    ]

    return {
        "trend_pct": trend_pct,
        "total_units_recent": recent_units,
        "total_revenue_recent": round(recent_revenue, 2),
        "total_units_prior": prior_units,
        "total_revenue_prior": round(prior_revenue, 2),
        "top_products": top_products[:5],
        "declining_products": declining_summary,
    }


def build_growth_opportunity_proposal(
    db: Session,
    merchant_id: str,
    opportunity_type: str,
    primary_product_id: str,
    complement_product_id: Optional[str] = None,
    discount_pct: float = 10.0,
    campaign_duration_weeks: int = 1,
    title: Optional[str] = None,
) -> dict:
    """
    Constructs a complete GrowthOpportunity proposal, computing exact discount exposure
    and deterministically evaluating it with growth_policy_gate (§6.3, §6.4, §8.3).
    """
    primary = db.get(ProductModel, primary_product_id)
    if not primary:
        raise ValueError(f"Primary product '{primary_product_id}' not found")

    products_for_action = [primary]
    if complement_product_id:
        comp = db.get(ProductModel, complement_product_id)
        if comp:
            products_for_action.append(comp)

    # 1. Determine recent weekly units sold for primary product
    declining_list = detect_declining_sales(db, merchant_id, window_days=14)
    primary_declining = next((d for d in declining_list if d["product_id"] == primary.id), None)
    if primary_declining:
        weekly_units = primary_declining["recent_weekly_units"]
    else:
        # Fallback query directly on sales records
        today = datetime.now(timezone.utc).date()
        recent_sum = (
            db.query(func.coalesce(func.sum(SalesRecordModel.units_sold), 0))
            .filter(
                SalesRecordModel.merchant_id == merchant_id,
                SalesRecordModel.product_id == primary.id,
                SalesRecordModel.date >= today - timedelta(days=14),
            )
            .scalar()
        )
        weekly_units = round(float(recent_sum or 0) / 2.0, 1) or 1.0

    # 2. Build gate models
    gate_products = [
        ProductForGrowthGate(
            id=p.id,
            price=p.price,
            cost=p.cost,
            stock=p.stock,
            status=p.status,
        )
        for p in products_for_action
    ]

    # 3. Calculate exact discount exposure (§8.3)
    exposure = calculate_discount_exposure(
        weekly_units=weekly_units,
        campaign_duration_weeks=campaign_duration_weeks,
        products=gate_products,
        discount_pct=discount_pct,
    )

    action_gate = ActionForGrowthGate(
        type="discount_bundle",
        discount_pct=discount_pct,
        campaign_duration_weeks=campaign_duration_weeks,
        estimated_discount_exposure=exposure,
        products=gate_products,
        audience="configured_demo_audience",
    )

    # 4. Fetch current merchant rules
    merchant = db.get(MerchantModel, merchant_id)
    rules_model = merchant.rules if merchant else None
    rules_gate = MerchantRulesForGrowthGate(
        growth_actions_enabled=rules_model.growth_actions_enabled if rules_model else False,
        max_ai_discount_pct=rules_model.max_ai_discount_pct if rules_model else 0.0,
        min_margin_pct=rules_model.min_margin_pct if rules_model else 10.0,
        growth_approval_threshold_amount=rules_model.growth_approval_threshold_amount if rules_model else None,
    )

    # 5. Evaluate deterministic growth policy gate
    policy_outcome, policy_reasons = growth_policy_gate(action_gate, rules_gate)

    # 6. Status determination (§8.4)
    # new -> blocked | pending_approval (allowed executes autonomously)
    if policy_outcome == BLOCKED:
        status = "blocked"
    elif policy_outcome == REQUIRES_APPROVAL:
        status = "pending_approval"
    else:
        status = "pending_approval"  # or ready for autonomous execution in phase 4

    product_names = [p.name for p in products_for_action]
    generated_title = title or (
        f"{int(discount_pct)}% Off Bundle: {' + '.join(product_names)}"
        if len(product_names) > 1
        else f"{int(discount_pct)}% Off Promotion: {product_names[0]}"
    )

    return {
        "merchant_id": merchant_id,
        "opportunity_type": opportunity_type,
        "title": generated_title,
        "evidence": {
            "primary_product_id": primary.id,
            "primary_product_name": primary.name,
            "weekly_sales_pace": weekly_units,
            "products_considered": [p.id for p in products_for_action],
            "exposure_formula": f"{weekly_units} units/wk × {campaign_duration_weeks} wk × ₹{sum(p.price for p in products_for_action):,.0f} × {discount_pct}%",
        },
        "recommended_action": {
            "type": "discount_bundle",
            "product_ids": [p.id for p in products_for_action],
            "discount_pct": discount_pct,
            "campaign_duration_weeks": campaign_duration_weeks,
            "audience": "configured_demo_audience",
        },
        "estimated_discount_exposure": exposure,
        "policy_outcome": policy_outcome,
        "policy_reasons": policy_reasons,
        "status": status,
    }
