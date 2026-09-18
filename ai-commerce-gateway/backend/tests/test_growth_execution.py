"""
Phase 4 tests — Growth Approval, n8n Execution & Callback Invariants (§6.4, §6.5, §6.6, §6.7, §7).

Critical Acceptance Tests:
1. Blocked actions NEVER call n8n.
2. Allowed actions execute without approval.
3. Approval re-check ALWAYS uses fresh current rules (second policy check).
4. Tightened rules between proposal and click BLOCKS an earlier approval.
5. n8n webhook contains X-Gateway-Api-Key and zero secrets in JSON payload.
6. Callback requires valid X-N8N-Callback-Key header.
7. Callback rejects timestamps older than 5 minutes.
8. Duplicate callbacks are safe no-ops (idempotency keyed on execution_id).
9. Audit trail captures growth_analysis, both growth_approval checks, and growth_execution.
"""
import hmac
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models import (
    MerchantModel,
    MerchantRulesModel,
    ProductModel,
    GrowthOpportunityModel,
    GrowthExecutionModel,
    AuditLogModel,
)

settings = get_settings()
client = TestClient(app)

MERCHANT_ID = "merchant_velocity_sports"


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": MERCHANT_ID, "role": "merchant_admin"})
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


class TestApprovalAndPolicyInvariants:
    """Tests for mandatory double policy check and n8n triggering (§6.4, §6.5, §6.6)."""

    def test_blocked_action_never_calls_n8n(self, auth_headers, db_session):
        """
        Critical safety test:
        If current merchant rules block the opportunity at approval time,
        n8n is NEVER called and opportunity status becomes 'blocked'.
        """
        # Ensure rules currently block 20% discount (max_ai_discount_pct=15%)
        rules = db_session.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        rules.max_ai_discount_pct = 15.0
        rules.growth_actions_enabled = True
        db_session.commit()

        # Create an opportunity with discount_pct = 20%
        opp_id = f"opp_test_blocked_{uuid.uuid4().hex[:6]}"
        opp = GrowthOpportunityModel(
            id=opp_id,
            merchant_id=MERCHANT_ID,
            opportunity_type="declining_sales",
            title="Test Blocked Opportunity",
            evidence={},
            recommended_action={
                "type": "discount_bundle",
                "product_ids": ["prod_001"],
                "discount_pct": 20.0,  # exceeds 15% max
                "campaign_duration_weeks": 1,
            },
            estimated_discount_exposure=3500.0,
            policy_outcome="pending_approval",
            policy_reasons=[],
            status="pending_approval",
        )
        db_session.add(opp)
        db_session.commit()

        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/{opp_id}/approve",
                headers=auth_headers,
            )
            # Must be rejected with HTTP 400
            assert resp.status_code == 400
            assert "blocked by current merchant rules" in resp.json()["detail"]

            # n8n trigger must PROVABLY NEVER have been called
            mock_trigger.assert_not_called()

        # Verify status in database updated to blocked
        db_session.refresh(opp)
        assert opp.status == "blocked"
        assert opp.policy_outcome == "blocked"

    def test_approval_recheck_uses_fresh_rules_and_tightened_rules_block(self, auth_headers, db_session):
        """
        PRD §6.4 & §10:
        Opportunity created with 10% discount when max_ai_discount_pct=15% (first check -> requires_approval).
        Between creation and click, merchant tightens max_ai_discount_pct to 5%.
        At click time, second check re-evaluates fresh rules and rejects as blocked.
        """
        # 1. Start with permissive rules
        rules = db_session.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        rules.max_ai_discount_pct = 15.0
        rules.growth_actions_enabled = True
        rules.growth_approval_threshold_amount = 2000.0
        db_session.commit()

        opp_id = f"opp_tighten_{uuid.uuid4().hex[:6]}"
        opp = GrowthOpportunityModel(
            id=opp_id,
            merchant_id=MERCHANT_ID,
            opportunity_type="declining_sales",
            title="Test Tighten Rules",
            evidence={},
            recommended_action={
                "type": "discount_bundle",
                "product_ids": ["prod_001"],
                "discount_pct": 10.0,
                "campaign_duration_weeks": 1,
            },
            estimated_discount_exposure=2999.0,
            policy_outcome="requires_approval",
            policy_reasons=["exposure exceeds threshold"],
            status="pending_approval",
        )
        db_session.add(opp)
        db_session.commit()

        # 2. Merchant tightens max discount to 5% in DB
        rules.max_ai_discount_pct = 5.0
        db_session.commit()

        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/{opp_id}/approve",
                headers=auth_headers,
            )
            assert resp.status_code == 400
            assert "exceeds maximum allowed 5.0%" in resp.json()["detail"]
            mock_trigger.assert_not_called()

        db_session.refresh(opp)
        assert opp.status == "blocked"

    def test_approved_path_executes_and_calls_n8n(self, auth_headers, db_session):
        """
        Golden Demo Path 1:
        When current rules allow the action, clicking Approve creates an execution,
        sets status to 'executing', and triggers n8n.
        """
        rules = db_session.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        rules.max_ai_discount_pct = 15.0
        rules.growth_actions_enabled = True
        rules.growth_approval_threshold_amount = 2000.0
        db_session.commit()

        opp_id = f"opp_approve_{uuid.uuid4().hex[:6]}"
        opp = GrowthOpportunityModel(
            id=opp_id,
            merchant_id=MERCHANT_ID,
            opportunity_type="declining_sales",
            title="Velocity Pro + Socks Bundle",
            evidence={"trend": -35.0},
            recommended_action={
                "type": "discount_bundle",
                "product_ids": ["prod_001", "prod_006"],
                "discount_pct": 10.0,
                "campaign_duration_weeks": 1,
                "audience": "configured_demo_audience",
            },
            estimated_discount_exposure=2999.0,
            policy_outcome="requires_approval",
            policy_reasons=["exposure exceeds threshold"],
            status="pending_approval",
        )
        db_session.add(opp)
        db_session.commit()

        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            mock_trigger.return_value = (True, None, {"action": "discount_bundle", "status": "dispatched"})

            resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/{opp_id}/approve",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "executing"
            assert data["opportunity_id"] == opp_id
            assert "execution_id" in data

            # Verify n8n was triggered
            mock_trigger.assert_called_once()
            call_kwargs = mock_trigger.call_args.kwargs
            assert call_kwargs["opportunity_id"] == opp_id
            assert call_kwargs["merchant_id"] == MERCHANT_ID

        # Verify opportunity status is executing in DB
        db_session.refresh(opp)
        assert opp.status == "executing"

    def test_double_approval_audit_entries_exist(self, auth_headers, db_session):
        """
        PRD §6.7 & §10:
        An approved opportunity produces TWO growth_approval audit entries
        (first check at proposal, second check at click).
        """
        rules = db_session.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        rules.max_ai_discount_pct = 15.0
        rules.growth_actions_enabled = True
        rules.growth_approval_threshold_amount = 2000.0
        # Clean any prior opportunities for this merchant to ensure clean scan test
        db_session.query(GrowthExecutionModel).delete()
        db_session.query(GrowthOpportunityModel).filter_by(merchant_id=MERCHANT_ID).delete()
        db_session.commit()

        # Run scan which creates opportunity and logs first check
        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            mock_trigger.return_value = (True, None, {})
            scan_resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/scan?discount_pct=10.0",
                headers=auth_headers,
            )
            assert scan_resp.status_code == 200

        opps = db_session.query(GrowthOpportunityModel).filter_by(merchant_id=MERCHANT_ID, status="pending_approval").all()
        assert len(opps) > 0
        target_opp = opps[0]

        # Now approve it, triggering second check
        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            mock_trigger.return_value = (True, None, {})
            approve_resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/{target_opp.id}/approve",
                headers=auth_headers,
            )
            assert approve_resp.status_code == 200

        # Query audit logs for growth_approval stages for this opportunity
        audit_entries = (
            db_session.query(AuditLogModel)
            .filter(
                AuditLogModel.merchant_id == MERCHANT_ID,
                AuditLogModel.stage == "growth_approval",
            )
            .order_by(AuditLogModel.timestamp.desc())
            .all()
        )
        opp_audits = [a for a in audit_entries if a.payload.get("opportunity_id") == target_opp.id]
        # Must have at least 2 entries: initial_policy_gate and recheck_at_approval_click
        assert len(opp_audits) == 2
        checks = {a.payload.get("check") for a in opp_audits}
        assert checks == {"initial_policy_gate", "recheck_at_approval_click"}

    def test_reject_flow_never_calls_n8n(self, auth_headers, db_session):
        """Rejecting an opportunity sets status=rejected_by_merchant and never calls n8n (§6.5)."""
        opp_id = f"opp_reject_{uuid.uuid4().hex[:6]}"
        opp = GrowthOpportunityModel(
            id=opp_id,
            merchant_id=MERCHANT_ID,
            opportunity_type="declining_sales",
            title="Reject Test",
            evidence={},
            recommended_action={"type": "discount_bundle"},
            estimated_discount_exposure=2500.0,
            policy_outcome="requires_approval",
            status="pending_approval",
        )
        db_session.add(opp)
        db_session.commit()

        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/{opp_id}/reject",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            mock_trigger.assert_not_called()

        db_session.refresh(opp)
        assert opp.status == "rejected_by_merchant"

    def test_allowed_action_executes_without_merchant_approval(self, auth_headers, db_session):
        """
        PRD §6.4 & §10:
        When action exposure is below merchant's growth_approval_threshold_amount,
        policy outcome is ALLOWED.
        During scan/discovery, the opportunity immediately transitions to 'executing'
        and triggers n8n without waiting for merchant approval.
        """
        rules = db_session.query(MerchantRulesModel).filter_by(merchant_id=MERCHANT_ID).first()
        rules.max_ai_discount_pct = 15.0
        rules.growth_actions_enabled = True
        # Set threshold high so exposure (2999.0) is ALLOWED
        rules.growth_approval_threshold_amount = 10000.0
        # Clean prior opportunities
        db_session.query(GrowthExecutionModel).delete()
        db_session.query(GrowthOpportunityModel).filter_by(merchant_id=MERCHANT_ID).delete()
        db_session.commit()

        with patch("app.api.growth.trigger_growth_action") as mock_trigger:
            mock_trigger.return_value = (True, None, {"action": "discount_bundle"})

            scan_resp = client.post(
                f"/api/merchants/{MERCHANT_ID}/growth/opportunities/scan?discount_pct=10.0",
                headers=auth_headers,
            )
            assert scan_resp.status_code == 200

            # Must have triggered n8n directly
            mock_trigger.assert_called()

        # Check DB state
        opps = db_session.query(GrowthOpportunityModel).filter_by(merchant_id=MERCHANT_ID).all()
        assert len(opps) > 0
        allowed_opp = next(o for o in opps if o.policy_outcome == "allowed")
        assert allowed_opp.status == "executing"

        # Execution record must exist
        execution = db_session.query(GrowthExecutionModel).filter_by(opportunity_id=allowed_opp.id).first()
        assert execution is not None
        assert execution.status == "executing"

    def test_n8n_webhook_payload_has_header_and_zero_secrets(self, monkeypatch):
        """
        PRD §6.6 & §9:
        FastAPI -> n8n webhook sends X-Gateway-Api-Key header
        and JSON payload contains business data only — zero API secrets or callback keys.
        """
        from app.integrations.n8n_client import trigger_growth_action

        monkeypatch.setattr(settings, "N8N_GROWTH_WEBHOOK_URL", "https://n8n.internal.example.com/webhook/growth")
        monkeypatch.setattr(settings, "N8N_WEBHOOK_API_KEY", "test-gateway-secret-key-123")

        recorded_request = {}

        def mock_post(url, json=None, headers=None):
            recorded_request["url"] = url
            recorded_request["json"] = json
            recorded_request["headers"] = headers
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

        with patch("httpx.Client.post", side_effect=mock_post):
            success, err, payload = trigger_growth_action(
                execution_id="exec_sec_test",
                opportunity_id="opp_sec_test",
                merchant_id=MERCHANT_ID,
                action={"type": "discount_bundle", "discount_pct": 10.0},
                products=[{"id": "prod_001", "name": "Velocity Pro"}],
            )
            assert success is True
            assert err is None

        # Verify header
        assert recorded_request["headers"]["X-Gateway-Api-Key"] == "test-gateway-secret-key-123"

        # Verify payload contains zero secrets
        payload_data = recorded_request["json"]
        assert payload_data["execution_id"] == "exec_sec_test"
        assert payload_data["opportunity_id"] == "opp_sec_test"
        assert "callback_url" in payload_data
        for forbidden in ["api_key", "secret", "token", "password", "key"]:
            assert forbidden not in payload_data


