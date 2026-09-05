"""
Catalog management routes.
POST /api/merchants/{id}/catalog          — manual add / edit one product
POST /api/merchants/{id}/catalog/upload   — CSV upload
GET  /api/merchants/{id}/passport         — products + validation issues + status
POST /api/merchants/{id}/passport/activate
DELETE /api/merchants/{id}/catalog/{product_id}
"""
import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.merchants import get_current_merchant
from app.audit.logger import write_audit_event
from app.db.session import get_db
from app.engine.validation import validate_catalog
from app.models import MerchantModel, MerchantRulesModel, ProductModel
from app.schemas import (
    MerchantRules, PassportResponse, Product, ProductCreate, ProductUpdate, ValidationIssue
)

router = APIRouter()

# Columns that map directly to ProductModel fields; used for CSV parsing
_CSV_FIELD_MAP = {
    "id": "id",
    "name": "name",
    "category": "category",
    "price": "price",
    "cost": "cost",
    "stock": "stock",
    "description": "description",
    "image_url": "image_url",
    "status": "status",
    # list fields handled separately
}


def _rules_schema(rules_model: MerchantRulesModel | None) -> MerchantRules | None:
    if not rules_model:
        return None
    return MerchantRules.model_validate(rules_model)


def _get_merchant_or_403(merchant_id: str, current: MerchantModel) -> None:
    if current.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")


# ---------------------------------------------------------------------------
# Manual add / update
# ---------------------------------------------------------------------------

@router.post(
    "/merchants/{merchant_id}/catalog",
    response_model=Product,
    status_code=201,
    tags=["catalog"],
)
def add_product(
    merchant_id: str,
    body: ProductCreate,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    _get_merchant_or_403(merchant_id, current)

    product_id = body.id or f"prod_{uuid.uuid4().hex[:8]}"

    # Conflict check
    if db.get(ProductModel, product_id):
        raise HTTPException(status_code=409, detail=f"Product id '{product_id}' already exists")

    product = ProductModel(
        id=product_id,
        merchant_id=merchant_id,
        name=body.name,
        category=body.category,
        tags=body.tags,
        price=body.price,
        cost=body.cost,
        stock=body.stock,
        complement_categories=body.complement_categories,
        description=body.description,
        image_url=body.image_url,
        status=body.status,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put(
    "/merchants/{merchant_id}/catalog/{product_id}",
    response_model=Product,
    tags=["catalog"],
)
def update_product(
    merchant_id: str,
    product_id: str,
    body: ProductUpdate,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    _get_merchant_or_403(merchant_id, current)
    product = db.get(ProductModel, product_id)
    if not product or product.merchant_id != merchant_id:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product


@router.delete(
    "/merchants/{merchant_id}/catalog/{product_id}",
    status_code=204,
    tags=["catalog"],
)
def delete_product(
    merchant_id: str,
    product_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    _get_merchant_or_403(merchant_id, current)
    product = db.get(ProductModel, product_id)
    if not product or product.merchant_id != merchant_id:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()


# ---------------------------------------------------------------------------
# CSV upload
# ---------------------------------------------------------------------------

@router.post(
    "/merchants/{merchant_id}/catalog/upload",
    response_model=list[Product],
    tags=["catalog"],
)
def upload_catalog_csv(
    merchant_id: str,
    file: UploadFile = File(...),
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Upload a CSV with product data. Required columns: name, category, price, cost, stock.
    Optional: id, tags (semicolon-separated), complement_categories (semicolon-separated),
              description, image_url, status.
    Existing products (matched by id) are updated; new ones are inserted.
    """
    _get_merchant_or_403(merchant_id, current)

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    # Normalise headers: lowercase + strip
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Empty or unreadable CSV")

    created: list[ProductModel] = []
    for row in reader:
        row = {k.lower().strip(): v.strip() for k, v in row.items()}

        name = row.get("name", "")
        category = row.get("category", "")
        try:
            price = float(row.get("price", 0))
            cost = float(row.get("cost", 0))
            stock = int(float(row.get("stock", 0)))
        except ValueError:
            continue  # skip malformed numeric rows

        product_id = row.get("id") or f"prod_{uuid.uuid4().hex[:8]}"
        tags = [t.strip() for t in row.get("tags", "").split(";") if t.strip()]
        complement_categories = [
            c.strip() for c in row.get("complement_categories", "").split(";") if c.strip()
        ]
        status_val = row.get("status", "active")
        if status_val not in ("active", "inactive"):
            status_val = "active"

        existing = db.get(ProductModel, product_id)
        if existing and existing.merchant_id == merchant_id:
            existing.name = name or existing.name
            existing.category = category or existing.category
            existing.price = price if price else existing.price
            existing.cost = cost if cost else existing.cost
            existing.stock = stock
            existing.tags = tags or existing.tags
            existing.complement_categories = complement_categories or existing.complement_categories
            existing.description = row.get("description", existing.description)
            existing.image_url = row.get("image_url") or existing.image_url
            existing.status = status_val
            created.append(existing)
        else:
            product = ProductModel(
                id=product_id,
                merchant_id=merchant_id,
                name=name,
                category=category,
                tags=tags,
                price=price,
                cost=cost,
                stock=stock,
                complement_categories=complement_categories,
                description=row.get("description", ""),
                image_url=row.get("image_url") or None,
                status=status_val,
            )
            db.add(product)
            created.append(product)

    db.commit()
    for p in created:
        db.refresh(p)
    return created


# ---------------------------------------------------------------------------
# Passport — view + activate
# ---------------------------------------------------------------------------

@router.get(
    "/merchants/{merchant_id}/passport",
    response_model=PassportResponse,
    tags=["passport"],
)
def get_passport(
    merchant_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    _get_merchant_or_403(merchant_id, current)
    merchant = db.get(MerchantModel, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    rules = _rules_schema(merchant.rules)
    issues, can_activate = validate_catalog(merchant.products, rules)

    return PassportResponse(
        merchant_id=merchant_id,
        passport_status=merchant.passport_status,
        products=[Product.model_validate(p) for p in merchant.products],
        validation_issues=issues,
        can_activate=can_activate,
    )


@router.post(
    "/merchants/{merchant_id}/passport/activate",
    response_model=PassportResponse,
    tags=["passport"],
)
def activate_passport(
    merchant_id: str,
    current: MerchantModel = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """
    Runs validation. Sets passport_status = 'active' only if no error-severity issues.
    Writes a passport_activated audit event on success.
    """
    _get_merchant_or_403(merchant_id, current)
    merchant = db.get(MerchantModel, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    rules = _rules_schema(merchant.rules)
    issues, can_activate = validate_catalog(merchant.products, rules)

    if not can_activate:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Passport cannot be activated: error-severity validation issues exist",
                "issues": [i.model_dump() for i in issues if i.severity == "error"],
            },
        )

    merchant.passport_status = "active"
    db.commit()
    db.refresh(merchant)

    # Write audit event — first entry in the log
    write_audit_event(
        db,
        merchant_id=merchant_id,
        stage="passport_activated",
        actor="merchant",
        payload={"product_count": len(merchant.products)},
        result={"status": "active", "warnings": [i.model_dump() for i in issues if i.severity == "warning"]},
    )

    return PassportResponse(
        merchant_id=merchant_id,
        passport_status="active",
        products=[Product.model_validate(p) for p in merchant.products],
        validation_issues=issues,
        can_activate=True,
    )
