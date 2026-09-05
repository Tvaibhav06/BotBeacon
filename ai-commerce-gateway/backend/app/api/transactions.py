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
    entries = q.order_by(AuditLogModel.timestamp.desc()).all()
    return [AuditLogEntry.model_validate(e) for e in entries]


from pydantic import BaseModel
import asyncio
import json
from fastapi.responses import StreamingResponse

class DemoRequest(BaseModel):
    intent: str

@router.post("/demo/buyer-request", tags=["demo"])
async def demo_buyer_request(body: DemoRequest):
    """
    Invokes buyer-client/scripted_buyer.py with the given intent string
    and streams back the stdout line by line via Server-Sent Events (SSE).
    """
    async def event_generator():
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = "/buyer-client"
        
        process = await asyncio.create_subprocess_exec(
            "python", "/buyer-client/scripted_buyer.py", "--intent", body.intent, "--mcp-url", "http://localhost:8000/mcp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env
        )
        
        # Buffer to catch the final JSON receipt block
        is_receipt = False
        receipt_buffer = []

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            text = line.decode("utf-8").strip()
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
                    except json.JSONDecodeError:
                        pass
                else:
                    receipt_buffer.append(text)
            else:
                yield f"data: {json.dumps({'type': 'log', 'message': text})}\n\n"
            
        await process.wait()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
