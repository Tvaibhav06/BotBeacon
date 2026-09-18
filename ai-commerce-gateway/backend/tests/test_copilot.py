"""
Phase 5 tests — Merchant AI Copilot, SSE Streaming, Tool Grounding & Fallback (§6.1, §7, §10).

Critical Acceptance Tests:
1. Copilot tools strictly ground claims in real DB metrics.
2. check_growth_policy and execute_growth_action are NEVER model-callable.
3. Copilot falls back to deterministic analysis when GEMINI_API_KEY is empty/unavailable.
4. Deterministic fallback produces real grounded figures (37.5% drop, 10% attach, ₹2,999 exposure).
5. Copilot endpoint enforces JWT authentication and merchant scoping (403 for other merchants).
6. Copilot stream returns valid SSE event format.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models import MerchantRulesModel, GrowthOpportunityModel, AuditLogModel
from app.copilot.agent import MerchantCopilotAgent

settings = get_settings()
client = TestClient(app)

MERCHANT_ID = "merchant_velocity_sports"
OTHER_MERCHANT_ID = "merchant_other_store"


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": MERCHANT_ID, "role": "merchant_admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers(db_session):
    from app.models import MerchantModel
    # Ensure second merchant exists in DB so auth succeeds
    second = db_session.get(MerchantModel, OTHER_MERCHANT_ID)
    if not second:
        second = MerchantModel(
            id=OTHER_MERCHANT_ID,
            name="Other Sports Store",
            email="other@example.com",
            hashed_password="mock_hashed_pw",
        )
        db_session.add(second)
        db_session.commit()
    token = create_access_token({"sub": OTHER_MERCHANT_ID, "role": "merchant_admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def preserve_merchant_rules():
    db = SessionLocal()
    try:
        rules = db.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        orig_max = rules.max_ai_discount_pct if rules else 15.0
        orig_enabled = rules.growth_actions_enabled if rules else True
        orig_thresh = rules.growth_approval_threshold_amount if rules else 2000.0
    finally:
        db.close()

    yield

    db = SessionLocal()
    try:
        rules = db.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        if rules:
            rules.max_ai_discount_pct = orig_max
            rules.growth_actions_enabled = orig_enabled
            rules.growth_approval_threshold_amount = orig_thresh
            db.commit()
    finally:
        db.close()


class TestCopilotToolsAndSafety:
    """Tests that copilot tools are grounded and safety invariants are held (§6.1)."""

    def test_model_tools_are_grounded_in_database(self, db_session):
        agent = MerchantCopilotAgent(db_session, MERCHANT_ID)

        # 1. Sales insights
        insights = agent.get_sales_insights()
        assert "total_revenue_recent" in insights
        assert "trend_pct" in insights
        assert insights["trend_pct"] < 0  # velocity pro decline drags overall trend

        # 2. Find growth opportunities
        opps = agent.find_growth_opportunities()
        assert "declining_products" in opps
        assert "cross_sell_opportunities" in opps
        # Velocity Pro must be detected
        declining_ids = [p["product_id"] for p in opps["declining_products"]]
        assert "prod_001" in declining_ids
        # Socks cross-sell must be detected
        cross_sell_pairs = [
            (c["primary_product_id"], c["complement_product_id"])
            for c in opps["cross_sell_opportunities"]
        ]
        assert ("prod_001", "prod_006") in cross_sell_pairs

        # 3. Recommend action
        proposal = agent.recommend_growth_action(
            opportunity_type="declining_sales",
            primary_product_id="prod_001",
            complement_product_id="prod_006",
            discount_pct=10.0,
            campaign_duration_weeks=1,
        )
        assert proposal["estimated_discount_exposure"] == 2999.0
        assert proposal["policy_outcome"] == "requires_approval"
        assert "opportunity_id" in proposal

        # Opportunity must be persisted in PostgreSQL
        db_session.expire_all()
        saved = db_session.get(GrowthOpportunityModel, proposal["opportunity_id"])
        assert saved is not None
        assert saved.merchant_id == MERCHANT_ID

    def test_prohibited_tools_are_not_callable(self, db_session):
        """
        PRD §6.1: check_growth_policy and execute_growth_action must NEVER be model-callable.
        """
        agent = MerchantCopilotAgent(db_session, MERCHANT_ID)
        assert not hasattr(agent, "check_growth_policy")
        assert not hasattr(agent, "execute_growth_action")
        assert not hasattr(agent, "trigger_growth_action")


class TestCopilotDeterministicFallbackAndSSE:
    """Tests for fallback narrative and streaming SSE endpoint (§6.1, §7)."""

    def test_copilot_endpoint_requires_auth(self):
        resp = client.post(
            f"/api/merchants/{MERCHANT_ID}/copilot/chat",
            json={"message": "My sales are down. How can I grow?"},
        )
        assert resp.status_code == 401

    def test_copilot_endpoint_enforces_merchant_scoping(self, other_auth_headers):
        resp = client.post(
            f"/api/merchants/{MERCHANT_ID}/copilot/chat",
            json={"message": "My sales are down. How can I grow?"},
            headers=other_auth_headers,
        )
        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

    def test_copilot_sse_streaming_with_deterministic_fallback(self, auth_headers, monkeypatch):
        """
        Golden Demo Acceptance test:
        Even when GEMINI_API_KEY is unset, merchant can ask golden demo question and receives
        real grounded figures streamed via SSE.
        """
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

        resp = client.post(
            f"/api/merchants/{MERCHANT_ID}/copilot/chat",
            json={"message": "My sales are down. How can I grow?"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        # Parse SSE lines
        raw_body = resp.text
        lines = [line.strip() for line in raw_body.split("\n") if line.startswith("data:")]
        events = [json.loads(line[5:].strip()) for line in lines]

        # Verify tool events
        tool_events = [e for e in events if e.get("type") == "tool"]
        tool_names = [e["name"] for e in tool_events]
        assert "get_sales_insights" in tool_names
        assert "find_growth_opportunities" in tool_names
        assert "recommend_growth_action" in tool_names

        # Verify opportunity event
        opp_events = [e for e in events if e.get("type") == "opportunity"]
        assert len(opp_events) == 1
        opp_data = opp_events[0]["opportunity"]
        assert opp_data["estimated_discount_exposure"] == 2999.0
        assert opp_data["policy_outcome"] == "requires_approval"

        # Verify text content chunks
        chunks = [e["text"] for e in events if e.get("type") == "chunk"]
        full_text = "".join(chunks)

        # PRD Acceptance (§6.1, §10): Real numbers from SalesRecordModel, no hallucinated figures
        assert "Velocity Pro" in full_text
        assert "37.5%" in full_text
        assert "Performance Running Socks" in full_text
        assert "10.0%" in full_text
        assert "₹2,999.00" in full_text
        assert "36.65%" in full_text

        # Verify completion event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
