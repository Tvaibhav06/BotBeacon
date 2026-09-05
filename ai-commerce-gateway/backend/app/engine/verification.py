"""
Verification — §8.4.
Pure function: quoted vs. charged/fulfilled post-payment check.

Checks (all must pass for match=True):
  1. Signature:    caller must have already verified HMAC before calling this.
                   This function checks the payment/order relationship and amounts.
  2. Order match:  razorpay_payment.order_id == expected_order_id
  3. Amount match: razorpay_payment.amount (paise) == expected_amount_paise
  4. Status:       razorpay_payment.status == "captured"

Returns (match: bool, discrepancies: list[str]).
discrepancies is empty when match=True.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PaymentForVerification:
    """Razorpay payment fields needed for verification — resolved before calling."""
    razorpay_payment_id: str
    razorpay_order_id: str      # from the payment object
    amount_paise: int           # from the payment object
    status: str                 # "captured", "failed", etc.


def verify_payment(
    payment: PaymentForVerification,
    expected_order_id: str,
    expected_amount_paise: int,
) -> tuple[bool, list[str]]:
    """
    §8.4 verification — compare what was charged vs. what was approved.

    Args:
        payment:               Razorpay payment data fetched server-side.
        expected_order_id:     The order_id stored in TransactionModel.
        expected_amount_paise: cart.total converted to paise (round(total * 100)).

    Returns:
        (match: bool, discrepancies: list[str])
        discrepancies is empty when match=True.
        Each failed check appends one human-readable discrepancy string.
    """
    discrepancies: list[str] = []

    # Check 1: payment is in captured state
    if payment.status != "captured":
        discrepancies.append(
            f"payment status is '{payment.status}', expected 'captured'"
        )

    # Check 2: payment belongs to the expected order
    if payment.razorpay_order_id != expected_order_id:
        discrepancies.append(
            f"payment order_id mismatch: got '{payment.razorpay_order_id}', "
            f"expected '{expected_order_id}'"
        )

    # Check 3: amount charged matches amount approved
    if payment.amount_paise != expected_amount_paise:
        charged_inr   = payment.amount_paise / 100
        expected_inr  = expected_amount_paise / 100
        discrepancies.append(
            f"amount mismatch: charged ₹{charged_inr:,.2f} "
            f"!= approved ₹{expected_inr:,.2f}"
        )

    match = len(discrepancies) == 0
    return match, discrepancies
