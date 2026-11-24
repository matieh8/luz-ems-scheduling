"""Gift cards: a package bought for someone else, redeemed later as a normal package."""
import secrets
from datetime import timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.tz import utcnow

router = APIRouter(prefix="/api/gift-cards", tags=["Gift cards"])
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid misreading


def _new_code(db: Session) -> str:
    while True:
        part = lambda: "".join(secrets.choice(ALPHABET) for _ in range(4))
        code = f"GIFT-{part()}-{part()}"
        if not db.query(models.GiftCard).filter(models.GiftCard.code == code).first():
            return code


def _out(g: models.GiftCard) -> dict:
    data = schemas.GiftCardResponse.model_validate(g).model_dump()
    data.update(plan_name=g.plan.name if g.plan else None, purchaser_name=g.purchaser.name if g.purchaser else None)
    return data


def _find_or_create_client(db: Session, name: str, phone: str, source: str) -> models.Client:
    if phone:
        c = db.query(models.Client).filter(models.Client.phone == phone.strip()).first()
        if c:
            return c
    c = models.Client(name=name.strip(), phone=(phone or "").strip() or "-", source=source)
    db.add(c)
    db.flush()
    return c


def _get(db: Session, gift_id: int) -> models.GiftCard:
    g = db.query(models.GiftCard).filter(models.GiftCard.id == gift_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return g


@router.get("/", response_model=List[schemas.GiftCardResponse])
def list_gift_cards(db: Session = Depends(get_db)):
    return [_out(g) for g in db.query(models.GiftCard).order_by(models.GiftCard.created_at.desc(), models.GiftCard.id.desc()).all()]


@router.get("/lookup", response_model=schemas.GiftCardResponse)
def lookup(code: str, db: Session = Depends(get_db)):
    g = db.query(models.GiftCard).filter(models.GiftCard.code == code.strip().upper()).first()
    if not g:
        raise HTTPException(status_code=404, detail="No gift card with that code")
    return _out(g)


@router.post("/", response_model=schemas.GiftCardResponse)
def sell(body: schemas.GiftCardCreate, db: Session = Depends(get_db)):
    plan = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.id == body.plan_id).first()
    if not plan:
        raise HTTPException(status_code=400, detail="Plan not found")
    if body.purchaser_client_id:
        buyer = db.query(models.Client).filter(models.Client.id == body.purchaser_client_id).first()
        if not buyer:
            raise HTTPException(status_code=400, detail="Buyer not found")
    elif body.purchaser_name and body.purchaser_name.strip():
        buyer = _find_or_create_client(db, body.purchaser_name, body.purchaser_phone, "gift buyer")
    else:
        raise HTTPException(status_code=422, detail="Choose the buyer or enter their name")
    now = utcnow()
    price = body.price_paid if body.price_paid is not None else plan.price
    g = models.GiftCard(code=_new_code(db), plan_id=plan.id, price_paid=price, purchaser_client_id=buyer.id,
                        recipient_name=body.recipient_name.strip(), recipient_phone=(body.recipient_phone or "").strip() or None,
                        message=(body.message or "").strip() or None, valid_until=now + timedelta(days=body.valid_days))
    db.add(g)
    db.flush()
    if body.payment_method and price > 0:
        p = models.Payment(client_id=buyer.id, amount=price, method=body.payment_method, paid_at=now,
                           notes=f"Gift card {g.code}: {plan.name} for {g.recipient_name}")
        db.add(p)
        db.flush()
        g.payment_id = p.id
    db.commit()
    db.refresh(g)
    return _out(g)


@router.post("/{gift_id}/redeem", response_model=schemas.SubscriptionResponse)
def redeem(gift_id: int, body: schemas.GiftCardRedeem, db: Session = Depends(get_db)):
    g = _get(db, gift_id)
    now = utcnow()
    if g.status != "active":
        raise HTTPException(status_code=409, detail=f"This gift card is {g.status}")
    if g.valid_until and now > g.valid_until:
        raise HTTPException(status_code=409, detail="This gift card has expired")
    if body.client_id:
        client = db.query(models.Client).filter(models.Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=400, detail="Client not found")
    else:
        client = _find_or_create_client(db, g.recipient_name, g.recipient_phone, "gift card")
    plan = g.plan
    sub = models.Subscription(client_id=client.id, plan_id=plan.id, start_date=now,
                              end_date=now + timedelta(days=plan.duration_days) if plan.duration_days else None,
                              sessions_total=plan.sessions_included, sessions_used=0, price_paid=g.price_paid,
                              status="active", notes=f"Gift card {g.code}" + (f" from {g.purchaser.name}" if g.purchaser else ""))
    db.add(sub)
    db.flush()
    if g.payment_id:  # the buyer's payment now covers this package, so it shows as paid
        p = db.query(models.Payment).filter(models.Payment.id == g.payment_id).first()
        if p:
            p.subscription_id = sub.id
    g.status, g.redeemed_at, g.redeemed_client_id, g.redeemed_subscription_id = "redeemed", now, client.id, sub.id
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{gift_id}/cancel", response_model=schemas.GiftCardResponse)
def cancel(gift_id: int, db: Session = Depends(get_db)):
    g = _get(db, gift_id)
    if g.status != "active":
        raise HTTPException(status_code=409, detail=f"This gift card is {g.status}")
    g.status = "cancelled"
    db.commit()
    db.refresh(g)
    return _out(g)
