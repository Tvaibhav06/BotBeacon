"""
Transaction and audit log read endpoints.
GET /api/merchants/{id}/transactions
GET /api/transactions/{id}/receipt
GET /api/transactions/{id}/audit-trail
GET /api/merchants/{id}/audit-log
POST /api/demo/buyer-request  (stub — wired in Phase 8)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.merchants import get_current_merchant
from app.db.session import get_db
from app.models import AuditLogModel, MerchantModel, TransactionModel
from app.schemas import AuditLogEntry, DecisionReceipt, TransactionResult

router = APIRouter()


@router.get(
    "/merchants/{merchant_id}/transactions",
    response_model=list[TransactionResult],
    tags=["transactions"],
)
def list_transactions(
    merchant_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    if current.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    txns = (
        db.query(TransactionModel)
        .filter(TransactionModel.merchant_id == merchant_id)
        .order_by(TransactionModel.created_at.desc())
        .all()
    )
    return [TransactionResult.model_validate(t) for t in txns]


@router.get(
    "/transactions/{transaction_id}/receipt",
    response_model=DecisionReceipt,
    tags=["transactions"],
)
def get_receipt(
    transaction_id: str,
    db: Session = Depends(get_db),
):
    txn = db.get(TransactionModel, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    receipt_data = txn.receipt_data or {}
    return DecisionReceipt(
        transaction_id=txn.id,
        customer_request=txn.customer_request,
        ai_considered_count=receipt_data.get("ai_considered_count"),
        selected=receipt_data.get("selected"),
        why=receipt_data.get("why", []),
        upsell=receipt_data.get("upsell"),
        final_total=txn.amount,
        authorization_status=receipt_data.get("authorization_status", ""),
        payment_status=receipt_data.get("payment_status", ""),
    )


@router.get(
    "/transactions/{transaction_id}/audit-trail",
    response_model=list[AuditLogEntry],
    tags=["audit"],
)
def get_audit_trail(
    transaction_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    entries = (
        db.query(AuditLogModel)
        .filter(AuditLogModel.transaction_id == transaction_id)
        .filter(AuditLogModel.merchant_id == current.id)
        .order_by(AuditLogModel.timestamp.asc())
        .all()
    )
    return [AuditLogEntry.model_validate(e) for e in entries]


@router.get(
    "/merchants/{merchant_id}/audit-log",
    response_model=list[AuditLogEntry],
    tags=["audit"],
)
def get_audit_log(
    merchant_id: str,
    stage: Optional[str] = Query(None, description="Filter by stage"),
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    if current.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    q = (
        db.query(AuditLogModel)
        .filter(AuditLogModel.merchant_id == merchant_id)
    )
    if stage:
        q = q.filter(AuditLogModel.stage == stage)
    entries = q.order_by(AuditLogModel.timestamp.desc()).limit(500).all()
    return [AuditLogEntry.model_validate(e) for e in entries]


from pydantic import BaseModel
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from fastapi import Request
from fastapi.responses import StreamingResponse

class DemoRequest(BaseModel):
    intent: str

@router.post("/demo/buyer-request", tags=["demo"])
async def demo_buyer_request(body: DemoRequest, request: Request):
    """
    Invokes buyer-client/scripted_buyer.py with the given intent string
    and streams back the stdout line by line via Server-Sent Events (SSE).
    """
    async def event_generator():
        # 1. Resolve buyer-client directory using pathlib.Path
        current_file = Path(__file__).resolve()
        # project layout: ai-commerce-gateway/buyer-client
        candidate_dir = current_file.parents[3] / "buyer-client"
        if candidate_dir.exists() and (candidate_dir / "scripted_buyer.py").exists():
            buyer_client_dir = candidate_dir
        elif Path("/buyer-client/scripted_buyer.py").exists():
            buyer_client_dir = Path("/buyer-client")
        else:
            cwd_candidate = Path.cwd() / "buyer-client"
            if (cwd_candidate / "scripted_buyer.py").exists():
                buyer_client_dir = cwd_candidate
            else:
                buyer_client_dir = candidate_dir

        script_path = str(buyer_client_dir / "scripted_buyer.py")

        # 2. Resolve MCP URL dynamically from running server request or settings
        port = request.url.port or 8000
        host = request.url.hostname or "127.0.0.1"
        mcp_url = os.environ.get("MCP_URL", f"http://{host}:{port}/mcp")

        # 3. Environment with UTF-8 and PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = str(buyer_client_dir) + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        process = subprocess.Popen(
            [sys.executable, script_path, "--intent", body.intent, "--mcp-url", mcp_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )

        # Buffer to catch the final JSON receipt block
        is_receipt = False
        receipt_buffer = []

        try:
            while True:
                line = await asyncio.to_thread(process.stdout.readline)
                if not line:
                    break

                text = line.strip()
                if not text:
                    continue

                if text == "DECISION RECEIPT:":
                    is_receipt = True
                    continue

                if is_receipt:
                    # Accumulate receipt JSON
                    if text.startswith("========="):
                        # End of receipt block
                        is_receipt = False
                        try:
                            receipt_json = json.loads("".join(receipt_buffer))
                            yield f"data: {json.dumps({'type': 'receipt', 'data': receipt_json})}\n\n"
                        except json.JSONDecodeError as e:
                            yield f"data: {json.dumps({'type': 'log', 'message': f'JSON Parse Error: {e}'})}\n\n"
                            yield f"data: {json.dumps({'type': 'log', 'message': f'Buffer was: {repr(receipt_buffer)}'})}\n\n"
                    else:
                        receipt_buffer.append(text)
                else:
                    yield f"data: {json.dumps({'type': 'log', 'message': text})}\n\n"
        finally:
            if process.poll() is None:
                process.terminate()
            await asyncio.to_thread(process.wait)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
