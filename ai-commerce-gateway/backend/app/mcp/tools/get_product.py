"""
get_product MCP tool — §6.
Returns full ProductPublic for one product (cost field excluded — buyer must not see margin).

Input:  { "product_id": str }
Output: ProductPublic object or error dict
"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.models import ProductModel
from app.schemas import ProductPublic


def get_product(product_id: str) -> dict:
    """
    Fetch one product by ID.
    Returns ProductPublic — cost is intentionally omitted (§2 / §5).
    Returns an error dict if not found or not active.
    """
    db = SessionLocal()
    try:
        product = db.get(ProductModel, product_id)
        if not product or product.status != "active":
            return {"error": f"Product '{product_id}' not found or inactive"}
        return ProductPublic.model_validate(product).model_dump()
    finally:
        db.close()
