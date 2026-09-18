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
    MerchantModel, MerchantRulesModel, ProductModel, MandateModel,
    SalesRecordModel, CartModel, CartItemModel
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
        # Idempotent — skip if merchant already exists, but ensure sales history & growth rules are seeded
        existing = db.get(MerchantModel, MERCHANT_ID)
        if existing:
            print(f"Merchant '{MERCHANT_ID}' already exists — checking sales history & growth rules…")
            if existing.rules:
                if existing.rules.growth_actions_enabled is None or not existing.rules.growth_actions_enabled:
                    existing.rules.growth_actions_enabled = True
                if existing.rules.growth_approval_threshold_amount is None:
                    existing.rules.growth_approval_threshold_amount = 2000.0
                if existing.rules.max_ai_discount_pct < 15.0:
                    existing.rules.max_ai_discount_pct = 15.0
                db.commit()
            seed_sales_history(db, MERCHANT_ID)
            print("Seed verification complete.")
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

        # --- Rules (§11 & Merchant Growth AI PRD §10) ---
        # max_ai_discount_pct=15.0, growth_approval_threshold_amount=2000.0, growth_actions_enabled=True
        rules = MerchantRulesModel(
            merchant_id=MERCHANT_ID,
            max_ai_discount_pct=15.0,
            upsell_enabled=True,
            preferred_categories=["footwear", "accessories"],
            min_margin_pct=15.0,
            approval_threshold_amount=15000.0,
            growth_approval_threshold_amount=2000.0,
            growth_actions_enabled=True,
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

        seed_sales_history(db, MERCHANT_ID)

    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


def seed_sales_history(db, merchant_id: str):
    """
    Seed 28 days of historical sales records (§6.2, §8.3, §10):
    - Velocity Pro (prod_001): down ~35% (8 units/wk prior -> 5 units/wk recent).
    - Performance Socks (prod_006): defined complement with low historical attach rate.
    - Other products for realistic top/declining trends.
    Also seed past carts to establish historical co-occurrence history.
    """
    existing_records = db.query(SalesRecordModel).filter(SalesRecordModel.merchant_id == merchant_id).first()
    if existing_records:
        print("Sales records already exist — skipping sales history seeding.")
        return

    today = datetime.now(timezone.utc).date()

    # prod_001: Velocity Pro (price 5499)
    # Days -27 to -14 (prior 14 days): 16 units total = 8 units/week (revenue: 16 * 5499 = 87,984)
    prior_days_p1 = [-27, -25, -23, -21, -20, -18, -16, -15]
    for d_offset in prior_days_p1:
        d = today + timedelta(days=d_offset)
        db.add(SalesRecordModel(
            merchant_id=merchant_id,
            product_id="prod_001",
            date=d,
            units_sold=2,
            revenue=2 * 5499.0,
        ))

    # Days -13 to 0 (recent 14 days): 10 units total = 5 units/week (revenue: 10 * 5499 = 54,990)
    # Pace: 5 units/week. Drop from 8 -> 5 = 37.5% drop (~35%)
    recent_days_p1 = [-13, -11, -9, -7, -5, -3, -2, -1]
    for i, d_offset in enumerate(recent_days_p1):
        units = 2 if i in (0, 3) else 1
        d = today + timedelta(days=d_offset)
        db.add(SalesRecordModel(
            merchant_id=merchant_id,
            product_id="prod_001",
            date=d,
            units_sold=units,
            revenue=units * 5499.0,
        ))

    # prod_006: Performance Socks (price 499)
    # Low sales volume across the month
    for d_offset in [-26, -20, -14, -10, -5, -1]:
        d = today + timedelta(days=d_offset)
        db.add(SalesRecordModel(
            merchant_id=merchant_id,
            product_id="prod_006",
            date=d,
            units_sold=1,
            revenue=499.0,
        ))

    # prod_004: Court Classic (price 3499) — top product, steady ~10 units/week
    for d_offset in range(-27, 0, 2):
        d = today + timedelta(days=d_offset)
        db.add(SalesRecordModel(
            merchant_id=merchant_id,
            product_id="prod_004",
            date=d,
            units_sold=2,
            revenue=2 * 3499.0,
        ))

    # prod_003: Trail Runner X (price 4999) — steady ~6 units/week
    for d_offset in range(-26, 0, 3):
        d = today + timedelta(days=d_offset)
        db.add(SalesRecordModel(
            merchant_id=merchant_id,
            product_id="prod_003",
            date=d,
            units_sold=2,
            revenue=2 * 4999.0,
        ))

    # Seed historical carts to establish low attach rate for prod_001 -> prod_006
    # 10 past carts for prod_001: 9 bought alone, only 1 bought with prod_006 (10% attach rate)
    for i in range(10):
        cart_id = f"cart_hist_demo_{i+1:02d}"
        if not db.get(CartModel, cart_id):
            c = CartModel(
                id=cart_id,
                merchant_id=merchant_id,
                buyer_id=f"buyer_hist_{i+1}",
                total=5499.0 if i > 0 else (5499.0 + 499.0),
                created_at=datetime.now(timezone.utc) - timedelta(days=20 - i * 2),
            )
            db.add(c)
            db.add(CartItemModel(
                cart_id=cart_id,
                product_id="prod_001",
                quantity=1,
                unit_price=5499.0,
                role="primary",
            ))
            if i == 0:
                db.add(CartItemModel(
                    cart_id=cart_id,
                    product_id="prod_006",
                    quantity=1,
                    unit_price=499.0,
                    role="upsell",
                ))

    db.commit()
    print("Seeded historical sales records and cart co-occurrence history.")


if __name__ == "__main__":
    seed()

