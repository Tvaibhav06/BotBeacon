"""
SQLAlchemy ORM models for AI Commerce Gateway.
Field names match §5 of the Build Plan exactly.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    JSON, Enum as SAEnum, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class MerchantModel(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    passport_status: Mapped[str] = mapped_column(
        SAEnum("draft", "active", name="passport_status_enum"), default="draft", nullable=False
    )
    # Auth
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    rules: Mapped[Optional["MerchantRulesModel"]] = relationship(
        "MerchantRulesModel", back_populates="merchant", uselist=False, cascade="all, delete-orphan"
    )
    products: Mapped[list["ProductModel"]] = relationship(
        "ProductModel", back_populates="merchant", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLogModel"]] = relationship(
        "AuditLogModel", back_populates="merchant"
    )


class MerchantRulesModel(Base):
    __tablename__ = "merchant_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("merchants.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    max_ai_discount_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    upsell_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferred_categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    min_margin_pct: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    approval_threshold_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    merchant: Mapped["MerchantModel"] = relationship("MerchantModel", back_populates="rules")


class ProductModel(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    complement_categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum("active", "inactive", name="product_status_enum"), default="active", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    merchant: Mapped["MerchantModel"] = relationship("MerchantModel", back_populates="products")


class MandateModel(Base):
    __tablename__ = "mandates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    buyer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    max_amount: Mapped[float] = mapped_column(Float, nullable=False)
    category_scope: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CartModel(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    buyer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list["CartItemModel"]] = relationship(
        "CartItemModel", back_populates="cart", cascade="all, delete-orphan"
    )


class CartItemModel(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)  # snapshot at build_cart time
    role: Mapped[str] = mapped_column(
        SAEnum("primary", "upsell", name="cart_item_role_enum"), default="primary", nullable=False
    )

    cart: Mapped["CartModel"] = relationship("CartModel", back_populates="items")


class PolicyDecisionModel(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cart_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mandate_check_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mandate_check_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    policy_check_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_check_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TransactionModel(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cart_id: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    buyer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    razorpay_signature: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum("approved_paid", "blocked", "failed", "pending_payment",
               name="transaction_status_enum"),
        nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Denormalized receipt data for fast retrieval
    customer_request: Mapped[str] = mapped_column(Text, default="", nullable=False)
    receipt_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    merchant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cart_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(
        SAEnum("passport_activated", "decision_engine", "mandate_check",
               "policy_gate", "payment", "verification",
               name="audit_stage_enum"),
        nullable=False
    )
    actor: Mapped[str] = mapped_column(
        SAEnum("system", "buyer_agent", "merchant", name="audit_actor_enum"),
        nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    merchant: Mapped["MerchantModel"] = relationship("MerchantModel", back_populates="audit_logs")
