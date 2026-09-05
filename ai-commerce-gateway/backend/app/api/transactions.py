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
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    txn = db.get(TransactionModel, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.merchant_id != current.id:
        raise HTTPException(status_code=403, detail="Access denied")

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


@router.post("/demo/buyer-request", tags=["demo"])
def demo_buyer_request(body: dict):
    """
    Stub — will be wired to buyer-client/scripted_buyer.py in Phase 8.
    Returns a 501 so the frontend can display a clear not-implemented message.
    """
    raise HTTPException(status_code=501, detail="Demo buyer endpoint implemented in Phase 8")
