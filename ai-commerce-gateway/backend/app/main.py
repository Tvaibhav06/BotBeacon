from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import logger
from app.api import merchants, catalog, rules, transactions, payments, audit
from app.mcp.server import create_mcp_app

settings = get_settings()

app = FastAPI(
    title="AI Commerce Gateway",
    description="Merchant-side infrastructure layer for AI-buyer-ready commerce.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes — merchant dashboard (§7)
app.include_router(merchants.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(audit.router, prefix="/api")

# MCP server — the ONLY agent-facing surface (§4)
# Mounted at /mcp; exposes /mcp/sse and /mcp/messages/
app.mount("/mcp", create_mcp_app())


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "ai-commerce-gateway", "version": "0.1.0"}


@app.get("/mcp/health", tags=["system"])
async def mcp_health():
    """Confirm MCP server is mounted and the 5 tools are registered."""
    tools = [t.name for t in mcp_app_tools()]
    return {"status": "ok", "transport": "sse", "tools": tools}


def mcp_app_tools():
    from app.mcp.server import mcp
    return mcp._mcp_server.list_tools() if hasattr(mcp._mcp_server, "list_tools") else []


logger.info("AI Commerce Gateway starting up — MCP server mounted at /mcp")
