"""
Merchant rules configuration.
POST /api/merchants/{id}/rules
GET  /api/merchants/{id}/rules
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.merchants import get_current_merchant
from app.db.session import get_db
from app.models import MerchantModel, MerchantRulesModel
from app.schemas import MerchantRules

router = APIRouter()


@router.get("/merchants/{merchant_id}/rules", response_model=MerchantRules, tags=["rules"])
def get_rules(
    merchant_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    if current.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    merchant = db.get(MerchantModel, merchant_id)
    if not merchant or not merchant.rules:
        raise HTTPException(status_code=404, detail="Rules not found")
    return MerchantRules.model_validate(merchant.rules)


@router.post("/merchants/{merchant_id}/rules", response_model=MerchantRules, tags=["rules"])
def save_rules(
    merchant_id: str,
    body: MerchantRules,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Save (upsert) merchant rules.
    approval_threshold_amount is an autonomous-purchase threshold, NOT a payment ceiling.
    """
    if current.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    merchant = db.get(MerchantModel, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    if merchant.rules:
        rules = merchant.rules
    else:
        rules = MerchantRulesModel(merchant_id=merchant_id)
        db.add(rules)

    rules.max_ai_discount_pct = body.max_ai_discount_pct
    rules.upsell_enabled = body.upsell_enabled
    rules.preferred_categories = body.preferred_categories
    rules.min_margin_pct = body.min_margin_pct
    rules.approval_threshold_amount = body.approval_threshold_amount

    db.commit()
    db.refresh(rules)
    return MerchantRules.model_validate(rules)
