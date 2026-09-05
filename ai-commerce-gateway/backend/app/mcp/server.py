"""
MCP Server — §6, §4.
Transport: SSE (MCP 1.2.0 — closest available to the "Streamable HTTP" specified in §3).
Build Plan §3 specifies Streamable HTTP transport; MCP 1.2.0 ships SSE transport only.
SSE satisfies the same architectural intent: the Gateway runs as an independently-reachable
HTTP service, not a subprocess of one client.  Streamable HTTP transport is available in
MCP 1.3+ and can be swapped in with no tool-contract changes.

The MCP server is mounted on the main FastAPI app at /mcp/sse and /mcp/messages/.
This is the ONLY agent-facing surface. Buyer clients talk here and ONLY here.

5 tools exposed (exactly as specified in §6):
  search_catalog, get_product, build_cart, check_policy, checkout
"""
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.logging import logger
from app.mcp.tools.search_catalog import search_catalog as _search_catalog
from app.mcp.tools.get_product import get_product as _get_product
from app.mcp.tools.build_cart import build_cart as _build_cart
from app.mcp.tools.check_policy import check_policy as _check_policy
from app.mcp.tools.checkout import checkout as _checkout

# -------------------------------------------------------------------------
# FastMCP instance
# -------------------------------------------------------------------------

mcp = FastMCP("AI Commerce Gateway")


# -------------------------------------------------------------------------
# Tool 1 — search_catalog
# Deterministic. No LLM. Category / keyword / price filtering only.
# -------------------------------------------------------------------------

@mcp.tool()
def search_catalog(
    query: str = "",
    max_price: float | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Search the merchant catalog.
    Returns matching active products (cost excluded) and the total considered count.
    Deterministic — no LLM involved.

    Args:
        query: Free-text keyword search against product name, description, tags
        max_price: Maximum price ceiling in INR (inclusive)
        category: Exact category name filter (e.g. "footwear", "accessories")
        limit: Maximum number of results to return (default 20)
    """
    logger.info("MCP search_catalog | query=%r max_price=%s category=%s", query, max_price, category)
    return _search_catalog(query=query, max_price=max_price, category=category, limit=limit)


# -------------------------------------------------------------------------
# Tool 2 — get_product
# -------------------------------------------------------------------------

@mcp.tool()
def get_product(product_id: str) -> dict:
    """
    Get the full details of one product by ID.
    Returns ProductPublic — cost (merchant margin data) is never included.

    Args:
        product_id: The product ID (e.g. "prod_001")
    """
    logger.info("MCP get_product | product_id=%s", product_id)
    return _get_product(product_id=product_id)


# -------------------------------------------------------------------------
# Tool 3 — build_cart
# -------------------------------------------------------------------------

@mcp.tool()
def build_cart(
    buyer_id: str,
    merchant_id: str,
    items: list[dict[str, Any]],
    reasoning: dict[str, Any] | None = None,
) -> dict:
    """
    Build a cart and snapshot current prices into CartItem.unit_price.
    The snapshot is what Verification later checks against — prices are
    locked at build_cart time, not re-read at checkout.

    Args:
        buyer_id: Identifier for the AI buyer agent
        merchant_id: Merchant whose catalog to buy from
        items: List of {"product_id": str, "quantity": int, "role": "primary"|"upsell"}
        reasoning: Optional reasoning from the AI (customer_request, considered_count, why)
    """
    logger.info("MCP build_cart | buyer=%s merchant=%s items=%d", buyer_id, merchant_id, len(items))
    return _build_cart(buyer_id=buyer_id, merchant_id=merchant_id, items=items, reasoning=reasoning)


# -------------------------------------------------------------------------
# Tool 4 — check_policy
# -------------------------------------------------------------------------

@mcp.tool()
def check_policy(
    cart_id: str,
    mandate_id: str | None = None,
    mandate: dict[str, Any] | None = None,
) -> dict:
    """
    Run Mandate Check (buyer authority) + Policy Gate (merchant rules) against a cart.
    Returns a PolicyDecision with approved=True only if BOTH sub-checks pass.
    Accepts either a stored mandate_id (resolved server-side) or an inline mandate dict.

    Args:
        cart_id: Cart to evaluate
        mandate_id: ID of a stored Mandate record (e.g. "mandate_demo_buyer_1")
        mandate: Inline mandate object (for testing; overrides mandate_id if both provided)
    """
    logger.info("MCP check_policy | cart=%s mandate_id=%s", cart_id, mandate_id)
    return _check_policy(cart_id=cart_id, mandate_id=mandate_id, mandate=mandate)


# -------------------------------------------------------------------------
# Tool 5 — checkout
# -------------------------------------------------------------------------

@mcp.tool()
def checkout(cart_id: str, policy_decision_id: str) -> dict:
    """
    Execute checkout for an approved cart.
    SAFETY: Re-verifies policy_decision.approved == True before touching Razorpay.
    If not approved: returns status="blocked", razorpay_order_id=None.
    Razorpay is never instantiated on a blocked decision.

    Args:
        cart_id: Cart to check out
        policy_decision_id: PolicyDecision ID returned by check_policy
    """
    logger.info("MCP checkout | cart=%s pd=%s", cart_id, policy_decision_id)
    return _checkout(cart_id=cart_id, policy_decision_id=policy_decision_id)


# -------------------------------------------------------------------------
# Starlette sub-app for mounting on FastAPI
# -------------------------------------------------------------------------

def create_mcp_app():
    """
    Returns a Starlette app with SSE transport routes:
      GET  /sse        — client connects and receives server-sent events
      POST /messages/  — client posts messages to an established SSE session
    Mount this at /mcp on the main FastAPI app.
    """
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sse = SseServerTransport("/mcp/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0],
                streams[1],
                mcp._mcp_server.create_initialization_options(),
            )

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
