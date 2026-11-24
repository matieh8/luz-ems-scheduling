from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.tz import to_utc_naive, utcnow

router = APIRouter(prefix="/api/clients", tags=["Clients"])


def retention(completed_times, no_shows: int, has_future: bool, now) -> dict:
    """How regularly a client comes, and how likely they are to stop.

    Compares the days since the last session with the client's own usual gap between sessions:
    regular (on rhythm or already booked), slipping (1.5x their gap), at_risk (2.5x), lapsed (4x, or 60+ days).
    """
    times = sorted(completed_times)
    attendance = round(len(times) / (len(times) + no_shows) * 100, 1) if (times or no_shows) else None
    if not times:
        return {"risk": "regular" if has_future else "new", "attendance_rate": attendance, "avg_gap_days": None, "days_since_last": None}
    since = (now - times[-1]).days
    recent = times[-11:]
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(recent, recent[1:])]
    avg_gap = round(sum(gaps) / len(gaps), 1) if gaps else None
    if has_future:
        risk = "regular"
    elif avg_gap is None:
        risk = "new" if since <= 21 else "slipping" if since <= 45 else "lapsed"
    else:
        ratio = since / max(avg_gap, 3)
        risk = "regular" if ratio <= 1.5 else "slipping" if ratio <= 2.5 else "at_risk" if ratio <= 4 else "lapsed"
        if since > 60:
            risk = "lapsed"
    return {"risk": risk, "attendance_rate": attendance, "avg_gap_days": avg_gap, "days_since_last": since}


def summarize(c: models.Client) -> dict:
    now = utcnow()
    appts = c.appointments
    completed = [a for a in appts if a.status == "completed"]
    future = [a for a in appts if a.status in ("scheduled", "confirmed") and a.start_time >= now]
    no_shows = len([a for a in appts if a.status == "no_show"])
    outstanding = sum(a.balance_due for a in completed)
    remaining = sum(s.sessions_remaining for s in c.subscriptions if s.status == "active")
    data = schemas.ClientResponse.model_validate(c).model_dump()
    data.update(
        total_appointments=len(appts),
        completed_appointments=len(completed),
        no_shows=no_shows,
        total_spent=float(sum(p.amount for p in c.payments)),
        outstanding=float(outstanding),
        sessions_remaining=int(remaining),
        last_visit=max((a.start_time for a in completed), default=None),
        next_visit=min((a.start_time for a in future), default=None),
        **retention([a.start_time for a in completed if a.start_time <= now], no_shows, bool(future), now),
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
        "measurements": [schemas.MeasurementResponse.model_validate(m)
                         for m in sorted(client.measurements, key=lambda m: m.measured_at, reverse=True)],
        "notes": [schemas.ClientNoteResponse.model_validate(n)
                  for n in sorted(client.client_notes, key=lambda n: n.created_at, reverse=True)],
    }


def _client_or_404(db: Session, client_id: int) -> models.Client:
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/{client_id}/measurements", response_model=List[schemas.MeasurementResponse])
def list_measurements(client_id: int, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    return (db.query(models.BodyMeasurement).filter(models.BodyMeasurement.client_id == client_id)
            .order_by(models.BodyMeasurement.measured_at.desc()).all())


@router.post("/{client_id}/measurements", response_model=schemas.MeasurementResponse)
def add_measurement(client_id: int, body: schemas.MeasurementCreate, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    data = body.model_dump()
    values = [v for k, v in data.items() if k not in ("measured_at", "notes")]
    if all(v is None for v in values):
        raise HTTPException(status_code=422, detail="Enter at least one measurement")
    m = models.BodyMeasurement(client_id=client_id, **{k: v for k, v in data.items() if k != "measured_at"},
                               measured_at=to_utc_naive(body.measured_at) if body.measured_at else utcnow())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/measurements/{measurement_id}")
def delete_measurement(measurement_id: int, db: Session = Depends(get_db)):
    m = db.query(models.BodyMeasurement).filter(models.BodyMeasurement.id == measurement_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Measurement not found")
    db.delete(m)
    db.commit()
    return {"detail": "deleted"}


@router.get("/{client_id}/notes", response_model=List[schemas.ClientNoteResponse])
def list_notes(client_id: int, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    return (db.query(models.ClientNote).filter(models.ClientNote.client_id == client_id)
            .order_by(models.ClientNote.created_at.desc()).all())


@router.post("/{client_id}/notes", response_model=schemas.ClientNoteResponse)
def add_note(client_id: int, body: schemas.ClientNoteCreate, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    n = models.ClientNote(client_id=client_id, kind=body.kind, text=body.text.strip(), author=body.author)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    n = db.query(models.ClientNote).filter(models.ClientNote.id == note_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    db.delete(n)
    db.commit()
    return {"detail": "deleted"}


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
