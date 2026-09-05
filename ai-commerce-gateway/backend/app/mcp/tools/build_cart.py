"""
build_cart MCP tool — §6.
Snapshots prices at call time into CartItem.unit_price.
This snapshot is what Verification later checks against.

Input:  { "buyer_id": str, "merchant_id": str, "items": [{"product_id", "quantity", "role"}] }
Output: full Cart object (§5)
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from app.db.session import SessionLocal
from app.models import CartModel, CartItemModel, ProductModel, MerchantModel
from app.audit.logger import write_audit_event


def build_cart(
    buyer_id: str,
    merchant_id: str,
    items: list[dict[str, Any]],
    reasoning: Optional[dict[str, Any]] = None,
) -> dict:
    """
    Build a cart, snapshotting current prices.

    Each item dict: { product_id: str, quantity: int, role: "primary"|"upsell" }
    reasoning dict (optional): { customer_request, considered_count, why }

    Returns a Cart dict (§5) or an error dict if any product is unavailable.
    """
    db = SessionLocal()
    try:
        # Verify merchant has active passport
        merchant = db.get(MerchantModel, merchant_id)
        if not merchant or merchant.passport_status != "active":
            return {"error": f"Merchant '{merchant_id}' not found or passport not active"}

        cart_id = f"cart_{uuid.uuid4().hex[:12]}"
        total = 0.0
        cart_items: list[CartItemModel] = []
        item_dicts: list[dict] = []

        for item in items:
            product_id = item.get("product_id", "")
            quantity = int(item.get("quantity", 1))
            role = item.get("role", "primary")

            product = db.get(ProductModel, product_id)
            if not product or product.status != "active":
                return {"error": f"Product '{product_id}' not found or inactive"}
            if product.stock < quantity:
                return {"error": f"Insufficient stock for '{product_id}': need {quantity}, have {product.stock}"}

            # Snapshot price at build_cart time — §6
            unit_price = product.price
            line_total = unit_price * quantity
            total += line_total

            cart_item = CartItemModel(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                role=role,
            )
            cart_items.append(cart_item)
            item_dicts.append({
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "role": role,
            })

        cart = CartModel(
            id=cart_id,
            merchant_id=merchant_id,
            buyer_id=buyer_id,
            total=round(total, 2),
        )
        db.add(cart)
        for ci in cart_items:
            db.add(ci)
        db.commit()

        cart_dict = {
            "id": cart_id,
            "merchant_id": merchant_id,
            "buyer_id": buyer_id,
            "items": item_dicts,
            "total": round(total, 2),
        }

        # The AI's decision to cart these specific items represents the output of the decision engine.
        payload = {"requested_items": item_dicts}
        if reasoning:
            payload["reasoning"] = reasoning

        write_audit_event(
            db=db,
            merchant_id=merchant_id,
            stage="decision_engine",
            actor="buyer_agent",
            payload=payload,
            result={"cart": cart_dict},
            transaction_id=None,
            cart_id=cart_id,
        )

        return cart_dict
    finally:
        db.close()
