"""
check_policy MCP tool — §6.
Phase 5: real Mandate Check (§8.2) + real Policy Gate (§8.3) wired.

Accepts either a stored mandate_id (resolved server-side against the Mandate table)
or an inline mandate object for testing.

Input:  { "cart_id": str, "mandate_id": str } OR { "cart_id": str, "mandate": {...} }
Output: full PolicyDecision object (§5)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.session import SessionLocal
from app.models import CartModel, CartItemModel, MandateModel, PolicyDecisionModel, ProductModel, MerchantRulesModel
from app.engine.mandate_check import (
    mandate_check,
    CartForCheck,
    CartItemForCheck,
    MandateForCheck,
)
from app.engine.policy_gate import (
    policy_gate,
    CartForGate,
    CartItemForGate,
    MerchantRulesForGate,
)
from app.audit.logger import write_audit_event


def check_policy(
    cart_id: str,
    mandate_id: str | None = None,
    mandate: dict[str, Any] | None = None,
) -> dict:
    """
    Phase 5: Real Mandate Check (§8.2) + real Policy Gate (§8.3).

    Resolution order for mandate:
      1. If `mandate` dict is provided, use it (for testing / inline override).
      2. Else resolve from DB using `mandate_id`.
      3. If neither is provided, return an error.
    """
    db = SessionLocal()
    try:
        # ── Resolve cart ────────────────────────────────────────────────
        cart = db.get(CartModel, cart_id)
        if not cart:
            return {"error": f"Cart '{cart_id}' not found"}

        # ── Resolve cart items with their product categories ────────────
        cart_items_db: list[CartItemModel] = (
            db.query(CartItemModel)
            .filter(CartItemModel.cart_id == cart_id)
            .all()
        )

        items_for_check: list[CartItemForCheck] = []
        for ci in cart_items_db:
            product = db.get(ProductModel, ci.product_id)
            category = product.category if product else "unknown"
            items_for_check.append(CartItemForCheck(
                product_id=ci.product_id,
                quantity=ci.quantity,
                unit_price=ci.unit_price,
                role=ci.role,
                category=category,
            ))

        cart_for_check = CartForCheck(
            id=cart.id,
            total=cart.total,
            items=items_for_check,
        )

        # ── Resolve mandate ──────────────────────────────────────────────
        mandate_for_check: MandateForCheck | None = None

        if mandate:
            # Inline mandate dict (for testing)
            expires_raw = mandate.get("expires_at")
            if isinstance(expires_raw, str):
                expires_dt = datetime.fromisoformat(expires_raw)
            elif isinstance(expires_raw, datetime):
                expires_dt = expires_raw
            else:
                expires_dt = datetime.now(timezone.utc).replace(year=9999)  # far future

            mandate_for_check = MandateForCheck(
                id=mandate.get("id", "inline"),
                buyer_id=mandate.get("buyer_id", cart.buyer_id),
                max_amount=float(mandate.get("max_amount", 0)),
                category_scope=mandate.get("category_scope", []),
                expires_at=expires_dt,
            )
        elif mandate_id:
            mandate_db = db.get(MandateModel, mandate_id)
            if not mandate_db:
                return {"error": f"Mandate '{mandate_id}' not found"}
            mandate_for_check = MandateForCheck(
                id=mandate_db.id,
                buyer_id=mandate_db.buyer_id,
                max_amount=mandate_db.max_amount,
                category_scope=mandate_db.category_scope,
                expires_at=mandate_db.expires_at,
            )
        else:
            return {"error": "Either mandate_id or inline mandate must be provided"}

        # ── §8.2 Mandate Check ───────────────────────────────────────────
        mc_passed, mc_reasons = mandate_check(cart_for_check, mandate_for_check)

        # ── Audit: mandate_check stage ───────────────────────────────────
        write_audit_event(
            db,
            merchant_id=cart.merchant_id,
            stage="mandate_check",
            actor="buyer_agent",
            payload={
                "cart_id": cart_id,
                "mandate_id": mandate_for_check.id,
                "cart_total": cart.total,
                "mandate_max": mandate_for_check.max_amount,
            },
            result={
                "passed": mc_passed,
                "reasons": mc_reasons,
            },
            cart_id=cart_id,
        )

        # ── §8.3 Policy Gate — resolve live product data for each item ───
        # Load merchant rules (fall back to defaults if no rules row yet)
        rules_row: MerchantRulesModel | None = (
            db.query(MerchantRulesModel)
            .filter(MerchantRulesModel.merchant_id == cart.merchant_id)
            .first()
        )
        gate_rules = MerchantRulesForGate(
            max_ai_discount_pct=rules_row.max_ai_discount_pct if rules_row else 0.0,
            min_margin_pct=rules_row.min_margin_pct if rules_row else 10.0,
            approval_threshold_amount=rules_row.approval_threshold_amount if rules_row else None,
        )

        # Build CartForGate: re-fetch live product data from DB (§8.3 "don't trust snapshot")
        gate_items: list[CartItemForGate] = []
        for ci in cart_items_db:
            product = db.get(ProductModel, ci.product_id)
            live_price = product.price if product else ci.unit_price
            live_cost  = product.cost  if product else 0.0
            live_stock = product.stock if product else 0
            gate_items.append(CartItemForGate(
                product_id=ci.product_id,
                quantity=ci.quantity,
                unit_price=ci.unit_price,
                role=ci.role,
                live_price=live_price,
                live_cost=live_cost,
                live_stock=live_stock,
                applied_discount_pct=0.0,   # no discounts in MVP (§11 has none)
            ))

        cart_for_gate = CartForGate(
            id=cart.id,
            total=cart.total,
            items=gate_items,
        )

        pg_passed, pg_reasons = policy_gate(cart_for_gate, gate_rules)

        # ── Audit: policy_gate stage ─────────────────────────────────────
        write_audit_event(
            db,
            merchant_id=cart.merchant_id,
            stage="policy_gate",
            actor="buyer_agent",
            payload={
                "cart_id": cart_id,
                "cart_total": cart.total,
                "approval_threshold": gate_rules.approval_threshold_amount,
                "min_margin_pct": gate_rules.min_margin_pct,
                "max_ai_discount_pct": gate_rules.max_ai_discount_pct,
            },
            result={
                "passed": pg_passed,
                "reasons": pg_reasons,
            },
            cart_id=cart_id,
        )

        # ── Combine: approved only if BOTH sub-checks pass ───────────────
        approved = mc_passed and pg_passed
        all_reasons = mc_reasons + pg_reasons  # each list is empty when the check passes

        pd_id = f"pd_{uuid.uuid4().hex[:12]}"
        decision = PolicyDecisionModel(
            id=pd_id,
            cart_id=cart_id,
            mandate_check_passed=mc_passed,
            mandate_check_reasons=mc_reasons,
            policy_check_passed=pg_passed,
            policy_check_reasons=pg_reasons,
            approved=approved,
            reasons=all_reasons,
        )
        db.add(decision)
        db.commit()

        return {
            "id": pd_id,
            "cart_id": cart_id,
            "mandate_check": {
                "passed": mc_passed,
                "reasons": mc_reasons,
            },
            "policy_check": {
                "passed": pg_passed,
                "reasons": pg_reasons,
            },
            "approved": approved,
            "reasons": all_reasons,
        }

    finally:
        db.close()