class TestCallbackAndIdempotency:
    """Tests for n8n callback authentication, replay protection, and idempotency (§6.6)."""

    @pytest.fixture
    def active_execution(self, db_session):
        opp_id = f"opp_cb_{uuid.uuid4().hex[:6]}"
        opp = GrowthOpportunityModel(
            id=opp_id,
            merchant_id=MERCHANT_ID,
            opportunity_type="declining_sales",
            title="Callback Test Opp",
            evidence={},
            recommended_action={},
            estimated_discount_exposure=2999.0,
            policy_outcome="requires_approval",
            status="executing",
        )
        db_session.add(opp)

        exec_id = f"exec_cb_{uuid.uuid4().hex[:6]}"
        execution = GrowthExecutionModel(
            id=exec_id,
            opportunity_id=opp_id,
            status="executing",
            request_payload={"action": "test"},
            result_payload={},
        )
        db_session.add(execution)
        db_session.commit()
        return execution

    def test_callback_requires_valid_key(self, active_execution):
        """Missing or wrong X-N8N-Callback-Key header returns HTTP 401."""
        body = {
            "execution_id": active_execution.id,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 1. No header
        resp_no_header = client.post("/api/growth/execution-callback", json=body)
        assert resp_no_header.status_code == 401

        # 2. Wrong header
        resp_wrong_key = client.post(
            "/api/growth/execution-callback",
            json=body,
            headers={"X-N8N-Callback-Key": "wrong-secret-key"},
        )
        assert resp_wrong_key.status_code == 401

    def test_callback_rejects_stale_timestamp(self, active_execution):
        """Callback with timestamp older than 5 minutes is rejected with HTTP 400 (§6.6)."""
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        body = {
            "execution_id": active_execution.id,
            "status": "completed",
            "timestamp": stale_time,
        }
        resp = client.post(
            "/api/growth/execution-callback",
            json=body,
            headers={"X-N8N-Callback-Key": settings.N8N_CALLBACK_API_KEY},
        )
        assert resp.status_code == 400
        assert "timestamp expired" in resp.json()["detail"]

    def test_callback_success_updates_state_and_audit(self, active_execution, db_session):
        """Valid callback updates execution and opportunity to completed and writes growth_execution audit."""
        body = {
            "execution_id": active_execution.id,
            "status": "completed",
            "n8n_run_id": "run_98765",
            "result": {"emails_sent": 100, "campaign_id": "camp_abc"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        resp = client.post(
            "/api/growth/execution-callback",
            json=body,
            headers={"X-N8N-Callback-Key": settings.N8N_CALLBACK_API_KEY},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        db_session.refresh(active_execution)
        assert active_execution.status == "completed"
        assert active_execution.n8n_run_id == "run_98765"
        assert active_execution.result_payload["emails_sent"] == 100

        opp = db_session.get(GrowthOpportunityModel, active_execution.opportunity_id)
        assert opp.status == "completed"

        # Verify growth_execution audit event exists
        audit = (
            db_session.query(AuditLogModel)
            .filter(
                AuditLogModel.merchant_id == MERCHANT_ID,
                AuditLogModel.stage == "growth_execution",
            )
            .order_by(AuditLogModel.timestamp.desc())
            .first()
        )
        assert audit is not None
        assert audit.result.get("status") == "completed"

    def test_duplicate_callback_is_safe_noop(self, active_execution, db_session):
        """Duplicate callback for already completed execution returns 200 safe no-op without double-auditing."""
        body = {
            "execution_id": active_execution.id,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 1. First callback
        resp1 = client.post(
            "/api/growth/execution-callback",
            json=body,
            headers={"X-N8N-Callback-Key": settings.N8N_CALLBACK_API_KEY},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "success"

        # Count audit events before duplicate
        audit_count_before = (
            db_session.query(AuditLogModel)
            .filter(
                AuditLogModel.merchant_id == MERCHANT_ID,
                AuditLogModel.stage == "growth_execution",
            )
            .count()
        )

        # 2. Second callback with same execution_id
        resp2 = client.post(
            "/api/growth/execution-callback",
            json=body,
            headers={"X-N8N-Callback-Key": settings.N8N_CALLBACK_API_KEY},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_processed"

        # Count audit events after duplicate: MUST NOT have increased
        audit_count_after = (
            db_session.query(AuditLogModel)
            .filter(
                AuditLogModel.merchant_id == MERCHANT_ID,
                AuditLogModel.stage == "growth_execution",
            )
            .count()
        )
        assert audit_count_after == audit_count_before
