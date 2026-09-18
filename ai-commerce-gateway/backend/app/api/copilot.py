"""
Merchant Copilot API endpoint (§6.1, §7).

POST /api/merchants/{merchant_id}/copilot/chat
- Streaming SSE response
- Merchant-scoped authentication (JWT.merchant_id == path.merchant_id)
- Grounded in 4 backend model tools with deterministic fallback
"""
from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.merchants import get_current_merchant
from app.models import MerchantModel
from app.copilot.agent import MerchantCopilotAgent

router = APIRouter(tags=["copilot"])


class CopilotChatRequest(BaseModel):
    message: str
    history: Optional[list[dict[str, Any]]] = None


@router.post(
    "/merchants/{merchant_id}/copilot/chat",
    summary="Chat with Merchant Growth AI Copilot (SSE Streaming)",
)
async def chat_with_copilot(
    merchant_id: str,
    body: CopilotChatRequest,
    db: Session = Depends(get_db),
    current: MerchantModel = Depends(get_current_merchant),
):
    """
    Initiates an SSE streaming conversation with the Merchant Growth AI Copilot.
    """
    if current.id != merchant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to merchant resource",
        )

    agent = MerchantCopilotAgent(db, merchant_id)

    return StreamingResponse(
        agent.stream_chat(body.message, body.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
