"""Add merchant growth models and audit stages

Revision ID: c4f2a71d89e0
Revises: b200e13954b0
Create Date: 2026-09-18 17:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f2a71d89e0'
down_revision: Union[str, None] = 'b200e13954b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Native PostgreSQL ENUM updates in autocommit_block() (§8.5)
    # Postgres forbids ALTER TYPE ... ADD VALUE inside a transaction block alongside other DDL.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for stage in ("growth_analysis", "growth_approval", "growth_execution"):
                op.execute(sa.text(f"ALTER TYPE audit_stage_enum ADD VALUE IF NOT EXISTS '{stage}'"))

    # 2. Add columns to merchant_rules
    op.add_column("merchant_rules", sa.Column("growth_approval_threshold_amount", sa.Float(), nullable=True))
    op.add_column("merchant_rules", sa.Column("growth_actions_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    # 3. Create sales_records table
    op.create_table(
        "sales_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("units_sold", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_records_merchant_product_date", "sales_records", ["merchant_id", "product_id", "date"], unique=False)

    # 4. Create growth_opportunities table
    op.create_table(
        "growth_opportunities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.JSON(), nullable=False),
        sa.Column("estimated_discount_exposure", sa.Float(), nullable=False),
        sa.Column("policy_outcome", sa.String(length=32), nullable=False),
        sa.Column("policy_reasons", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_growth_opportunities_merchant_status", "growth_opportunities", ["merchant_id", "status"], unique=False)

    # 5. Create growth_executions table
    op.create_table(
        "growth_executions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("n8n_run_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="executing", nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["growth_opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("growth_executions")
    op.drop_index("ix_growth_opportunities_merchant_status", table_name="growth_opportunities")
    op.drop_table("growth_opportunities")
    op.drop_index("ix_sales_records_merchant_product_date", table_name="sales_records")
    op.drop_table("sales_records")
    op.drop_column("merchant_rules", "growth_actions_enabled")
    op.drop_column("merchant_rules", "growth_approval_threshold_amount")
