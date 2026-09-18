"""
n8n Webhook Client — §6.6.

Triggers the 'Execute Merchant Growth Action' workflow in n8n.
Security Invariant:
- Secrets are NEVER included inside the JSON payload.
- Authentication uses header 'X-Gateway-Api-Key'.
- Short timeout (~8s); only waits for workflow trigger acknowledgment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


def trigger_growth_action(
    *,
    execution_id: str,
    opportunity_id: str,
    merchant_id: str,
    action: dict[str, Any],
    products: list[dict[str, Any]],
) -> tuple[bool, Optional[str], dict[str, Any]]:
    """
    Send authenticated trigger webhook to n8n.

    Returns:
        (success: bool, error_message: Optional[str], request_payload: dict)
    """
    callback_url = f"{settings.GROWTH_CALLBACK_BASE_URL.rstrip('/')}/api/growth/execution-callback"

    # Business data only — zero secrets in payload (§6.6, §9)
    payload = {
        "execution_id": execution_id,
        "opportunity_id": opportunity_id,
        "merchant_id": merchant_id,
        "action_type": action.get("type", "discount_bundle"),
        "target_products": products,
        "discount_pct": action.get("discount_pct", 10.0),
        "campaign_duration_weeks": action.get("campaign_duration_weeks", 1),
        "audience": action.get("audience", "configured_demo_audience"),
        "callback_url": callback_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not settings.N8N_GROWTH_WEBHOOK_URL:
        logger.info(
            "N8N_GROWTH_WEBHOOK_URL not configured — recording execution dispatch in simulated mode: exec_id=%s",
            execution_id,
        )
        return True, None, payload

    headers = {
        "Content-Type": "application/json",
        "X-Gateway-Api-Key": settings.N8N_WEBHOOK_API_KEY,
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(settings.N8N_GROWTH_WEBHOOK_URL, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                logger.info("n8n webhook triggered successfully for execution_id=%s", execution_id)
                return True, None, payload
            else:
                err = f"n8n webhook failed with HTTP {resp.status_code}: {resp.text}"
                logger.error(err)
                return False, err, payload
    except Exception as exc:
        err = f"n8n webhook network failure: {str(exc)}"
        logger.error(err)
        return False, err, payload
