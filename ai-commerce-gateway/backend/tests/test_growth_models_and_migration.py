"""
Phase 2 tests — Merchant Growth Data Models, Schema, Migration & Seed Data.

Verifies:
1. Model attributes, defaults, table names, constraints, and relationships.
2. Pydantic schema validation for sales records, growth opportunities, executions, and rules.
3. AuditStage literal and AuditLogModel enum values.
4. Real PostgreSQL migration & seed verification (when database is available).
"""
import datetime
from typing import get_args
import pytest

from app.models import (
    MerchantModel,
    MerchantRulesModel,
    ProductModel,
    SalesRecordModel,
    GrowthOpportunityModel,
    GrowthExecutionModel,
    AuditLogModel,
)
from app.audit.logger import AuditStage
from app.schemas import (
    MerchantRules,
    SalesRecord,
    SalesRecordCreate,
    RecommendedAction,
    GrowthOpportunity,
    GrowthOpportunityBase,
    GrowthExecution,
)


class TestMerchantRulesModel:
    """Validate additions to MerchantRulesModel (§8.2)."""

    def test_merchant_rules_growth_defaults(self):
        rules = MerchantRulesModel(merchant_id="m_test")
        assert rules.growth_actions_enabled is False
        assert rules.growth_approval_threshold_amount is None

    def test_merchant_rules_schema_defaults(self):
        schema = MerchantRules()
        assert schema.growth_actions_enabled is False
        assert schema.growth_approval_threshold_amount is None

    def test_merchant_rules_schema_custom(self):
        schema = MerchantRules(
            growth_actions_enabled=True,
            growth_approval_threshold_amount=2000.0,
            max_ai_discount_pct=15.0,
        )
        assert schema.growth_actions_enabled is True
        assert schema.growth_approval_threshold_amount == 2000.0
        assert schema.max_ai_discount_pct == 15.0


class TestSalesRecordModel:
    """Validate SalesRecordModel schema and table configuration (§8.1)."""

    def test_table_name_and_columns(self):
        assert SalesRecordModel.__tablename__ == "sales_records"
        cols = {c.name for c in SalesRecordModel.__table__.columns}
        assert {"id", "merchant_id", "product_id", "date", "units_sold", "revenue", "created_at"}.issubset(cols)

    def test_index_present(self):
        indices = [idx.name for idx in SalesRecordModel.__table__.indexes]
        assert "ix_sales_records_merchant_product_date" in indices

    def test_sales_record_schema(self):
        record = SalesRecord(
            id=1,
            merchant_id="merchant_velocity_sports",
            product_id="prod_001",
            date=datetime.date(2026, 9, 10),
            units_sold=2,
            revenue=10998.0,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        assert record.id == 1
        assert record.product_id == "prod_001"
        assert record.units_sold == 2
        assert record.revenue == 10998.0


class TestGrowthOpportunityModel:
    """Validate GrowthOpportunityModel schema and state transitions (§6.3, §8.1, §8.4)."""

    def test_table_name_and_columns(self):
        assert GrowthOpportunityModel.__tablename__ == "growth_opportunities"
        cols = {c.name for c in GrowthOpportunityModel.__table__.columns}
        expected = {
            "id", "merchant_id", "opportunity_type", "title", "evidence",
            "recommended_action", "estimated_discount_exposure", "policy_outcome",
            "policy_reasons", "status", "created_at", "updated_at",
        }
        assert expected.issubset(cols)

    def test_index_present(self):
        indices = [idx.name for idx in GrowthOpportunityModel.__table__.indexes]
        assert "ix_growth_opportunities_merchant_status" in indices

    def test_opportunity_schema_validation(self):
        action = RecommendedAction(
            type="discount_bundle",
            product_ids=["prod_001", "prod_006"],
            discount_pct=10.0,
            campaign_duration_weeks=1,
            audience="configured_demo_audience",
        )
        opp = GrowthOpportunityBase(
            merchant_id="merchant_velocity_sports",
            opportunity_type="declining_sales",
            title="Promote Velocity Pro with Performance Socks",
            evidence={"trend_pct": -37.5, "recent_weekly_units": 5},
            recommended_action=action,
            estimated_discount_exposure=2999.0,
            policy_outcome="requires_approval",
            policy_reasons=["exposure ₹2,999 exceeds threshold ₹2,000"],
            status="pending_approval",
        )
        assert opp.estimated_discount_exposure == 2999.0
        assert opp.policy_outcome == "requires_approval"
        assert opp.recommended_action.audience == "configured_demo_audience"


class TestGrowthExecutionModel:
    """Validate GrowthExecutionModel schema (§8.1)."""

    def test_table_name_and_columns(self):
        assert GrowthExecutionModel.__tablename__ == "growth_executions"
        cols = {c.name for c in GrowthExecutionModel.__table__.columns}
        expected = {
            "id", "opportunity_id", "n8n_run_id", "status",
            "request_payload", "result_payload", "error", "started_at", "completed_at",
        }
        assert expected.issubset(cols)

    def test_execution_schema_validation(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        exec_item = GrowthExecution(
            id="exec_001",
            opportunity_id="opp_001",
            n8n_run_id="run_123",
            status="completed",
            request_payload={"action": "discount_bundle"},
            result_payload={"emails_sent": 150},
            error=None,
            started_at=now,
            completed_at=now,
        )
        assert exec_item.id == "exec_001"
        assert exec_item.status == "completed"
        assert exec_item.result_payload["emails_sent"] == 150


class TestAuditStages:
    """Validate the 3 new native audit stages (§6.7)."""

    def test_audit_stage_literal_has_growth_stages(self):
        stages = get_args(AuditStage)
        assert "growth_analysis" in stages
        assert "growth_approval" in stages
        assert "growth_execution" in stages
        assert len(stages) == 9


class TestPostgresVerification:
    """
    Live verification against real PostgreSQL (if running locally or in Docker).
    Tests actual database schema, enum values, and seeded sales figures (§6.2, §8.3, §10).
    """

    def test_live_postgres_enum_and_tables(self):
        import psycopg
        from app.core.config import get_settings

        settings = get_settings()
        # Parse db url or connect directly if postgres is running
        try:
            conn = psycopg.connect("postgresql://acg_user:acg_pass@localhost:5432/ai_commerce_gateway")
        except Exception:
            pytest.skip("Live PostgreSQL not reachable on localhost:5432, skipping live DB test")

        with conn.cursor() as cur:
            # Check native enum stages
            cur.execute(
                "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE typname = 'audit_stage_enum'"
            )
            enum_vals = {r[0] for r in cur.fetchall()}
            assert {"growth_analysis", "growth_approval", "growth_execution"}.issubset(enum_vals)

            # Check rules columns
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'merchant_rules' AND column_name IN ('growth_actions_enabled', 'growth_approval_threshold_amount')"
            )
            rules_cols = {r[0] for r in cur.fetchall()}
            assert rules_cols == {"growth_actions_enabled", "growth_approval_threshold_amount"}

            # Check seeded sales figures for Velocity Pro (prod_001)
            cur.execute(
                "SELECT SUM(units_sold), SUM(revenue) FROM sales_records WHERE product_id = 'prod_001'"
            )
            total_units, total_rev = cur.fetchone()
            assert total_units == 26  # 16 prior + 10 recent
            assert total_rev == 26 * 5499.0

            # Check seeded sales for Performance Socks (prod_006)
            cur.execute(
                "SELECT SUM(units_sold) FROM sales_records WHERE product_id = 'prod_006'"
            )
            socks_units = cur.fetchone()[0]
            assert socks_units == 6
