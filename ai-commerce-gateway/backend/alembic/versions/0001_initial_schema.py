"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

Creates all Phase 1 tables:
  merchants, merchant_rules, products, mandates,
  carts, cart_items, policy_decisions, transactions, audit_logs

Enum strategy (SQLAlchemy 2.0 / Alembic 1.14):
  NamedType._on_table_create fires for every enum column in create_table,
  UNLESS the enum has a MetaData bound to it (self.metadata is not None).
  When metadata is bound, _on_table_create is a no-op — it assumes the
  MetaData-level DDL events already handled creation.

  We therefore:
    1. Create a local MetaData instance and bind it to every PgEnum.
    2. Emit CREATE TYPE explicitly via op.execute before the first table.
    3. PgEnum(..., create_type=False, metadata=_meta) → _on_table_create is
       suppressed → no duplicate-type error.

  This is the canonical pattern for SQLAlchemy 2.0 + Alembic manual migrations.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Shared MetaData — binding this to every PgEnum suppresses _on_table_create
# so the types are created exactly once by the explicit op.execute calls below.
# ---------------------------------------------------------------------------
_meta = MetaData()


def _enum(*values, name: str) -> PgEnum:
    """
    Return a PgEnum that:
      - has create_type=False (belt)
      - is bound to _meta (suspenders) → _on_table_create is a no-op
    Types are created explicitly before any create_table call.
    """
    return PgEnum(*values, name=name, create_type=False, metadata=_meta)


def upgrade() -> None:
    # ── Step 1: Create enum types exactly once ────────────────────────────
    # Plain CREATE TYPE (no DO block needed — this is a fresh DB).
    # On a fresh volume these will always succeed.
    op.execute("CREATE TYPE passport_status_enum AS ENUM ('draft', 'active')")
    op.execute("CREATE TYPE product_status_enum AS ENUM ('active', 'inactive')")
    op.execute("CREATE TYPE cart_item_role_enum AS ENUM ('primary', 'upsell')")
    op.execute("CREATE TYPE transaction_status_enum AS ENUM ('approved_paid', 'blocked', 'failed', 'pending_payment')")
    op.execute("CREATE TYPE audit_stage_enum AS ENUM ('passport_activated', 'decision_engine', 'mandate_check', 'policy_gate', 'payment', 'verification')")
    op.execute("CREATE TYPE audit_actor_enum AS ENUM ('system', 'buyer_agent', 'merchant')")

    # ── Step 2: Create tables (enums are referenced, never re-created) ────

    # --- merchants ---
    op.create_table(
        "merchants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("passport_status", _enum("draft", "active", name="passport_status_enum"), nullable=False, server_default="draft"),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- merchant_rules ---
    op.create_table(
        "merchant_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("merchant_id", sa.String(64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("max_ai_discount_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("upsell_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("preferred_categories", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("min_margin_pct", sa.Float, nullable=False, server_default="10"),
        sa.Column("approval_threshold_amount", sa.Float, nullable=True),
    )

    # --- products ---
    op.create_table(
        "products",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("merchant_id", sa.String(64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("stock", sa.Integer, nullable=False),
        sa.Column("complement_categories", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("description", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("status", _enum("active", "inactive", name="product_status_enum"), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_products_merchant_id", "products", ["merchant_id"])
    op.create_index("ix_products_category", "products", ["category"])

    # --- mandates ---
    op.create_table(
        "mandates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("buyer_id", sa.String(64), nullable=False),
        sa.Column("max_amount", sa.Float, nullable=False),
        sa.Column("category_scope", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mandates_buyer_id", "mandates", ["buyer_id"])

    # --- carts ---
    op.create_table(
        "carts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("merchant_id", sa.String(64), nullable=False),
        sa.Column("buyer_id", sa.String(64), nullable=False),
        sa.Column("total", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- cart_items ---
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("cart_id", sa.String(64), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Float, nullable=False),
        sa.Column("role", _enum("primary", "upsell", name="cart_item_role_enum"), nullable=False, server_default="primary"),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])

    # --- policy_decisions ---
    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("cart_id", sa.String(64), nullable=False),
        sa.Column("mandate_check_passed", sa.Boolean, nullable=False),
        sa.Column("mandate_check_reasons", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("policy_check_passed", sa.Boolean, nullable=False),
        sa.Column("policy_check_reasons", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("approved", sa.Boolean, nullable=False),
        sa.Column("reasons", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- transactions ---
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("cart_id", sa.String(64), nullable=False),
        sa.Column("merchant_id", sa.String(64), nullable=False),
        sa.Column("buyer_id", sa.String(64), nullable=False),
        sa.Column("razorpay_order_id", sa.String(128), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(128), nullable=True),
        sa.Column("razorpay_signature", sa.String(512), nullable=True),
        sa.Column("status", _enum("approved_paid", "blocked", "failed", "pending_payment", name="transaction_status_enum"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("customer_request", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("receipt_data", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_transactions_merchant_id", "transactions", ["merchant_id"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("merchant_id", sa.String(64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", sa.String(64), nullable=True),
        sa.Column("stage", _enum("passport_activated", "decision_engine", "mandate_check", "policy_gate", "payment", "verification", name="audit_stage_enum"), nullable=False),
        sa.Column("actor", _enum("system", "buyer_agent", "merchant", name="audit_actor_enum"), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("result", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_audit_logs_merchant_id", "audit_logs", ["merchant_id"])
    op.create_index("ix_audit_logs_transaction_id", "audit_logs", ["transaction_id"])
    op.create_index("ix_audit_logs_stage", "audit_logs", ["stage"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("transactions")
    op.drop_table("policy_decisions")
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_table("mandates")
    op.drop_table("products")
    op.drop_table("merchant_rules")
    op.drop_table("merchants")

    op.execute("DROP TYPE IF EXISTS audit_actor_enum")
    op.execute("DROP TYPE IF EXISTS audit_stage_enum")
    op.execute("DROP TYPE IF EXISTS transaction_status_enum")
    op.execute("DROP TYPE IF EXISTS cart_item_role_enum")
    op.execute("DROP TYPE IF EXISTS product_status_enum")
    op.execute("DROP TYPE IF EXISTS passport_status_enum")
