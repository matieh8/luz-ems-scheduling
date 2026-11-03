from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.tz import utcnow

router = APIRouter(prefix="/api/clients", tags=["Clients"])


def summarize(c: models.Client) -> dict:
    now = utcnow()
    appts = c.appointments
    completed = [a for a in appts if a.status == "completed"]
    past = [a for a in appts if a.status == "completed"]
    future = [a for a in appts if a.status in ("scheduled", "confirmed") and a.start_time >= now]
    outstanding = sum(a.balance_due for a in completed)
    remaining = sum(s.sessions_remaining for s in c.subscriptions if s.status == "active")
    data = schemas.ClientResponse.model_validate(c).model_dump()
    data.update(
        total_appointments=len(appts),
        completed_appointments=len(completed),
        no_shows=len([a for a in appts if a.status == "no_show"]),
        total_spent=float(sum(p.amount for p in c.payments)),
        outstanding=float(outstanding),
        sessions_remaining=int(remaining),
        last_visit=max((a.start_time for a in past), default=None),
        next_visit=min((a.start_time for a in future), default=None),
    )
    return data


@router.get("/", response_model=List[schemas.ClientSummary])
def list_clients(q: str = "", include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.Client)
    if q:
        query = query.filter(
            (models.Client.name.ilike(f"%{q}%")) |
            (models.Client.phone.ilike(f"%{q}%")) |
            (models.Client.email.ilike(f"%{q}%"))
        )
    if not include_inactive:
        query = query.filter(models.Client.active == True)
    return [summarize(c) for c in query.order_by(models.Client.name).all()]


@router.post("/", response_model=schemas.ClientResponse)
def create_client(client: schemas.ClientCreate, db: Session = Depends(get_db)):
    db_client = models.Client(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.get("/{client_id}", response_model=schemas.ClientSummary)
def get_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return summarize(client)


@router.get("/{client_id}/history")
def client_history(client_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    appointments = sorted(client.appointments, key=lambda a: a.start_time, reverse=True)
    subs = sorted(client.subscriptions, key=lambda s: s.created_at, reverse=True)
    payments = sorted(client.payments, key=lambda p: p.paid_at, reverse=True)
    messages = (
        db.query(models.NotificationLog)
        .filter(models.NotificationLog.client_id == client_id)
        .order_by(models.NotificationLog.created_at.desc()).limit(50).all()
    )
    return {
        "client": summarize(client),
        "appointments": [schemas.AppointmentResponse.model_validate(a) for a in appointments],
        "subscriptions": [schemas.SubscriptionResponse.model_validate(s) for s in subs],
        "payments": [schemas.PaymentResponse.model_validate(p) for p in payments],
        "messages": [schemas.NotificationLogResponse.model_validate(m) for m in messages],
    }


@router.put("/{client_id}", response_model=schemas.ClientResponse)
def update_client(client_id: int, client: schemas.ClientUpdate, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    for key, value in client.model_dump(exclude_unset=True).items():
        setattr(db_client, key, value)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    db.query(models.NotificationLog).filter(models.NotificationLog.client_id == client_id).delete()
    db.delete(db_client)
    db.commit()
    return {"detail": "Client deleted"}
