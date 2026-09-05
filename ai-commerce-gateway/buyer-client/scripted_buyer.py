"""
scripted_buyer.py — Phase 3: Gemini-backed decision engine.
Replaces the Phase 2 naive cheapest-product selection.

Usage:
    # Demo scenario 1 — APPROVED (§11 golden path)
    python scripted_buyer.py --intent "Find me running shoes under 6000"

    # Demo scenario 2 — BLOCKED by mandate (§11 golden blocked path)
    # Gemini needs enough context to select prod_002 (Velocity Pro Premium, Rs 8999)
    # "Buy the 8999 Velocity Pro Premium footwear" reliably targets prod_002
    python scripted_buyer.py --intent "Buy the 8999 Velocity Pro Premium footwear"

    python scripted_buyer.py  # default demo intent

Architectural invariant: zero backend imports.
All Gateway communication is through the 5 MCP tool calls only.

NOTE: MCP transport is currently SSE (MCP 1.2.0).
TODO: Migrate to Streamable HTTP when mcp>=1.3.0 is available — no tool-contract changes needed.
"""
from __future__ import annotations

import argparse
import json
import sys

from decision_engine import run_decision_engine, EngineResult
from mcp_client import MCPClient

MERCHANT_ID = "merchant_velocity_sports"
BUYER_ID = "demo-buyer-1"
MANDATE_ID = "mandate_demo_buyer_1"
MANDATE_MAX = 6000.0
MANDATE_CATEGORIES = ["footwear", "accessories"]


def assemble_receipt(result: EngineResult) -> dict:
    """
    Assemble the full DecisionReceipt payload from EngineResult.
    Mirrors the §5 DecisionReceipt schema.
    """
    txn = result.transaction or {}
    status = txn.get("status", "unknown")
    is_blocked = status == "blocked"

    selected_item = None
    if result.selected:
        selected_item = {
            "product_id": result.selected["id"],
            "quantity": 1,
            "unit_price": result.selected["price"],
            "role": "primary",
        }

    upsell_item = None
    if result.upsell and not is_blocked:
        upsell_item = {
            "product_id": result.upsell["id"],
            "quantity": 1,
            "unit_price": result.upsell["price"],
            "role": "upsell",
        }

    cart = result.cart or {}
    final_total = cart.get("total", result.selected["price"] if result.selected else 0.0)

    pd = result.policy_decision or {}

    if is_blocked:
        reasons = pd.get("reasons", [])
        authorization_status = f"Blocked — {reasons[0]}" if reasons else "Blocked"
        payment_status = "Razorpay was never called."
    else:
        authorization_status = "Within buyer limit"
        rz_order_id = txn.get("razorpay_order_id", "")
        payment_status = (
            f"Razorpay order created: {rz_order_id} — pending frontend payment confirmation"
            if rz_order_id else "Razorpay order created (pending payment)"
        )

    return {
        "transaction_id": txn.get("id", ""),
        "customer_request": result.intent,
        "ai_considered_count": result.considered_count,
        "selected": selected_item,
        "why": result.why,
        "upsell": upsell_item,
        "final_total": final_total,
        "authorization_status": authorization_status,
        "payment_status": payment_status,
        # Extra debug fields (not in §5 schema but useful during dev)
        "_structured_filter": result.structured_filter,
        "_transaction_status": status,
        "_razorpay_order_id": txn.get("razorpay_order_id"),
        "_policy_approved": pd.get("approved"),
        "_policy_reasons": pd.get("reasons", []),
    }


def run_buyer(intent: str, mcp: MCPClient) -> dict:
    """
    Full buyer flow:
      decision_engine → build_cart → check_policy → checkout → receipt
    """
    print(f"\n{'='*60}")
    print(f"  AI Commerce Buyer — Phase 3 (Gemini decision engine)")
    print(f"  Intent: {intent!r}")
    print(f"{'='*60}\n")

    # ── Decision Engine (§8.1) ──────────────────────────────────────────
    result = run_decision_engine(
        intent=intent,
        mcp=mcp,
        mandate_max_amount=MANDATE_MAX,
        mandate_category_scope=MANDATE_CATEGORIES,
        upsell_enabled=True,
        preferred_categories=["footwear", "accessories"],
    )

    if result.selected is None:
        print("[buyer] No product selected — aborting.")
        return {"error": "No product selected", "intent": intent}

    # ── Build Cart ──────────────────────────────────────────────────────
    print("\n[buyer] Building cart via MCP...")
    items = [{"product_id": result.selected["id"], "quantity": 1, "role": "primary"}]
    if result.upsell:
        items.append({"product_id": result.upsell["id"], "quantity": 1, "role": "upsell"})

    cart = mcp.build_cart(
        buyer_id=BUYER_ID,
        merchant_id=MERCHANT_ID,
        items=items,
        reasoning={
            "customer_request": result.intent,
            "considered_count": result.considered_count,
            "why": result.why,
        }
    )
    if "error" in cart:
        print(f"[buyer] Cart error: {cart['error']}")
        return cart

    result.cart = cart
    print(f"[buyer]   Cart {cart['id']} | total ₹{cart['total']}")

    # ── Check Policy ────────────────────────────────────────────────────
    print("[buyer] Checking policy via MCP...")
    policy = mcp.check_policy(cart_id=cart["id"], mandate_id=MANDATE_ID)
    if "error" in policy:
        print(f"[buyer] Policy error: {policy['error']}")
        return policy

    result.policy_decision = policy
    approved_icon = "✓" if policy.get("approved") else "✗"
    print(f"[buyer]   {approved_icon} approved={policy.get('approved')} | {policy.get('reasons', [])}")

    # ── Checkout ────────────────────────────────────────────────────────
    # checkout() is called for BOTH approved and blocked decisions (§8.1 step 5).
    # For blocked decisions, checkout() creates a blocked TransactionResult
    # without instantiating or calling Razorpay.
    print("[buyer] Checkout via MCP...")
    txn = mcp.checkout(cart_id=cart["id"], policy_decision_id=policy["id"])
    if "error" in txn:
        print(f"[buyer] Checkout error: {txn['error']}")
        return txn

    result.transaction = txn
    status_icon = "✓" if txn["status"] != "blocked" else "✗ BLOCKED"
    print(f"[buyer]   {status_icon} status={txn['status']} | razorpay_order_id={txn.get('razorpay_order_id')}")
    if txn["status"] == "blocked":
        print(f"[buyer]   Razorpay was never called.")

    # ── Assemble Receipt ────────────────────────────────────────────────
    receipt = assemble_receipt(result)

    print(f"\n{'='*60}")
    print("  DECISION RECEIPT:")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    print(f"{'='*60}\n")

    return receipt


def main():
    parser = argparse.ArgumentParser(description="AI Commerce Gateway — scripted buyer (Phase 3)")
    parser.add_argument(
        "--intent",
        default="Find me running shoes under 6000",
        help="Buyer intent string",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,  # defaults to MCP_BASE_URL env var (http://localhost:8001/mcp)
        help="MCP server base URL (default: MCP_BASE_URL env var or http://localhost:8001/mcp)",
    )
    args = parser.parse_args()

    mcp = MCPClient(base_url=args.mcp_url) if args.mcp_url else MCPClient()
    receipt = run_buyer(args.intent, mcp)
    sys.exit(0 if "error" not in receipt else 1)


if __name__ == "__main__":
    main()
