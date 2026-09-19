"""
Audit API router.
Note: The active audit routes (/api/merchants/{merchant_id}/audit-log and
/api/transactions/{transaction_id}/audit-trail) are registered and served by
transactions.router to preserve existing routing priority and behavior.
"""
from fastapi import APIRouter

router = APIRouter(tags=["Audit"])

