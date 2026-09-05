"""
Razorpay test-mode client — Phase 6.

Security rules:
  - RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are loaded from backend settings only.
  - They are NEVER passed to frontend, buyer-client, or MCP responses.
  - The frontend receives only the KEY_ID (public) via POST /api/payments/config.
  - The KEY_SECRET stays server-side for HMAC signature verification only.

Responsibilities:
  1. create_order(amount_paise, receipt_id) — create a Razorpay test-mode Order.
  2. verify_payment_signature(order_id, payment_id, signature) — HMAC-SHA256 check.
  3. fetch_payment(payment_id) — fetch payment details for amount/order verification.
"""
from __future__ import annotations

import hashlib
import hmac

import razorpay

from app.core.config import get_settings
from app.core.logging import logger


def _client() -> razorpay.Client:
    """Return a lazily-created Razorpay client using settings credentials."""
    s = get_settings()
    client = razorpay.Client(auth=(s.RAZORPAY_KEY_ID, s.RAZORPAY_KEY_SECRET))
    
    # Inject a default timeout so network hangs don't freeze the backend
    original_request = client.session.request
    def timeout_request(*args, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = 10
        return original_request(*args, **kwargs)
    
    client.session.request = timeout_request
    return client


def create_order(amount_paise: int, receipt_id: str, currency: str = "INR") -> dict:
    """
    Create a Razorpay test-mode Order.

    Args:
        amount_paise: Amount in paise (₹1 = 100 paise). Must be integer.
        receipt_id:   Merchant-side transaction/receipt ID for correlation.
        currency:     ISO 4217 currency code (default: "INR").

    Returns:
        Razorpay order dict with at minimum: id, amount, currency, status.

    Raises:
        Exception: propagates Razorpay API errors to caller for audit logging.
    """
    client = _client()
    order_data = {
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt_id,
        "payment_capture": 1,   # auto-capture on success
    }
    order = client.order.create(data=order_data)
    logger.info("razorpay | order_created order_id=%s amount_paise=%d", order["id"], amount_paise)
    return order


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify the HMAC-SHA256 signature sent by Razorpay Checkout.js on payment success.

    The signature is: HMAC_SHA256(key=KEY_SECRET, msg="{order_id}|{payment_id}")

    Returns True only if the computed digest matches the provided signature exactly.
    Any mismatch must be treated as a potential replay/tamper attack — do not accept.
    """
    s = get_settings()
    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        s.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    match = hmac.compare_digest(expected, razorpay_signature)
    logger.info(
        "razorpay | signature_verify order_id=%s payment_id=%s match=%s",
        razorpay_order_id, razorpay_payment_id, match,
    )
    return match


def fetch_payment(payment_id: str) -> dict:
    """
    Fetch payment details from Razorpay for server-side amount verification.

    Returns the payment dict. Key fields used by verification:
      - amount   (in paise)
      - order_id (must match the expected order_id)
      - status   ("captured" for a successful payment)
    """
    client = _client()
    payment = client.payment.fetch(payment_id)
    logger.info(
        "razorpay | payment_fetched payment_id=%s order_id=%s status=%s amount_paise=%s",
        payment_id,
        payment.get("order_id"),
        payment.get("status"),
        payment.get("amount"),
    )
    return payment
