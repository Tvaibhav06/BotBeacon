"""
Merchant auth + onboarding routes.
POST /api/merchants/onboard
POST /api/auth/login
GET  /api/merchants/{id}
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token, decode_token
from app.db.session import get_db
from app.models import MerchantModel, MerchantRulesModel
from app.schemas import MerchantCreate, Merchant, MerchantRules, TokenResponse, LoginRequest

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_merchant(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> MerchantModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        merchant_id: str = payload.get("sub")
        if not merchant_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    merchant = db.get(MerchantModel, merchant_id)
    if not merchant:
        raise credentials_exception
    return merchant


@router.post("/merchants/onboard", response_model=Merchant, status_code=201, tags=["merchants"])
def onboard_merchant(body: MerchantCreate, db: Session = Depends(get_db)):
    """Create a new merchant account. Returns the created merchant (no password)."""
    existing = db.query(MerchantModel).filter(MerchantModel.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    merchant_id = body.id or f"merchant_{uuid.uuid4().hex[:8]}"
    merchant = MerchantModel(
        id=merchant_id,
        name=body.name,
        email=body.email,
        hashed_password=hash_password(body.password),
        passport_status="draft",
    )
    db.add(merchant)

    # Create default rules
    rules = MerchantRulesModel(
        merchant_id=merchant_id,
        max_ai_discount_pct=0.0,
        upsell_enabled=True,
        preferred_categories=[],
        min_margin_pct=10.0,
        approval_threshold_amount=None,
    )
    db.add(rules)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a merchant and return a JWT."""
    merchant = db.query(MerchantModel).filter(MerchantModel.email == body.email).first()
    if not merchant or not verify_password(body.password, merchant.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": merchant.id, "role": "merchant_admin"})
    return TokenResponse(access_token=token)


@router.get("/merchants/{merchant_id}", response_model=Merchant, tags=["merchants"])
def get_merchant(
    merchant_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    if current.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    merchant = db.get(MerchantModel, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
