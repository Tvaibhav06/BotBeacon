"""
MCP HTTP client for the buyer side.
Talks to the Gateway MCP server over SSE/HTTP.
NO backend imports — this communicates only through the 5 MCP tool calls.

MCP 1.2.0 SSE protocol (used by mcp.server.sse.SseServerTransport):

  1. Client opens a persistent GET /mcp/sse connection (Accept: text/event-stream).
  2. Server sends:
       event: endpoint
       data: /mcp/messages/?session_id=<hex>
  3. Client POSTs all JSON-RPC messages to that session URL while keeping the
     SSE stream open.
  4. Server sends responses back over the *same* SSE stream as:
       event: message
       data: <json>

The previous implementation had two bugs:
  a) It hardcoded port 8000 — the Docker backend is exposed on host port 8001.
  b) It tried to parse the endpoint event as JSON (the data is a plain URL string),
     and it opened a *second* SSE connection to read tool responses, which creates
     a different session and never receives the reply.

Fix: keep one SSE connection open throughout and run SSE reading and HTTP POSTs
concurrently inside a single async scope.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Default base URL — configurable via MCP_BASE_URL env var so callers
# running against Docker (port 8001) vs. local (port 8000) can override
# without touching source code.
# ---------------------------------------------------------------------------
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "http://localhost:8001/mcp")


class MCPClient:
    """
    Thin wrapper that calls the 5 Gateway MCP tools over SSE/HTTP.
    Each tool call opens a fresh SSE session, performs the full
    initialize → initialized → tools/call lifecycle, and closes.
    No backend code is imported.
    """

    def __init__(self, base_url: str = MCP_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call one MCP tool synchronously (runs an async event loop)."""
        return asyncio.run(self._call_tool_async(tool_name, arguments))

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        MCP SSE 1.2.0 protocol — correct implementation:

        1. Open persistent SSE connection to /mcp/sse.
        2. Read the "endpoint" event — data is a plain relative URL:
               /mcp/messages/?session_id=<hex>
        3. Build the absolute messages URL from it.
        4. POST initialize, initialized notification, then the tool call
           to that URL — all while the SSE stream stays open.
        5. Read the tool-call response from the same SSE stream
           (event: message, id matches our request id=2).
        6. Return the parsed result.
        """
        sse_url = f"{self.base_url}/sse"
        result_container: list[Any] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            # ---------------------------------------------------------------
            # Phase A: open SSE, get the session messages URL
            # ---------------------------------------------------------------
            messages_url: str | None = None
            collected_sse_events: list[tuple[str, str]] = []  # (event, data)

            # We need to keep the SSE connection alive while we POST.
            # Strategy: start the SSE stream, read the endpoint event,
            # then run POSTs concurrently with the SSE reader.

            async def read_sse_stream(
                sse_resp: httpx.Response,
            ) -> None:
                """Read SSE lines from the stream; parse event/data pairs."""
                nonlocal messages_url
                current_event: str = "message"
                pending_data: list[str] = []

                async for raw_line in sse_resp.aiter_lines():
                    line = raw_line.strip()

                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                        continue

                    if line.startswith("data:"):
                        data_val = line[len("data:"):].strip()
                        pending_data.append(data_val)
                        continue

                    if line == "":
                        # Empty line = end of SSE event block
                        data_str = "\n".join(pending_data)
                        pending_data = []

                        if current_event == "endpoint" and messages_url is None:
                            # data is a plain relative URL, NOT JSON
                            # e.g. "/mcp/messages/?session_id=abc123"
                            relative = data_str.strip()
                            # Build absolute URL using the base host
                            # (strip the /mcp path segment from base_url)
                            host = self.base_url.split("/mcp")[0]  # e.g. http://localhost:8001
                            messages_url = f"{host}{relative}"
                            continue

                        if current_event == "message" and data_str:
                            try:
                                msg = json.loads(data_str)
                                if isinstance(msg, dict):
                                    collected_sse_events.append((current_event, data_str))
                                    # Signal that we have a response with id=2
                                    if msg.get("id") == 2:
                                        # Parse result content
                                        result = msg.get("result", {})
                                        content = result.get("content", [])
                                        if content and isinstance(content, list):
                                            for c in content:
                                                if c.get("type") == "text":
                                                    try:
                                                        result_container.append(
                                                            json.loads(c["text"])
                                                        )
                                                    except json.JSONDecodeError:
                                                        result_container.append(c["text"])
                                                    break
                                        return  # done — exit SSE reader
                            except json.JSONDecodeError:
                                pass

                        current_event = "message"  # reset for next event

            # Open the SSE stream
            async with client.stream(
                "GET", sse_url, headers={"Accept": "text/event-stream"}
            ) as sse_resp:
                # Start SSE reader as a background task
                sse_task = asyncio.create_task(read_sse_stream(sse_resp))

                # Wait until we have the messages_url (endpoint event received)
                deadline = asyncio.get_event_loop().time() + 15.0
                while messages_url is None:
                    if asyncio.get_event_loop().time() > deadline:
                        sse_task.cancel()
                        raise RuntimeError(
                            f"Timed out waiting for MCP endpoint event from {sse_url}"
                        )
                    await asyncio.sleep(0.05)

                # -----------------------------------------------------------
                # Phase B: send MCP initialize handshake
                # -----------------------------------------------------------
                init_payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "buyer-client", "version": "0.1.0"},
                    },
                    "id": 1,
                }
                await client.post(messages_url, json=init_payload)

                await client.post(
                    messages_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    },
                )

                # -----------------------------------------------------------
                # Phase C: send tool call
                # -----------------------------------------------------------
                tool_payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                    "id": 2,
                }
                await client.post(messages_url, json=tool_payload)

                # -----------------------------------------------------------
                # Phase D: wait for the SSE reader to capture the response
                # -----------------------------------------------------------
                try:
                    await asyncio.wait_for(sse_task, timeout=30.0)
                except asyncio.TimeoutError:
                    sse_task.cancel()
                    raise RuntimeError(
                        f"Timed out waiting for tool response: {tool_name}"
                    )
                except asyncio.CancelledError:
                    pass  # task cancelled by itself after finding result

        return result_container[0] if result_container else {}

    # -------------------------------------------------------------------------
    # Public tool methods — one per MCP tool
    # -------------------------------------------------------------------------

    def search_catalog(
        self,
        query: str = "",
        max_price: float | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> dict:
        args: dict[str, Any] = {"query": query, "limit": limit}
        if max_price is not None:
            args["max_price"] = max_price
        if category is not None:
            args["category"] = category
        return self._call_tool("search_catalog", args)

    def get_product(self, product_id: str) -> dict:
        return self._call_tool("get_product", {"product_id": product_id})

    def build_cart(
        self,
        buyer_id: str,
        merchant_id: str,
        items: list[dict[str, Any]],
        reasoning: dict[str, Any] | None = None,
    ) -> dict:
        args = {
            "buyer_id": buyer_id,
            "merchant_id": merchant_id,
            "items": items,
        }
        if reasoning:
            args["reasoning"] = reasoning
        return self._call_tool("build_cart", args)

    def check_policy(
        self,
        cart_id: str,
        mandate_id: str | None = None,
        mandate: dict | None = None,
    ) -> dict:
        args: dict[str, Any] = {"cart_id": cart_id}
        if mandate_id:
            args["mandate_id"] = mandate_id
        if mandate:
            args["mandate"] = mandate
        return self._call_tool("check_policy", args)

    def checkout(self, cart_id: str, policy_decision_id: str) -> dict:
        return self._call_tool("checkout", {
            "cart_id": cart_id,
            "policy_decision_id": policy_decision_id,
        })
