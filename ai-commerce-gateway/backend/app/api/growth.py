"""
Merchant Growth REST API — §6.4, §6.5, §6.6, §6.7, §7, §8.4.

Endpoints:
- GET  /api/merchants/{id}/growth/insights
- GET  /api/merchants/{id}/growth/opportunities
- POST /api/merchants/{id}/growth/opportunities/scan
- GET  /api/merchants/{id}/growth/opportunities/{oid}
- POST /api/merchants/{id}/growth/opportunities/{oid}/approve
- POST /api/merchants/{id}/growth/opportunities/{oid}/reject
- POST /api/growth/execution-callback

Security Invariants:
- All merchant-scoped routes enforce JWT.merchant_id == path.merchant_id (403 Access denied).
- On Approve, ALWAYS re-fetch current MerchantRulesModel and re-evaluate growth_policy_gate.
- If re-evaluation returns BLOCKED, n8n is NEVER called.
- Execution callback is authenticated via X-N8N-Callback-Key and checked via hmac.compare_digest.
- Callback rejects timestamps older than 5 minutes.
- Idempotency keyed strictly on execution_id (duplicate callbacks are safe no-ops).
"""
import hmac
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.orm import Session

from app.api.merchants import get_current_merchant
from app.audit.logger import write_audit_event
from app.core.config import get_settings
from app.core.logging import logger
from app.db.session import get_db
from app.engine.growth_detectors import (
    detect_declining_sales,
    detect_cross_sell_opportunities,
    get_sales_insights,
    build_growth_opportunity_proposal,
)
from app.engine.growth_policy import (
    growth_policy_gate,
    ActionForGrowthGate,
    ProductForGrowthGate,
    MerchantRulesForGrowthGate,
    BLOCKED,
    REQUIRES_APPROVAL,
    ALLOWED,
)
from app.integrations.n8n_client import trigger_growth_action
from app.models import (
    MerchantModel,
    MerchantRulesModel,
    ProductModel,
    GrowthOpportunityModel,
    GrowthExecutionModel,
)
from app.schemas import (
    GrowthOpportunity,
    GrowthExecution,
    GrowthInsightsResponse,
)

settings = get_settings()
router = APIRouter(tags=["growth"])


