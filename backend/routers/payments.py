from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.tz import to_utc_naive, utcnow

router = APIRouter(prefix="/api/payments", tags=["Payments"])
METHODS = ("cash", "card", "transfer", "online", "other")


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
