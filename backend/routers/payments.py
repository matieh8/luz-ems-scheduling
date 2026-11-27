from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.scheduling import get_settings
from backend.tz import to_local, to_utc_naive, utcnow

router = APIRouter(prefix="/api/payments", tags=["Payments"])
METHODS = ("cash", "card", "transfer", "online", "other")
SOURCES = {"social_media": "Social media", "ads": "Advertising / sponsorship", "other": "Other income"}


@router.get("/{payment_id}/invoice")
def invoice(payment_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return invoice_data(db, p)


def invoice_data(db: Session, p: models.Payment) -> dict:
    """Everything needed to print an invoice / receipt for one payment (admin and the client's own page)."""
    s = get_settings(db)
    lines = []
    sub, appt = p.subscription, p.appointment
    if sub and sub.plan:
        desc = f"{sub.plan.name} ({sub.sessions_total} sessions" + (f", valid until {to_local(sub.end_date, s.timezone):%d %b %Y}" if sub.end_date else "") + ")"
        full = float(sub.price_paid or 0) + float(sub.discount_amount or 0)
        # Show the list price and discount only when this payment settles the whole package
        if sub.discount_amount and abs(float(p.amount) - float(sub.price_paid or 0)) < 0.01:
            lines = [{"description": desc, "amount": round(full, 2)},
                     {"description": f"Discount ({sub.discount_code})", "amount": -round(float(sub.discount_amount), 2)}]
        else:
            lines = [{"description": desc, "amount": round(float(p.amount), 2)}]
    elif appt and appt.service:
        when = to_local(appt.start_time, s.timezone)
        lines = [{"description": f"{appt.service.name} session, {when:%d %b %Y %H:%M}", "amount": round(float(p.amount), 2)}]
    else:
        lines = [{"description": p.notes or SOURCES.get(p.source) or "Payment", "amount": round(float(p.amount), 2)}]
    paid_local = to_local(p.paid_at, s.timezone)
    return {
        # a refund prints as a credit note
        "number": f"{'CN' if p.amount < 0 else 'INV'}-{paid_local:%Y}-{p.id:05d}", "date": paid_local.strftime("%d %b %Y"),
        "credit_note": p.amount < 0,
        "business": {"name": s.business_name, "phone": s.business_phone, "email": s.business_email,
                     "address": s.business_address, "trn": s.tax_registration_number},
        "client": {"name": p.client.name if p.client else "", "phone": p.client.phone if p.client else "",
                   "email": p.client.email if p.client else None},
        "lines": lines, "total": round(float(p.amount), 2), "method": p.method, "currency": s.currency,
        "notes": p.notes if (sub or appt) else None,
    }


@router.get("/", response_model=List[schemas.PaymentResponse])
def list_payments(client_id: Optional[int] = None, from_date: Optional[datetime] = None,
                  to_date: Optional[datetime] = None, method: Optional[str] = None, limit: int = 200,
                  db: Session = Depends(get_db)):
    q = db.query(models.Payment)
    if client_id:
        q = q.filter(models.Payment.client_id == client_id)
    if from_date:
        q = q.filter(models.Payment.paid_at >= to_utc_naive(from_date))
    if to_date:
        q = q.filter(models.Payment.paid_at < to_utc_naive(to_date))
    if method:
        q = q.filter(models.Payment.method == method)
    return q.order_by(models.Payment.paid_at.desc()).limit(limit).all()


@router.post("/", response_model=schemas.PaymentResponse)
def create_payment(body: schemas.PaymentCreate, db: Session = Depends(get_db)):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if body.method not in METHODS:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    if body.client_id is None:
        if body.source not in SOURCES or body.appointment_id or body.subscription_id:
            raise HTTPException(status_code=400, detail="Choose a client, or where the income came from")
    elif not db.query(models.Client).filter(models.Client.id == body.client_id).first():
        raise HTTPException(status_code=400, detail="Client not found")
    appt = db.query(models.Appointment).filter(models.Appointment.id == body.appointment_id).first() if body.appointment_id else None
    if body.appointment_id and (not appt or appt.client_id != body.client_id):
        raise HTTPException(status_code=400, detail="That session doesn't belong to this client")
    sub = db.query(models.Subscription).filter(models.Subscription.id == body.subscription_id).first() if body.subscription_id else None
    if body.subscription_id and (not sub or sub.client_id != body.client_id):
        raise HTTPException(status_code=400, detail="That package doesn't belong to this client")
    if not body.confirm:
        # The same payment twice within a few minutes is almost always a double click or a second device
        same = db.query(models.Payment).filter(
            models.Payment.amount == body.amount, models.Payment.method == body.method,
            models.Payment.created_at >= utcnow() - timedelta(minutes=10),
            models.Payment.client_id == body.client_id if body.client_id else models.Payment.client_id.is_(None),
            models.Payment.appointment_id == body.appointment_id if body.appointment_id else models.Payment.appointment_id.is_(None),
            models.Payment.subscription_id == body.subscription_id if body.subscription_id else models.Payment.subscription_id.is_(None)).first()
        if same:
            raise HTTPException(status_code=409, detail="This looks like a duplicate: the same payment was recorded a few minutes ago. "
                                                        "Record it again only if the client really paid twice.")
        owed = (max(float(appt.price or 0) - appt.paid_amount, 0.0) if appt and not appt.subscription_id else None) if appt \
            else (max(float(sub.price_paid or 0) - sub.paid_amount, 0.0) if sub else None)
        if owed is not None and body.amount > owed + 0.005:
            raise HTTPException(status_code=409, detail=f"Only {owed:.2f} is still owed for this. Record more only if the client really overpaid.")
    p = models.Payment(client_id=body.client_id, appointment_id=body.appointment_id,
                       subscription_id=body.subscription_id, amount=body.amount, method=body.method,
                       paid_at=to_utc_naive(body.paid_at) if body.paid_at else utcnow(), notes=body.notes,
                       source=None if body.client_id else body.source)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{payment_id}", response_model=schemas.PaymentResponse)
def update_payment(payment_id: int, body: schemas.PaymentUpdate, db: Session = Depends(get_db)):
    p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    data = body.model_dump(exclude_unset=True)
    if "method" in data and data["method"] not in METHODS:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    if data.get("paid_at"):
        data["paid_at"] = to_utc_naive(data["paid_at"])
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.post("/{payment_id}/refund", response_model=schemas.PaymentResponse)
def refund_payment(payment_id: int, body: schemas.PaymentRefund, db: Session = Depends(get_db)):
    """Give money back. Recorded as its own negative payment linked to the original, so the original stays untouched
    and every report shows the refund in the month it happened."""
    p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.amount <= 0 or p.refund_of_id:
        raise HTTPException(status_code=400, detail="A refund can't be refunded")
    left = round(float(p.amount) - p.refunded_amount, 2)
    if body.amount > left + 0.005:
        raise HTTPException(status_code=400, detail=f"Only {left:.2f} of this payment can still be refunded")
    method = body.method or p.method
    if method not in METHODS:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    r = models.Payment(client_id=p.client_id, appointment_id=p.appointment_id, subscription_id=p.subscription_id, source=p.source,
                       amount=-round(body.amount, 2), method=method, paid_at=utcnow(), refund_of_id=p.id,
                       notes=f"Refund{': ' + body.reason.strip() if (body.reason or '').strip() else ''}")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{payment_id}")
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.refunds:
        raise HTTPException(status_code=409, detail="This payment has a refund. Delete the refund first.")
    db.delete(p)
    db.commit()
    return {"detail": "Payment deleted"}
