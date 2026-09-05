"""
checkout MCP tool — §6.

CRITICAL SAFETY RULE (unit-tested in Phase 2 and Phase 6):
  checkout re-checks policy_decision.approved == True ITSELF, immediately
  before touching the Razorpay client.
  It does NOT trust that the caller already checked.
  If approved == False:
    → status = "blocked"
    → razorpay_order_id = None   ← MUST be None, always
    → Razorpay client is NEVER instantiated

This single check is what makes "Razorpay was never called" a true
statement rather than a UI-only claim.  See §6 and §14.

Input:  { "cart_id": str, "policy_decision_id": str }
Output: full TransactionResult object (§5)
"""
from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models import CartModel, PolicyDecisionModel, TransactionModel
from app.audit.logger import write_audit_event
from app.core.logging import logger


def checkout(cart_id: str, policy_decision_id: str) -> dict:
    """
    Phase 6: Real Razorpay test-mode Order creation on approved path.

    Approved path:
      1. Re-check policy_decision.approved (MUST be True — not trusted from caller).
      2. Create Razorpay test-mode Order via razorpay_client.create_order().
      3. Persist TransactionModel with status="pending_payment".
      4. Write "payment" audit event.
      5. Return transaction + razorpay_order_id for frontend Checkout.js.

    Blocked path:
      1. Re-check policy_decision.approved == False.
      2. Persist TransactionModel with status="blocked", razorpay_order_id=None.
      3. Write "payment" audit event (with blocked=True).
      4. Return blocked result. Razorpay is never instantiated.
    """
    db = SessionLocal()
    try:
        cart = db.get(CartModel, cart_id)
        if not cart:
            return {"error": f"Cart '{cart_id}' not found"}

        policy_decision = db.get(PolicyDecisionModel, policy_decision_id)
        if not policy_decision:
            return {"error": f"PolicyDecision '{policy_decision_id}' not found"}

        # ---------------------------------------------------------------
        # SAFETY GATE — re-checked here, never trusted from the caller.
        # This is the invariant tested by the critical unit test in §14.
        # ---------------------------------------------------------------
        if not policy_decision.approved:
            blocked_txn = TransactionModel(
                id=f"txn_{uuid.uuid4().hex[:12]}",
                cart_id=cart_id,
                merchant_id=cart.merchant_id,
                buyer_id=cart.buyer_id,
                razorpay_order_id=None,   # MUST be None when blocked — §5
                status="blocked",
                amount=cart.total,
                customer_request="",
                receipt_data={},
            )
            db.add(blocked_txn)
            db.commit()

            # Audit: payment stage — blocked
            write_audit_event(
                db,
                merchant_id=cart.merchant_id,
                stage="payment",
                actor="buyer_agent",
                payload={
                    "cart_id": cart_id,
                    "policy_decision_id": policy_decision_id,
                    "amount": cart.total,
                    "blocked": True,
                },
                result={
                    "status": "blocked",
                    "razorpay_order_id": None,
                    "reason": "policy_decision.approved == False — Razorpay was never called",
                },
                transaction_id=blocked_txn.id,
                cart_id=cart_id,
            )

            return {
                "id": blocked_txn.id,
                "cart_id": cart_id,
                "razorpay_order_id": None,
                "status": "blocked",
                "amount": cart.total,
            }

        # ---------------------------------------------------------------
        # APPROVED PATH — create real Razorpay test-mode Order
        # Import here (not at module top) so the Razorpay client is only
        # instantiated on the approved path — blocked path never reaches it.
        # ---------------------------------------------------------------
        from app.integrations.razorpay_client import create_order  # noqa: PLC0415

        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        amount_paise = int(round(cart.total * 100))   # ₹ → paise

        try:
            rz_order = create_order(amount_paise=amount_paise, receipt_id=txn_id)
            rz_order_id: str = rz_order["id"]
        except Exception as exc:
            logger.error("razorpay | order_creation_failed cart_id=%s error=%s", cart_id, exc)
            # Write failed audit event before returning
            failed_txn = TransactionModel(
                id=txn_id,
                cart_id=cart_id,
                merchant_id=cart.merchant_id,
                buyer_id=cart.buyer_id,
                razorpay_order_id=None,
                status="failed",
                amount=cart.total,
                customer_request="",
                receipt_data={},
            )
            db.add(failed_txn)
            db.commit()
            write_audit_event(
                db,
                merchant_id=cart.merchant_id,
                stage="payment",
                actor="buyer_agent",
                payload={"cart_id": cart_id, "amount": cart.total},
                result={"status": "failed", "error": str(exc)},
                transaction_id=txn_id,
                cart_id=cart_id,
            )
            return {"error": f"Razorpay order creation failed: {exc}"}

        txn = TransactionModel(
            id=txn_id,
            cart_id=cart_id,
            merchant_id=cart.merchant_id,
            buyer_id=cart.buyer_id,
            razorpay_order_id=rz_order_id,
            status="pending_payment",   # transitions to approved_paid after verify
            amount=cart.total,
            customer_request="",
            receipt_data={},
        )
        db.add(txn)
        db.commit()

        # Audit: payment stage — order created, awaiting frontend confirmation
        write_audit_event(
            db,
            merchant_id=cart.merchant_id,
            stage="payment",
            actor="buyer_agent",
            payload={
                "cart_id": cart_id,
                "policy_decision_id": policy_decision_id,
                "amount": cart.total,
                "amount_paise": amount_paise,
            },
            result={
                "status": "pending_payment",
                "razorpay_order_id": rz_order_id,
            },
            transaction_id=txn_id,
            cart_id=cart_id,
        )

        return {
            "id": txn_id,
            "cart_id": cart_id,
            "razorpay_order_id": rz_order_id,
            "status": "pending_payment",
            "amount": cart.total,
        }
    finally:
        db.close()
