"""
search_catalog MCP tool — §6.
Deterministic. No LLM. Category / keyword / price filtering only.

Input:  { "query": str, "max_price": float|None, "category": str|None, "limit": int }
Output: { "products": [ProductPublic], "considered_count": int }
"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.models import ProductModel, MerchantModel
from app.schemas import ProductPublic


def search_catalog(
    query: str = "",
    max_price: float | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Search the active merchant catalog.
    Returns only ProductPublic objects — cost is never included.
    Only products from merchants with an ACTIVE passport are returned.
    """
    db = SessionLocal()
    try:
        q = (
            db.query(ProductModel)
            .join(MerchantModel, ProductModel.merchant_id == MerchantModel.id)
            .filter(
                MerchantModel.passport_status == "active",
                ProductModel.status == "active",
                ProductModel.stock > 0,
            )
        )

        # Category filter (exact match, case-insensitive)
        if category:
            q = q.filter(ProductModel.category.ilike(category.strip()))

        # Price ceiling
        if max_price is not None:
            q = q.filter(ProductModel.price <= max_price)

        all_matching = q.all()
        considered_count = len(all_matching)

        # Keyword scoring: rank by how well the product name/description/tags match the query
        if query.strip():
            keywords = [kw.lower() for kw in query.strip().split()]

            def score(p: ProductModel) -> int:
                text = f"{p.name} {p.description} {' '.join(p.tags)}".lower()
                return sum(1 for kw in keywords if kw in text)

            all_matching.sort(key=score, reverse=True)

        results = all_matching[:limit]
        return {
            "products": [ProductPublic.model_validate(p).model_dump() for p in results],
            "considered_count": considered_count,
        }
    finally:
        db.close()
