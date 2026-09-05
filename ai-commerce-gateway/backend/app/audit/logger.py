"""
Append-only Audit Logger — §8.5.
Written incrementally at every stage, never bolted on later.

Stages: passport_activated | decision_engine | mandate_check |
        policy_gate | payment | verification
"""
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.models import AuditLogModel
from app.core.logging import logger

AuditStage = Literal[
    "passport_activated", "decision_engine", "mandate_check",
    "policy_gate", "payment", "verification"
]
AuditActor = Literal["system", "buyer_agent", "merchant"]


def write_audit_event(
    db: Session,
    *,
    merchant_id: str,
    stage: AuditStage,
    actor: AuditActor,
    payload: dict,
    result: dict,
    transaction_id: Optional[str] = None,
    cart_id: Optional[str] = None,
) -> AuditLogModel:
    """
    Write one immutable audit event to the database.
    Called inline at each stage — never batched retroactively.
    """
    entry = AuditLogModel(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        merchant_id=merchant_id,
        transaction_id=transaction_id,
        cart_id=cart_id,
        stage=stage,
        actor=actor,
        payload=payload,
        result=result,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info(
        "audit | stage=%s actor=%s merchant=%s tx=%s",
        stage, actor, merchant_id, transaction_id or "-"
    )
    return entry
