from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import Optional, List

from app.db.session import get_db
from app.models import AuditLogModel, TransactionModel
from app.schemas.schemas import AuditLogEntry
from app.api.merchants import get_current_merchant

router = APIRouter(tags=["Audit"])

@router.get("/merchants/{merchant_id}/audit-log", response_model=List[AuditLogEntry])
def get_merchant_audit_log(
    merchant_id: str,
    stage: Optional[str] = Query(None, description="Filter by stage"),
    db: Session = Depends(get_db),
    current_merchant = Depends(get_current_merchant),
):
    """
    Get all audit logs for a merchant, ordered newest first.
    Optionally filter by stage.
    """
    if current_merchant.id != merchant_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this merchant's audit log")

    query = db.query(AuditLogModel).filter(AuditLogModel.merchant_id == merchant_id)
    if stage:
        query = query.filter(AuditLogModel.stage == stage)
    
    logs = query.order_by(desc(AuditLogModel.timestamp)).limit(500).all()
    return logs

@router.get("/transactions/{transaction_id}/audit-trail", response_model=List[AuditLogEntry])
def get_transaction_audit_trail(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_merchant = Depends(get_current_merchant),
):
    """
    Get all audit logs for a specific transaction's journey, ordered oldest first.
    Resolves the transaction to its cart_id and fetches the full chronological timeline.
    """
    txn = db.query(TransactionModel).filter(
        TransactionModel.id == transaction_id,
        TransactionModel.merchant_id == current_merchant.id
    ).first()
    
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    logs = db.query(AuditLogModel).filter(
        AuditLogModel.cart_id == txn.cart_id,
        AuditLogModel.merchant_id == current_merchant.id
    ).order_by(asc(AuditLogModel.timestamp)).all()
    
    return logs
