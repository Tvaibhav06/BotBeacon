"""
Seed script — §11 of the Build Plan.
Merchant: Velocity Sports
Products: 8 named SKUs + 10 filler SKUs = 18 total (so "AI considered 18 products" is accurate)
Mandate: mandate_demo_buyer_1 — max ₹6,000, footwear + accessories, expires 30d from now
"""
import sys
import os
from datetime import datetime, timezone, timedelta

# Ensure the backend/app package is importable when run as `python -m app.db.seed`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.security import hash_password
from app.db.session import SessionLocal, engine, Base
from app.models import (
    MerchantModel, MerchantRulesModel, ProductModel, MandateModel
)


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

MERCHANT_ID = "merchant_velocity_sports"
MERCHANT_EMAIL = "admin@velocitysports.demo"
MERCHANT_PASSWORD = "demo1234"

NAMED_PRODUCTS = [
    {
        "id": "prod_001",
        "name": "Velocity Pro",
        "category": "footwear",
        "tags": ["running", "men", "performance"],
        "price": 5499.0,
        "cost": 3200.0,
        "stock": 40,
        "complement_categories": ["accessories"],
        "description": "High-performance running shoe with responsive cushioning.",
    },
    {
        "id": "prod_002",
        "name": "Velocity Pro (Premium)",
        "category": "footwear",
        "tags": ["running", "men", "premium"],
        "price": 8999.0,
        "cost": 5200.0,
        "stock": 15,
        "complement_categories": ["accessories"],
        "description": "Premium edition with carbon-fibre plate and advanced foam.",
    },
    {
        "id": "prod_003",
        "name": "Trail Runner X",
        "category": "footwear",
        "tags": ["trail", "running", "unisex"],
        "price": 4999.0,
        "cost": 2800.0,
        "stock": 25,
        "complement_categories": ["accessories"],
        "description": "Aggressive outsole for off-road terrain.",
    },
    {
        "id": "prod_004",
        "name": "Court Classic",
        "category": "footwear",
        "tags": ["court", "casual", "unisex"],
        "price": 3499.0,
        "cost": 1900.0,
        "stock": 60,
        "complement_categories": ["accessories"],
        "description": "Clean silhouette for court and street.",
    },
    {
        "id": "prod_005",
        "name": "Everyday Sneaker",
        "category": "footwear",
        "tags": ["casual", "unisex", "everyday"],
        "price": 2999.0,
        "cost": 1600.0,
        "stock": 80,
        "complement_categories": ["accessories"],
        "description": "Lightweight everyday trainer.",
    },
    {
        "id": "prod_006",
        "name": "Performance Socks (2-pack)",
        "category": "accessories",
        "tags": ["socks", "running", "unisex"],
        "price": 499.0,
        "cost": 220.0,
        "stock": 200,
        "complement_categories": [],
        "description": "Moisture-wicking running socks, pack of 2 pairs.",
    },
    {
        "id": "prod_007",
        "name": "Cushion Insoles",
        "category": "accessories",
        "tags": ["insoles", "comfort", "unisex"],
        "price": 699.0,
        "cost": 300.0,
        "stock": 90,
        "complement_categories": [],
        "description": "Gel-cushion insoles for any shoe.",
    },
    {
        "id": "prod_008",
        "name": "Running Cap",
        "category": "accessories",
        "tags": ["cap", "running", "unisex"],
        "price": 599.0,
        "cost": 260.0,
        "stock": 70,
        "complement_categories": [],
        "description": "Lightweight reflective running cap.",
    },
]

