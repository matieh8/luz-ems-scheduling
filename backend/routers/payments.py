from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.scheduling import get_settings
from backend.tz import to_local, to_utc_naive, utcnow

router = APIRouter(prefix="/api/payments", tags=["Payments"])
METHODS = ("cash", "card", "transfer", "online", "other")


@router.get("/{payment_id}/invoice")
def invoice(payment_id: int, db: Session = Depends(get_db)):
    """Everything needed to print an invoice / receipt for one payment."""
    p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
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
        lines = [{"description": p.notes or "Payment", "amount": round(float(p.amount), 2)}]
    paid_local = to_local(p.paid_at, s.timezone)
    return {
        "number": f"INV-{paid_local:%Y}-{p.id:05d}", "date": paid_local.strftime("%d %b %Y"),
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
    if not db.query(models.Client).filter(models.Client.id == body.client_id).first():
        raise HTTPException(status_code=400, detail="Client not found")
    if body.appointment_id and not db.query(models.Appointment).filter(models.Appointment.id == body.appointment_id).first():
        raise HTTPException(status_code=400, detail="Appointment not found")
    p = models.Payment(client_id=body.client_id, appointment_id=body.appointment_id,
                       subscription_id=body.subscription_id, amount=body.amount, method=body.method,
                       paid_at=to_utc_naive(body.paid_at) if body.paid_at else utcnow(), notes=body.notes)
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
    if data.get("paid_at"):
        data["paid_at"] = to_utc_naive(data["paid_at"])
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{payment_id}")
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    db.delete(p)
    db.commit()
    return {"detail": "Payment deleted"}
