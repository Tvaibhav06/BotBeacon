"""
Phase 6 tests — Verification pure function (§8.4).

Pure function tests — no database, no MCP, no Razorpay network calls.
Tests the verify_payment() logic: status, order match, amount match.
"""
from __future__ import annotations

import pytest

from app.engine.verification import verify_payment, PaymentForVerification


def _payment(
    status: str = "captured",
    order_id: str = "order_test_001",
    amount_paise: int = 599800,
    payment_id: str = "pay_test_001",
) -> PaymentForVerification:
    return PaymentForVerification(
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
        amount_paise=amount_paise,
        status=status,
    )


# ── Happy path ────────────────────────────────────────────────────────────────

class TestVerifyPaymentHappyPath:

    def test_all_checks_pass_returns_match_true(self):
        """₹5,998 payment — all checks pass."""
        p = _payment(status="captured", order_id="order_123", amount_paise=599800)
        match, discrepancies = verify_payment(p, "order_123", 599800)
        assert match is True
        assert discrepancies == []

    def test_demo_scenario_1_amount(self):
        """₹5,998 = 599800 paise — the exact §11 demo happy path amount."""
        p = _payment(amount_paise=599800, order_id="order_demo")
        match, _ = verify_payment(p, "order_demo", 599800)
        assert match is True

    def test_small_amount_passes(self):
        p = _payment(amount_paise=49900, order_id="o1")  # ₹499
        match, _ = verify_payment(p, "o1", 49900)
        assert match is True


# ── Check 1: Status ───────────────────────────────────────────────────────────

class TestStatusCheck:

    def test_failed_status_fails(self):
        p = _payment(status="failed")
        match, discrepancies = verify_payment(p, "order_123", 599800)
        assert match is False
        assert any("status" in d.lower() for d in discrepancies)

    def test_created_status_fails(self):
        p = _payment(status="created")
        match, discrepancies = verify_payment(p, "order_123", 599800)
        assert match is False

    def test_authorized_status_fails(self):
        """'authorized' is not 'captured' — must fail."""
        p = _payment(status="authorized")
        match, discrepancies = verify_payment(p, "order_123", 599800)
        assert match is False

    def test_status_reason_mentions_captured(self):
        p = _payment(status="failed")
        _, discrepancies = verify_payment(p, "order_123", 599800)
        assert any("captured" in d for d in discrepancies), \
            f"Reason should mention 'captured': {discrepancies}"


# ── Check 2: Order ID match ───────────────────────────────────────────────────

class TestOrderIdCheck:

    def test_wrong_order_id_fails(self):
        p = _payment(order_id="order_WRONG")
        match, discrepancies = verify_payment(p, "order_CORRECT", 599800)
        assert match is False
        assert any("order_id" in d.lower() or "order" in d.lower() for d in discrepancies)

    def test_order_id_reason_shows_both_ids(self):
        p = _payment(order_id="order_A")
        _, discrepancies = verify_payment(p, "order_B", 599800)
        assert any("order_A" in d for d in discrepancies), f"Reason missing got order_id: {discrepancies}"
        assert any("order_B" in d for d in discrepancies), f"Reason missing expected order_id: {discrepancies}"

    def test_correct_order_id_passes(self):
        p = _payment(order_id="order_XYZ")
        match, _ = verify_payment(p, "order_XYZ", 599800)
        assert match is True


# ── Check 3: Amount match ─────────────────────────────────────────────────────

class TestAmountCheck:

    def test_one_paise_over_fails(self):
        """Even ₹0.01 over must be detected — no silent over-charge."""
        p = _payment(amount_paise=599801)
        match, discrepancies = verify_payment(p, "order_123", 599800)
        assert match is False
        assert any("amount" in d.lower() or "mismatch" in d.lower() for d in discrepancies)

    def test_one_paise_under_fails(self):
        """Even ₹0.01 under must be detected — partial payment is a discrepancy."""
        p = _payment(amount_paise=599799)
        match, discrepancies = verify_payment(p, "order_123", 599800)
        assert match is False

    def test_amount_reason_shows_inr_values(self):
        """Discrepancy reason must show ₹ values for human readability."""
        p = _payment(amount_paise=900000)  # ₹9,000 charged
        _, discrepancies = verify_payment(p, "order_123", 599800)  # ₹5,998 expected
        assert any("₹" in d or "9,000" in d or "5,998" in d for d in discrepancies), \
            f"Reason should show ₹ amounts: {discrepancies}"

    def test_exact_amount_match_passes(self):
        p = _payment(amount_paise=899900, order_id="order_123")  # ₹8,999, matching order_id
        match, _ = verify_payment(p, "order_123", 899900)
        assert match is True


# ── Multiple failures ─────────────────────────────────────────────────────────

class TestMultipleFailures:

    def test_all_three_checks_fail(self):
        """Wrong status + wrong order + wrong amount → three discrepancies."""
        p = _payment(status="failed", order_id="order_WRONG", amount_paise=100)
        match, discrepancies = verify_payment(p, "order_RIGHT", 599800)
        assert match is False
        assert len(discrepancies) == 3, f"Expected 3 discrepancies, got {len(discrepancies)}: {discrepancies}"

    def test_status_and_amount_fail(self):
        p = _payment(status="created", order_id="order_X", amount_paise=1000)
        match, discrepancies = verify_payment(p, "order_X", 599800)
        assert match is False
        assert len(discrepancies) == 2  # status + amount

    def test_empty_discrepancies_on_success(self):
        p = _payment()
        match, discrepancies = verify_payment(p, "order_test_001", 599800)
        assert match is True
        assert discrepancies == []
