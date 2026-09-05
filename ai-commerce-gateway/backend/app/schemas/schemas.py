"""
Pydantic schemas — §5 of the Build Plan.
Field names are exact matches; every other section (MCP contracts, REST routes, seed) depends on them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Product & Merchant
# ---------------------------------------------------------------------------

class ProductBase(BaseModel):
    name: str
    category: str
    tags: list[str] = []
    price: float
    cost: float
    stock: int
    complement_categories: list[str] = []
    description: str = ""
    image_url: Optional[str] = None
    status: Literal["active", "inactive"] = "active"


class ProductCreate(ProductBase):
    id: Optional[str] = None  # auto-generated if not provided


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    price: Optional[float] = None
    cost: Optional[float] = None
    stock: Optional[int] = None
    complement_categories: Optional[list[str]] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


class Product(ProductBase):
    """Full product — returned to the merchant dashboard. cost is visible to merchant."""
    id: str

    model_config = {"from_attributes": True}


class ProductPublic(BaseModel):
    """
    Product as exposed to AI buyers via MCP.
    cost is intentionally omitted — merchant margin info must never be shown to buyers (§2).
    """
    id: str
    name: str
    category: str
    tags: list[str] = []
    price: float
    stock: int
    complement_categories: list[str] = []
    description: str = ""
    image_url: Optional[str] = None
    status: Literal["active", "inactive"] = "active"

    model_config = {"from_attributes": True}


class MerchantRules(BaseModel):
    max_ai_discount_pct: float = 0.0
    upsell_enabled: bool = True
    preferred_categories: list[str] = []
    min_margin_pct: float = 10.0
    # Above this amount, AI requires merchant approval before checkout.
    # NOT a maximum sales/payment ceiling — see §2 and §8.3.
    approval_threshold_amount: Optional[float] = None

    model_config = {"from_attributes": True}


class MerchantCreate(BaseModel):
    id: Optional[str] = None
    name: str
    email: str
    password: str


class Merchant(BaseModel):
    id: str
    name: str
    email: str
    passport_status: Literal["draft", "active"] = "draft"
    rules: Optional[MerchantRules] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Validation (Commerce Passport)
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    product_id: str
    field: str
    message: str
    severity: Literal["error", "warning"]
    # error blocks activation; warning does not — §8.6


class PassportResponse(BaseModel):
    merchant_id: str
    passport_status: Literal["draft", "active"]
    products: list[Product]
    validation_issues: list[ValidationIssue]
    can_activate: bool  # True only if no error-severity issues remain


# ---------------------------------------------------------------------------
# Mandate
# ---------------------------------------------------------------------------

class Mandate(BaseModel):
    id: str
    buyer_id: str
    max_amount: float
    category_scope: list[str] = []  # empty = unscoped (any category)
    expires_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

class CartItem(BaseModel):
    product_id: str
    quantity: int
    unit_price: float  # SNAPSHOT at build_cart time — Verification checks against this
    role: Literal["primary", "upsell"] = "primary"

    model_config = {"from_attributes": True}


class CartItemInput(BaseModel):
    product_id: str
    quantity: int
    role: Literal["primary", "upsell"] = "primary"


class Cart(BaseModel):
    id: str
    merchant_id: str
    buyer_id: str
    items: list[CartItem]
    total: float

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Policy Decision
# ---------------------------------------------------------------------------

class MandateCheckResult(BaseModel):
    passed: bool
    reasons: list[str]


class PolicyCheckResult(BaseModel):
    passed: bool
    reasons: list[str]


class PolicyDecision(BaseModel):
    id: str
    cart_id: str
    mandate_check: MandateCheckResult
    policy_check: PolicyCheckResult
    approved: bool   # true only if BOTH sub-checks passed
    reasons: list[str]  # merged, human-readable

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Transaction & Verification
# ---------------------------------------------------------------------------

class TransactionResult(BaseModel):
    id: str
    cart_id: str
    razorpay_order_id: Optional[str]  # MUST be None when status == "blocked"
    status: Literal["approved_paid", "blocked", "failed", "pending_payment"]
    amount: float

    model_config = {"from_attributes": True}


class VerificationResult(BaseModel):
    transaction_id: str
    match: bool
    discrepancies: list[str]


class PaymentVerifyRequest(BaseModel):
    """
    Payload sent by Checkout.js payment.success handler to POST /api/payments/verify.
    All three fields are required for server-side HMAC signature verification.
    """
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentVerifyResponse(BaseModel):
    """
    Response from POST /api/payments/verify.
    transaction_id:  the transaction that was updated.
    verified:        True only when signature + amount + order all match.
    discrepancies:   human-readable list of what went wrong (empty on success).
    """
    transaction_id: str
    verified: bool
    status: Literal["approved_paid", "blocked", "failed", "pending_payment"]
    discrepancies: list[str]


class PaymentConfigResponse(BaseModel):
    """
    Public Razorpay config returned to the frontend.
    KEY_SECRET is never included — only the public KEY_ID.
    """
    key_id: str
    currency: str = "INR"


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLogEntry(BaseModel):
    id: str
    timestamp: datetime
    merchant_id: str
    transaction_id: str | None = None
    cart_id: str | None = None
    stage: Literal[
        "passport_activated", "decision_engine", "mandate_check",
        "policy_gate", "payment", "verification"
    ]
    actor: Literal["system", "buyer_agent", "merchant"]
    payload: dict
    result: dict

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Decision Receipt
# ---------------------------------------------------------------------------

class DecisionReceipt(BaseModel):
    transaction_id: str
    customer_request: str
    ai_considered_count: Optional[int]
    selected: Optional[CartItem]
    why: list[str] = []
    upsell: Optional[CartItem]
    final_total: float
    authorization_status: str   # "Within buyer limit" / "Blocked — exceeds buyer limit"
    payment_status: str         # "Razorpay verified" / "Razorpay was never called"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str