# ─────────────────────────────────────────────────────────────────────────────
# 1. Growth Insights
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/merchants/{merchant_id}/growth/insights", response_model=GrowthInsightsResponse)
def get_insights_endpoint(
    merchant_id: str,
    window_days: int = Query(default=14, ge=7, le=90),
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Live sales trend, top products, and declining products computed on demand (§6.2)."""
    if current.id != merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    insights = get_sales_insights(db, merchant_id, window_days=window_days)
    return insights


# ─────────────────────────────────────────────────────────────────────────────
# 2. Opportunities List & Detail
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/merchants/{merchant_id}/growth/opportunities")
def list_opportunities(
    merchant_id: str,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """List opportunities for a merchant with optional status filter."""
    if current.id != merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    query = db.query(GrowthOpportunityModel).filter(GrowthOpportunityModel.merchant_id == merchant_id)
    if status_filter:
        query = query.filter(GrowthOpportunityModel.status == status_filter)

    opps = query.order_by(GrowthOpportunityModel.created_at.desc()).all()
    return [
        {
            "id": o.id,
            "merchant_id": o.merchant_id,
            "opportunity_type": o.opportunity_type,
            "title": o.title,
            "evidence": o.evidence,
            "recommended_action": o.recommended_action,
            "estimated_discount_exposure": o.estimated_discount_exposure,
            "policy_outcome": o.policy_outcome,
            "policy_reasons": o.policy_reasons,
            "status": o.status,
            "created_at": o.created_at,
            "updated_at": o.updated_at,
        }
        for o in opps
    ]


@router.get("/merchants/{merchant_id}/growth/opportunities/{opportunity_id}")
def get_opportunity_detail(
    merchant_id: str,
    opportunity_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Full detail of a growth opportunity including latest execution."""
    if current.id != merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    opp = db.get(GrowthOpportunityModel, opportunity_id)
    if not opp or opp.merchant_id != merchant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    executions = (
        db.query(GrowthExecutionModel)
        .filter(GrowthExecutionModel.opportunity_id == opportunity_id)
        .order_by(GrowthExecutionModel.started_at.desc())
        .all()
    )

    return {
        "id": opp.id,
        "merchant_id": opp.merchant_id,
        "opportunity_type": opp.opportunity_type,
        "title": opp.title,
        "evidence": opp.evidence,
        "recommended_action": opp.recommended_action,
        "estimated_discount_exposure": opp.estimated_discount_exposure,
        "policy_outcome": opp.policy_outcome,
        "policy_reasons": opp.policy_reasons,
        "status": opp.status,
        "created_at": opp.created_at,
        "updated_at": opp.updated_at,
        "executions": [
            {
                "id": e.id,
                "n8n_run_id": e.n8n_run_id,
                "status": e.status,
                "request_payload": e.request_payload,
                "result_payload": e.result_payload,
                "error": e.error,
                "started_at": e.started_at,
                "completed_at": e.completed_at,
            }
            for e in executions
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Opportunity Scan (Detect + Propose)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/merchants/{merchant_id}/growth/opportunities/scan")
def scan_opportunities(
    merchant_id: str,
    discount_pct: float = Query(default=10.0, ge=1.0, le=50.0),
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Run detectors on demand and persist structured GrowthOpportunity proposals (§6.2, §6.3).
    Evaluates policy gate at creation time (First Check).
    """
    if current.id != merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    created_opportunities: list[dict] = []

    # 1. Run declining sales detector
    declining = detect_declining_sales(db, merchant_id, window_days=14)
    for dec in declining:
        primary_id = dec["product_id"]

        # Check if active opportunity already exists for this primary product
        existing = (
            db.query(GrowthOpportunityModel)
            .filter(
                GrowthOpportunityModel.merchant_id == merchant_id,
                GrowthOpportunityModel.opportunity_type == "declining_sales",
                GrowthOpportunityModel.status.in_(["new", "pending_approval", "executing"]),
            )
            .all()
        )
        if any(e.recommended_action.get("product_ids", [None])[0] == primary_id for e in existing):
            continue

        # Check for defined complement with low attach rate
        complements = detect_cross_sell_opportunities(db, merchant_id, primary_product_id=primary_id)
        comp_id = complements[0]["complement_product_id"] if complements else None

        proposal = build_growth_opportunity_proposal(
            db,
            merchant_id=merchant_id,
            opportunity_type="declining_sales",
            primary_product_id=primary_id,
            complement_product_id=comp_id,
            discount_pct=discount_pct,
            campaign_duration_weeks=1,
        )

        opp_id = f"opp_{uuid.uuid4().hex[:10]}"
        opp_model = GrowthOpportunityModel(
            id=opp_id,
            merchant_id=merchant_id,
            opportunity_type=proposal["opportunity_type"],
            title=proposal["title"],
            evidence=proposal["evidence"],
            recommended_action=proposal["recommended_action"],
            estimated_discount_exposure=proposal["estimated_discount_exposure"],
            policy_outcome=proposal["policy_outcome"],
            policy_reasons=proposal["policy_reasons"],
            status=proposal["status"],
        )
        db.add(opp_model)
        db.commit()
        db.refresh(opp_model)

        # Write First Check Audit Event (§6.7, §10)
        write_audit_event(
            db,
            merchant_id=merchant_id,
            stage="growth_approval",
            actor="system",
            payload={
                "check": "initial_policy_gate",
                "opportunity_id": opp_id,
                "action": proposal["recommended_action"],
                "estimated_discount_exposure": proposal["estimated_discount_exposure"],
            },
            result={
                "outcome": proposal["policy_outcome"],
                "reasons": proposal["policy_reasons"],
            },
        )

        # Autonomous execution path (§6.4): if ALLOWED, trigger immediately!
        if proposal["policy_outcome"] == ALLOWED:
            _execute_opportunity(db, opp_model)

        created_opportunities.append({"id": opp_model.id, "title": opp_model.title, "status": opp_model.status})

    # Log growth_analysis audit event
    write_audit_event(
        db,
        merchant_id=merchant_id,
        stage="growth_analysis",
        actor="system",
        payload={"trigger": "manual_scan", "window_days": 14},
        result={"new_opportunities_count": len(created_opportunities)},
    )

    return {
        "status": "success",
        "new_opportunities_count": len(created_opportunities),
        "opportunities": created_opportunities,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Approve & Reject Flows
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/merchants/{merchant_id}/growth/opportunities/{opportunity_id}/approve")
def approve_opportunity(
    merchant_id: str,
    opportunity_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Merchant clicks Approve (§6.4, §6.5).
    MANDATORY DOUBLE-CHECK:
    Always re-fetches CURRENT MerchantRulesModel and re-runs growth_policy_gate.
    Never trusts the stored first-check result.
    If blocked: rejects and n8n is NEVER called.
    """
    if current.id != merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    opp = db.get(GrowthOpportunityModel, opportunity_id)
    if not opp or opp.merchant_id != merchant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    if opp.status not in ("pending_approval", "new"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve opportunity with status '{opp.status}'",
        )

    # ── MANDATORY SECOND CHECK AGAINST FRESH CURRENT RULES ───────────────────
    merchant = db.get(MerchantModel, merchant_id)
    fresh_rules = merchant.rules if merchant else None
    rules_gate = MerchantRulesForGrowthGate(
        growth_actions_enabled=fresh_rules.growth_actions_enabled if fresh_rules else False,
        max_ai_discount_pct=fresh_rules.max_ai_discount_pct if fresh_rules else 0.0,
        min_margin_pct=fresh_rules.min_margin_pct if fresh_rules else 10.0,
        growth_approval_threshold_amount=fresh_rules.growth_approval_threshold_amount if fresh_rules else None,
    )

    # Load live products for bundle margin / stock re-check
    target_pids = opp.recommended_action.get("product_ids", [])
    live_products = db.query(ProductModel).filter(ProductModel.id.in_(target_pids)).all()
    gate_products = [
        ProductForGrowthGate(
            id=p.id,
            price=p.price,
            cost=p.cost,
            stock=p.stock,
            status=p.status,
        )
        for p in live_products
    ]

    action_gate = ActionForGrowthGate(
        type=opp.recommended_action.get("type", "discount_bundle"),
        discount_pct=float(opp.recommended_action.get("discount_pct", 0.0)),
        campaign_duration_weeks=int(opp.recommended_action.get("campaign_duration_weeks", 1)),
        estimated_discount_exposure=float(opp.estimated_discount_exposure),
        products=gate_products,
        audience=opp.recommended_action.get("audience", "configured_demo_audience"),
    )

    fresh_outcome, fresh_reasons = growth_policy_gate(action_gate, rules_gate)

    # Write Second Approval Check Audit Event (§6.7, §10)
    write_audit_event(
        db,
        merchant_id=merchant_id,
        stage="growth_approval",
        actor="merchant",
        payload={
            "check": "recheck_at_approval_click",
            "opportunity_id": opp.id,
            "action": opp.recommended_action,
            "estimated_discount_exposure": opp.estimated_discount_exposure,
            "current_rules": {
                "growth_actions_enabled": rules_gate.growth_actions_enabled,
                "max_ai_discount_pct": rules_gate.max_ai_discount_pct,
                "min_margin_pct": rules_gate.min_margin_pct,
                "growth_approval_threshold_amount": rules_gate.growth_approval_threshold_amount,
            },
        },
        result={
            "outcome": fresh_outcome,
            "reasons": fresh_reasons,
        },
    )

    # Hard Invariant: If blocked on second check, REJECT AND NEVER CALL n8n
    if fresh_outcome == BLOCKED:
        opp.status = "blocked"
        opp.policy_outcome = BLOCKED
        opp.policy_reasons = fresh_reasons
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Opportunity blocked by current merchant rules: {', '.join(fresh_reasons)}",
        )

    # Re-check passed! Execute action via n8n
    execution = _execute_opportunity(db, opp, live_products)
    return {
        "status": "executing",
        "opportunity_id": opp.id,
        "execution_id": execution.id,
        "recheck_outcome": fresh_outcome,
    }


@router.post("/merchants/{merchant_id}/growth/opportunities/{opportunity_id}/reject")
def reject_opportunity(
    merchant_id: str,
    opportunity_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Merchant rejects opportunity (§6.5). n8n is never called."""
    if current.id != merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    opp = db.get(GrowthOpportunityModel, opportunity_id)
    if not opp or opp.merchant_id != merchant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    opp.status = "rejected_by_merchant"
    db.commit()

    write_audit_event(
        db,
        merchant_id=merchant_id,
        stage="growth_approval",
        actor="merchant",
        payload={"action": "reject", "opportunity_id": opportunity_id},
        result={"status": "rejected_by_merchant"},
    )

    return {"status": "rejected_by_merchant", "opportunity_id": opp.id}


# ─────────────────────────────────────────────────────────────────────────────
# 5. n8n Execution Helper & Callback
# ─────────────────────────────────────────────────────────────────────────────

def _execute_opportunity(
    db: Session,
    opp: GrowthOpportunityModel,
    live_products: Optional[list[ProductModel]] = None,
) -> GrowthExecutionModel:
    """Trigger execution in n8n and track lifecycle."""
    if not live_products:
        pids = opp.recommended_action.get("product_ids", [])
        live_products = db.query(ProductModel).filter(ProductModel.id.in_(pids)).all()

    exec_id = f"exec_{uuid.uuid4().hex[:12]}"
    execution = GrowthExecutionModel(
        id=exec_id,
        opportunity_id=opp.id,
        status="executing",
        request_payload={},
        result_payload={},
    )
    opp.status = "executing"
    db.add(execution)
    db.commit()

    products_data = [
        {"id": p.id, "name": p.name, "category": p.category, "price": p.price}
        for p in live_products
    ]

    success, err, payload = trigger_growth_action(
        execution_id=exec_id,
        opportunity_id=opp.id,
        merchant_id=opp.merchant_id,
        action=opp.recommended_action,
        products=products_data,
    )

    execution.request_payload = payload

    if not success:
        execution.status = "failed"
        execution.error = err
        execution.completed_at = datetime.now(timezone.utc)
        opp.status = "failed"
        db.commit()

        write_audit_event(
            db,
            merchant_id=opp.merchant_id,
            stage="growth_execution",
            actor="system",
            payload=payload,
            result={"status": "failed", "error": err},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to trigger n8n growth action: {err}",
        )

    db.commit()
    return execution


@router.post("/growth/execution-callback")
def execution_callback(
    body: dict[str, Any],
    x_n8n_callback_key: Optional[str] = Header(None, alias="X-N8N-Callback-Key"),
    db: Session = Depends(get_db),
):
    """
    n8n reports execution results (§6.6).
    Authentication: X-N8N-Callback-Key matched via hmac.compare_digest.
    Replay Protection: rejects timestamps older than 5 minutes.
    Idempotency: keyed on execution_id; already-terminal executions return 200 safe no-op.
    """
    # 1. Authenticate shared key
    if not x_n8n_callback_key or not hmac.compare_digest(x_n8n_callback_key, settings.N8N_CALLBACK_API_KEY):
        logger.warning("Callback authentication failure: invalid or missing X-N8N-Callback-Key")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid callback key")

    # 2. Replay / Timestamp validation (5 minutes)
    ts_str = body.get("timestamp")
    if ts_str:
        try:
            cb_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_seconds = (now - cb_time).total_seconds()
            if age_seconds > 300:  # 5 minutes
                logger.warning("Callback rejected: timestamp expired (%s s old)", age_seconds)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Callback timestamp expired")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timestamp format")

    # 3. Idempotency on execution_id
    exec_id = body.get("execution_id")
    if not exec_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing execution_id")

    execution = db.get(GrowthExecutionModel, exec_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution '{exec_id}' not found")

    # If already completed or failed, safe no-op (§6.6)
    if execution.status in ("completed", "failed"):
        logger.info("Duplicate callback received for terminal execution_id=%s — safe no-op", exec_id)
        return {"status": "already_processed", "execution_id": exec_id, "execution_status": execution.status}

    opp = db.get(GrowthOpportunityModel, execution.opportunity_id)
    merchant_id = opp.merchant_id if opp else "unknown"

    cb_status = body.get("status", "completed")
    n8n_run_id = body.get("n8n_run_id")
    result_payload = body.get("result", {})
    error_msg = body.get("error")

    execution.n8n_run_id = n8n_run_id
    execution.result_payload = result_payload
    execution.completed_at = datetime.now(timezone.utc)

    if cb_status in ("completed", "success"):
        execution.status = "completed"
        if opp:
            opp.status = "completed"
        db.commit()

        write_audit_event(
            db,
            merchant_id=merchant_id,
            stage="growth_execution",
            actor="system",
            payload={"execution_id": exec_id, "opportunity_id": opp.id if opp else None},
            result={"status": "completed", "result": result_payload, "n8n_run_id": n8n_run_id},
        )
        logger.info("Growth execution %s successfully marked completed", exec_id)
        return {"status": "success", "execution_id": exec_id, "opportunity_status": "completed"}
    else:
        execution.status = "failed"
        execution.error = error_msg or "Execution failed reported by n8n"
        if opp:
            opp.status = "failed"
        db.commit()

        write_audit_event(
            db,
            merchant_id=merchant_id,
            stage="growth_execution",
            actor="system",
            payload={"execution_id": exec_id, "opportunity_id": opp.id if opp else None},
            result={"status": "failed", "error": execution.error},
        )
        logger.warning("Growth execution %s marked failed: %s", exec_id, execution.error)
        return {"status": "failed", "execution_id": exec_id, "error": execution.error}
