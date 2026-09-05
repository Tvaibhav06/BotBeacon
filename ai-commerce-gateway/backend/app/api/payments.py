"""
Payment endpoints — Phase 6.

GET  /api/payments/config            — returns public Razorpay KEY_ID for Checkout.js
POST /api/payments/verify            — server-side HMAC + amount verification after Checkout.js success

Security:
  - RAZORPAY_KEY_SECRET is never returned to the client.
  - Signature verification is HMAC-SHA256 server-side only.
  - Payment amount is verified against the stored transaction amount — not the frontend's claim.
  - A mismatch is logged and kept visible; it never silently becomes a success.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.merchants import get_current_merchant
from app.core.config import get_settings
from app.db.session import get_db
from app.models import MerchantModel, TransactionModel
from app.schemas import (
    PaymentConfigResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
)
from app.audit.logger import write_audit_event
from app.core.logging import logger

router = APIRouter()


@router.get(
    "/payments/config",
    response_model=PaymentConfigResponse,
    tags=["payments"],
)
def get_payment_config(
    current: MerchantModel = Depends(get_current_merchant),
):
    """
    Return the public Razorpay KEY_ID needed to initialise Checkout.js on the frontend.
    KEY_SECRET is never included in any response — server-side only.
    """
    s = get_settings()
    if not s.RAZORPAY_KEY_ID:
        raise HTTPException(status_code=503, detail="Razorpay not configured")
    return PaymentConfigResponse(key_id=s.RAZORPAY_KEY_ID)


@router.post(
    "/payments/verify",
    response_model=PaymentVerifyResponse,
    tags=["payments"],
)
def verify_payment_callback(
    body: PaymentVerifyRequest,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    §8.4 — server-side verification after Checkout.js fires payment.success.

    Steps (must ALL pass before marking transaction as approved_paid):
      1. Lookup transaction by razorpay_order_id — must exist and belong to this merchant.
      2. HMAC-SHA256 signature verification (KEY_SECRET never leaves server).
      3. Fetch payment from Razorpay API and verify order_id + amount match.
      4. Run verify_payment() pure function.
      5. On match=True: update status → approved_paid, store payment_id + signature.
      6. On match=False: keep status as failed/mismatch, log discrepancies.
      7. Write "verification" audit event in both cases.
    """
    from app.integrations.razorpay_client import verify_payment_signature, fetch_payment
    from app.engine.verification import verify_payment, PaymentForVerification

    # ── Step 1: Lookup transaction ────────────────────────────────────────────
    txn = (
        db.query(TransactionModel)
        .filter(TransactionModel.razorpay_order_id == body.razorpay_order_id)
        .filter(TransactionModel.merchant_id == current.id)
        .first()
    )
    if not txn:
        raise HTTPException(
            status_code=404,
            detail=f"No transaction found for order_id '{body.razorpay_order_id}'",
        )

    # Guard: don't re-verify an already-verified or blocked transaction
    if txn.status == "approved_paid":
        return PaymentVerifyResponse(
            transaction_id=txn.id,
            verified=True,
            status="approved_paid",
            discrepancies=[],
        )
    if txn.status == "blocked":
        raise HTTPException(status_code=400, detail="Transaction is blocked — cannot verify payment")

    discrepancies: list[str] = []

    # ── Step 2: HMAC signature verification ──────────────────────────────────
    sig_valid = verify_payment_signature(
        razorpay_order_id=body.razorpay_order_id,
        razorpay_payment_id=body.razorpay_payment_id,
        razorpay_signature=body.razorpay_signature,
    )
    if not sig_valid:
        discrepancies.append("HMAC signature verification failed — possible tamper/replay")

    # ── Step 3 + 4: Fetch payment from Razorpay and run verify_payment() ─────
    payment_data = None
    try:
        payment_data = fetch_payment(body.razorpay_payment_id)
        expected_paise = int(round(txn.amount * 100))
        pv = PaymentForVerification(
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_order_id=payment_data.get("order_id", ""),
            amount_paise=payment_data.get("amount", 0),
            status=payment_data.get("status", "unknown"),
        )
        _match, amount_discrepancies = verify_payment(pv, body.razorpay_order_id, expected_paise)
        discrepancies.extend(amount_discrepancies)
    except Exception as exc:
        logger.error("verification | fetch_payment_failed payment_id=%s error=%s",
                     body.razorpay_payment_id, exc)
        discrepancies.append(f"could not fetch payment from Razorpay: {exc}")

    # ── Step 5/6: Update transaction ──────────────────────────────────────────
    final_match = len(discrepancies) == 0
    new_status = "approved_paid" if final_match else "failed"

    txn.razorpay_payment_id = body.razorpay_payment_id
    txn.razorpay_signature  = body.razorpay_signature
    txn.status              = new_status
    db.commit()

    # ── Step 7: Verification audit event ─────────────────────────────────────
    write_audit_event(
        db,
        merchant_id=current.id,
        stage="verification",
        actor="system",
        payload={
            "razorpay_order_id":   body.razorpay_order_id,
            "razorpay_payment_id": body.razorpay_payment_id,
            "expected_amount":     txn.amount,
            "signature_valid":     sig_valid,
        },
        result={
            "match":          final_match,
            "status":         new_status,
            "discrepancies":  discrepancies,
        },
        transaction_id=txn.id,
        cart_id=txn.cart_id,
    )

    if not final_match:
        logger.warning(
            "verification | mismatch transaction_id=%s discrepancies=%s",
            txn.id, discrepancies,
        )

    return PaymentVerifyResponse(
        transaction_id=txn.id,
        verified=final_match,
        status=new_status,
        discrepancies=discrepancies,
    )
