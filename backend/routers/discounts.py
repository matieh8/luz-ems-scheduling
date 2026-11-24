"""Discount codes for package sales and renewals."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.tz import to_utc_naive, utcnow

router = APIRouter(prefix="/api/discounts", tags=["Discounts"])


def _norm(code: str) -> str:
    return (code or "").strip().upper()


def evaluate(db: Session, code: str, base_price: float):
    """Return (discount_code_row, discount_amount) or raise ValueError with a reason the owner can read."""
    row = db.query(models.DiscountCode).filter(models.DiscountCode.code == _norm(code)).first()
    now = utcnow()
    if not row:
        raise ValueError("No such code")
    if not row.active:
        raise ValueError("This code is switched off")
    if row.valid_from and now < row.valid_from:
        raise ValueError("This code is not valid yet")
    if row.valid_until and now > row.valid_until:
        raise ValueError("This code has expired")
    if row.max_uses is not None and row.used_count >= row.max_uses:
        raise ValueError("This code has been used up")
    off = base_price * row.value / 100 if row.kind == "percent" else row.value
    return row, round(min(max(off, 0), base_price), 2)


def apply(db: Session, code: Optional[str], base_price: float):
    """For a sale: (final_price, code, discount) and count the use. Raises HTTP 400 for a bad code."""
    if not code or not code.strip():
        return base_price, None, None
    try:
        row, off = evaluate(db, code, base_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Discount code: {e}")
    row.used_count += 1
    return round(base_price - off, 2), row.code, off


def _clean_dates(data: dict) -> dict:
    for k in ("valid_from", "valid_until"):
        if data.get(k) is not None:
            data[k] = to_utc_naive(data[k])
    return data


@router.get("/", response_model=List[schemas.DiscountResponse])
def list_discounts(db: Session = Depends(get_db)):
    return db.query(models.DiscountCode).order_by(models.DiscountCode.created_at.desc(), models.DiscountCode.id.desc()).all()


@router.get("/check")
def check(code: str, plan_id: Optional[int] = None, price: Optional[float] = None, db: Session = Depends(get_db)):
    base = price
    if base is None and plan_id:
        plan = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.id == plan_id).first()
        base = plan.price if plan else None
    if base is None:
        raise HTTPException(status_code=422, detail="Give a plan or a price")
    try:
        row, off = evaluate(db, code, float(base))
    except ValueError as e:
        return {"valid": False, "reason": str(e)}
    label = f"{row.value:g}% off" if row.kind == "percent" else f"{row.value:g} off"
    return {"valid": True, "code": row.code, "label": label, "discount": off, "final_price": round(float(base) - off, 2)}


@router.post("/", response_model=schemas.DiscountResponse)
def create_discount(body: schemas.DiscountCreate, db: Session = Depends(get_db)):
    if body.kind == "percent" and body.value > 100:
        raise HTTPException(status_code=422, detail="A percentage can't be more than 100")
    code = _norm(body.code)
    if db.query(models.DiscountCode).filter(models.DiscountCode.code == code).first():
        raise HTTPException(status_code=409, detail="That code already exists")
    row = models.DiscountCode(**_clean_dates({**body.model_dump(), "code": code}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{discount_id}", response_model=schemas.DiscountResponse)
def update_discount(discount_id: int, body: schemas.DiscountUpdate, db: Session = Depends(get_db)):
    row = db.query(models.DiscountCode).filter(models.DiscountCode.id == discount_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Code not found")
    data = _clean_dates(body.model_dump(exclude_unset=True))
    kind, value = data.get("kind", row.kind), data.get("value", row.value)
    if kind == "percent" and value > 100:
        raise HTTPException(status_code=422, detail="A percentage can't be more than 100")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{discount_id}")
def delete_discount(discount_id: int, db: Session = Depends(get_db)):
    row = db.query(models.DiscountCode).filter(models.DiscountCode.id == discount_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Code not found")
    db.delete(row)
    db.commit()
    return {"detail": "deleted"}
