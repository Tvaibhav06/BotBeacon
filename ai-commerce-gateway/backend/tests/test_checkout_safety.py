"""
Phase 2/6 tests — Critical safety tests for the checkout tool (§14).

"The single most important test in the whole system:"
checkout NEVER calls the Razorpay client when policy_decision.approved == False.

Phase 6 updates:
  - approved path now returns status="pending_payment" (not "approved_paid")
  - Razorpay import is inside the approved branch (never reached on blocked path)
  - write_audit_event is mocked so these tests run without a live DB
"""
import pytest
from unittest.mock import MagicMock, patch, call

from app.mcp.tools.checkout import checkout


def _make_cart(cart_id: str = "cart_test", total: float = 5998.0) -> MagicMock:
    cart = MagicMock()
    cart.id = cart_id
    cart.merchant_id = "merchant_velocity_sports"
    cart.buyer_id = "demo-buyer-1"
    cart.total = total
    return cart


def _make_policy_decision(pd_id: str = "pd_test", approved: bool = True) -> MagicMock:
    pd = MagicMock()
    pd.id = pd_id
    pd.cart_id = "cart_test"
    pd.approved = approved
    return pd


def _db_get(cart: MagicMock, pd: MagicMock):
    """Returns a db.get side_effect that routes by model name."""
    def _get(model, id):
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        if "Cart" in name and "Item" not in name:
            return cart
        return pd
    return _get


# ---------------------------------------------------------------------------
# THE CRITICAL SAFETY TEST (§14)
# ---------------------------------------------------------------------------

class TestCheckoutSafetyGate:

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_blocked_decision_never_calls_razorpay(self, mock_session_local, mock_audit):
        """
        THE most important test.
        When policy_decision.approved == False:
          - status must be "blocked"
          - razorpay_order_id must be None
          - Razorpay client must NEVER be instantiated or called.
        We verify this by ensuring create_order is never called on the blocked path.
        """
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.side_effect = _db_get(_make_cart(), _make_policy_decision(approved=False))

        # create_order lives inside razorpay_client — patch it there.
        # The blocked path uses a local import so we ensure the module is loaded first.
        import app.integrations.razorpay_client as rzp_mod
        with patch.object(rzp_mod, "create_order") as mock_create_order:
            result = checkout(cart_id="cart_test", policy_decision_id="pd_test")

        assert result["status"] == "blocked"
        assert result["razorpay_order_id"] is None
        # create_order must NEVER have been called on the blocked path
        mock_create_order.assert_not_called()

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_blocked_result_has_null_razorpay_order_id(self, mock_session_local, mock_audit):
        """
        razorpay_order_id must be literally None (not "" or omitted) when blocked. §5 MUST.
        """
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.side_effect = _db_get(_make_cart(total=8999.0), _make_policy_decision(approved=False))

        result = checkout(cart_id="cart_test", policy_decision_id="pd_test")

        assert result["status"] == "blocked"
        assert "razorpay_order_id" in result
        assert result["razorpay_order_id"] is None

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_approved_decision_returns_order_id(self, mock_session_local, mock_audit):
        """
        Approved decision: checkout must return a real razorpay_order_id
        and status="pending_payment" (real Razorpay order — Phase 6).
        """
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.side_effect = _db_get(_make_cart(total=5998.0), _make_policy_decision(approved=True))

        import app.integrations.razorpay_client as rzp_mod
        fake_order = {"id": "order_test_abc123", "amount": 599800, "currency": "INR"}
        with patch.object(rzp_mod, "create_order", return_value=fake_order):
            result = checkout(cart_id="cart_test", policy_decision_id="pd_test")

        assert result["status"] == "pending_payment"
        assert result["razorpay_order_id"] == "order_test_abc123"

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_approved_amount_converted_to_paise(self, mock_session_local, mock_audit):
        """
        Amount must be converted to paise (× 100) when calling Razorpay.
        ₹5,998 → 599800 paise.
        """
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.side_effect = _db_get(_make_cart(total=5998.0), _make_policy_decision(approved=True))

        captured_calls: list = []

        def fake_create_order(amount_paise, receipt_id, **kwargs):
            captured_calls.append(amount_paise)
            return {"id": "order_rz_xyz", "amount": amount_paise}

        import app.integrations.razorpay_client as rzp_mod
        with patch.object(rzp_mod, "create_order", side_effect=fake_create_order):
            checkout(cart_id="cart_test", policy_decision_id="pd_test")

        assert captured_calls == [599800], f"Expected 599800 paise, got {captured_calls}"

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_checkout_rejects_missing_cart(self, mock_session_local, mock_audit):
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.return_value = None

        result = checkout(cart_id="nonexistent_cart", policy_decision_id="pd_test")

        assert "error" in result

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_checkout_rejects_missing_policy_decision(self, mock_session_local, mock_audit):
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.side_effect = _db_get(_make_cart(), None)  # type: ignore[arg-type]

        result = checkout(cart_id="cart_test", policy_decision_id="pd_nonexistent")

        assert "error" in result


# ---------------------------------------------------------------------------
# §5 Invariant: blocked status → razorpay_order_id is always None
# ---------------------------------------------------------------------------

class TestCheckoutInvariants:

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_invariant_blocked_means_no_razorpay_order(self, mock_session_local, mock_audit):
        """
        Invariant: whenever result['status'] == 'blocked',
        result['razorpay_order_id'] MUST be None.
        Tested across several amounts to prove it's not amount-dependent.
        """
        for total in [1.0, 6000.0, 8999.0, 99999.0]:
            db = MagicMock()
            mock_session_local.return_value = db
            db.get.side_effect = _db_get(_make_cart(total=total), _make_policy_decision(approved=False))

            result = checkout(cart_id="cart_test", policy_decision_id="pd_test")
            assert result["status"] == "blocked", f"Expected blocked for total={total}"
            assert result["razorpay_order_id"] is None, (
                f"razorpay_order_id must be None when blocked (total={total})"
            )

    @patch("app.mcp.tools.checkout.write_audit_event")
    @patch("app.mcp.tools.checkout.SessionLocal")
    def test_blocked_audit_event_records_never_called(self, mock_session_local, mock_audit):
        """
        The 'payment' audit event for a blocked transaction must record
        razorpay_order_id=None and explain Razorpay was never called.
        """
        db = MagicMock()
        mock_session_local.return_value = db
        db.get.side_effect = _db_get(_make_cart(), _make_policy_decision(approved=False))

        checkout(cart_id="cart_test", policy_decision_id="pd_test")

        # write_audit_event must have been called once for the blocked payment stage
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["stage"] == "payment"
        assert call_kwargs["result"]["razorpay_order_id"] is None
        assert "never" in call_kwargs["result"]["reason"].lower()