# 10 filler SKUs to reach 18 total products (makes "AI considered 18" accurate)
FILLER_PRODUCTS = [
    {"id": "prod_f01", "name": "Speed Elite",       "category": "footwear",    "tags": ["running", "elite"],     "price": 6499.0, "cost": 3900.0, "stock": 20},
    {"id": "prod_f02", "name": "Marathon Pro",       "category": "footwear",    "tags": ["marathon", "men"],      "price": 7299.0, "cost": 4200.0, "stock": 10},
    {"id": "prod_f03", "name": "Recovery Slide",     "category": "footwear",    "tags": ["recovery", "unisex"],   "price": 1499.0, "cost":  700.0, "stock": 50},
    {"id": "prod_f04", "name": "Kids Runner",        "category": "footwear",    "tags": ["kids", "running"],      "price": 1999.0, "cost":  900.0, "stock": 35},
    {"id": "prod_f05", "name": "Hiking Boot",        "category": "footwear",    "tags": ["hiking", "outdoor"],    "price": 5999.0, "cost": 3500.0, "stock": 18},
    {"id": "prod_f06", "name": "Compression Sleeve", "category": "accessories", "tags": ["compression", "knee"], "price": 799.0,  "cost":  350.0, "stock": 120},
    {"id": "prod_f07", "name": "Water Bottle 750ml", "category": "accessories", "tags": ["hydration", "running"],"price": 599.0,  "cost":  250.0, "stock": 85},
    {"id": "prod_f08", "name": "Reflective Vest",    "category": "accessories", "tags": ["safety", "running"],   "price": 899.0,  "cost":  400.0, "stock": 45},
    {"id": "prod_f09", "name": "Shoe Bag",           "category": "accessories", "tags": ["bag", "travel"],       "price": 349.0,  "cost":  150.0, "stock": 110},
    {"id": "prod_f10", "name": "Sport Sunglasses",   "category": "accessories", "tags": ["eyewear", "outdoor"],  "price": 1299.0, "cost":  600.0, "stock": 30},
]


def seed():
    print("Running seed script…")

    db = SessionLocal()
    try:
        # Idempotent — skip if merchant already exists
        existing = db.get(MerchantModel, MERCHANT_ID)
        if existing:
            print(f"Merchant '{MERCHANT_ID}' already exists — skipping seed.")
            return

        # --- Merchant ---
        merchant = MerchantModel(
            id=MERCHANT_ID,
            name="Velocity Sports",
            email=MERCHANT_EMAIL,
            hashed_password=hash_password(MERCHANT_PASSWORD),
            passport_status="active",
        )
        db.add(merchant)

        # --- Rules (§11) ---
        # approval_threshold_amount=15000: AI can sell above ₹15k only with merchant approval.
        # This is NOT a maximum transaction limit.
        rules = MerchantRulesModel(
            merchant_id=MERCHANT_ID,
            max_ai_discount_pct=10.0,
            upsell_enabled=True,
            preferred_categories=["footwear", "accessories"],
            min_margin_pct=15.0,
            approval_threshold_amount=15000.0,
        )
        db.add(rules)

        # --- Products ---
        for p in NAMED_PRODUCTS:
            db.add(ProductModel(
                id=p["id"],
                merchant_id=MERCHANT_ID,
                name=p["name"],
                category=p["category"],
                tags=p.get("tags", []),
                price=p["price"],
                cost=p["cost"],
                stock=p["stock"],
                complement_categories=p.get("complement_categories", []),
                description=p.get("description", ""),
                status="active",
            ))

        for p in FILLER_PRODUCTS:
            db.add(ProductModel(
                id=p["id"],
                merchant_id=MERCHANT_ID,
                name=p["name"],
                category=p["category"],
                tags=p.get("tags", []),
                price=p["price"],
                cost=p["cost"],
                stock=p.get("stock", 0),
                complement_categories=[],
                description="",
                status="active",
            ))

        # --- Mandate (§11) ---
        mandate = MandateModel(
            id="mandate_demo_buyer_1",
            buyer_id="demo-buyer-1",
            max_amount=6000.0,
            category_scope=["footwear", "accessories"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(mandate)

        db.commit()
        print(f"Seed complete: 1 merchant, {len(NAMED_PRODUCTS) + len(FILLER_PRODUCTS)} products, 1 mandate.")
        print(f"  Login: {MERCHANT_EMAIL} / {MERCHANT_PASSWORD}")

    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
