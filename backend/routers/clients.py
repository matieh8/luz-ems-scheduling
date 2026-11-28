import os
import secrets
from collections import Counter
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.database import DATA_DIR, get_db
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
    future = [a for a in appts if a.status in models.ACTIVE_STATUSES and a.start_time >= now]
    no_shows = len([a for a in appts if a.status == "no_show"])
    outstanding = sum(a.balance_due for a in completed)
    live = sorted([s for s in c.subscriptions if s.status == "active" and s.sessions_remaining > 0 and (s.end_date is None or s.end_date >= now)],
                  key=lambda s: s.end_date or datetime.max)  # same order the booking uses them
    remaining = sum(s.sessions_remaining for s in live)  # expired packages can't be booked, so they don't count
    trainers = Counter(a.staff.name for a in appts if a.staff and a.status != "cancelled")
    data = schemas.ClientResponse.model_validate(c).model_dump()
    data.update(
        total_appointments=len(appts),
        completed_appointments=len(completed),
        no_shows=no_shows,
        late_count=len([a for a in completed if (a.late_minutes or 0) > 0]),
        total_spent=float(sum(p.amount for p in c.payments)),
        outstanding=float(outstanding),
        sessions_remaining=int(remaining),
        last_visit=max((a.start_time for a in completed), default=None),
        # same rule as the dashboard's "active clients": a session that isn't cancelled or a no-show, up to now
        last_session=max((a.start_time for a in appts if a.status in (*models.ACTIVE_STATUSES, "completed") and a.start_time <= now), default=None),
        next_visit=min((a.start_time for a in future), default=None),
        package_name=live[0].plan.name if live and live[0].plan else None,
        package_end=live[0].end_date if live else None,
        main_trainer=trainers.most_common(1)[0][0] if trainers else None,
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
    if db_client.photo_consent:
        db_client.photo_consent_at = utcnow()
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
    payments = sorted(client.payments, key=lambda p: (p.paid_at, p.id), reverse=True)
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
                  for n in sorted(client.client_notes, key=lambda n: (n.created_at, n.id), reverse=True)],
        "photos": [schemas.PhotoResponse.model_validate(p)
                   for p in sorted(client.photos, key=lambda p: (p.taken_at, p.id), reverse=True)],
    }


def _client_or_404(db: Session, client_id: int) -> models.Client:
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("/{client_id}/portal-link")
def portal_link(client_id: int, new: bool = False, db: Session = Depends(get_db)):
    """The client's private link to their own page. new=true replaces it, so an old forwarded link stops working."""
    c = _client_or_404(db, client_id)
    if new or not c.portal_token:
        c.portal_token = secrets.token_urlsafe(24)
        db.commit()
    from backend.notifications import normalize_phone
    return {"path": f"/c/{c.portal_token}", "phone": normalize_phone(c.phone)}


@router.delete("/{client_id}/portal-link")
def remove_portal_link(client_id: int, db: Session = Depends(get_db)):
    c = _client_or_404(db, client_id)
    c.portal_token = None
    db.commit()
    return {"detail": "The client's link is switched off"}


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


PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic", "image/heif": ".heif"}
PHOTO_POSES = ("front", "side", "back", "other")
PHOTO_MAX_BYTES = 12 * 1024 * 1024


def _photo_dir(client_id: int) -> str:
    return os.path.join(DATA_DIR, "photos", str(int(client_id)))


def _photo_path(p: models.ProgressPhoto) -> str:
    return os.path.join(_photo_dir(p.client_id), os.path.basename(p.filename))


def _remove_photo_file(p: models.ProgressPhoto):
    try:
        os.remove(_photo_path(p))
    except FileNotFoundError:
        pass


@router.get("/{client_id}/photos", response_model=List[schemas.PhotoResponse])
def list_photos(client_id: int, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    return (db.query(models.ProgressPhoto).filter(models.ProgressPhoto.client_id == client_id)
            .order_by(models.ProgressPhoto.taken_at.desc(), models.ProgressPhoto.id.desc()).all())


@router.post("/{client_id}/photos", response_model=schemas.PhotoResponse)
async def upload_photo(client_id: int, file: UploadFile = File(...), pose: str = Form("front"),
                       taken_at: Optional[datetime] = Form(None), notes: Optional[str] = Form(None),
                       db: Session = Depends(get_db)):
    client = _client_or_404(db, client_id)
    if not client.photo_consent:
        raise HTTPException(status_code=409, detail="Record the client's consent to progress photos first")
    if pose not in PHOTO_POSES:
        raise HTTPException(status_code=422, detail="Pose must be front, side, back or other")
    ext = PHOTO_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status_code=422, detail="Upload a JPG, PNG, WEBP or HEIC photo")
    data = await file.read(PHOTO_MAX_BYTES + 1)
    if len(data) > PHOTO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Photo is larger than 12 MB")
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty")
    os.makedirs(_photo_dir(client_id), exist_ok=True)
    name = f"{secrets.token_hex(12)}{ext}"
    with open(os.path.join(_photo_dir(client_id), name), "wb") as fh:
        fh.write(data)
    p = models.ProgressPhoto(client_id=client_id, pose=pose, filename=name, content_type=file.content_type.lower(),
                             notes=(notes or "").strip() or None,
                             taken_at=to_utc_naive(taken_at) if taken_at else utcnow())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ---- profile photo: a small head shot to recognise the client (resized in the browser before upload) ----
AVATAR_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
AVATAR_MAX_BYTES = 3 * 1024 * 1024


def _remove_avatar(c: models.Client):
    if c.avatar:
        try:
            os.remove(os.path.join(_photo_dir(c.id), os.path.basename(c.avatar)))
        except FileNotFoundError:
            pass
        c.avatar = None


@router.post("/{client_id}/avatar", response_model=schemas.ClientResponse)
async def upload_avatar(client_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    client = _client_or_404(db, client_id)
    ext = AVATAR_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status_code=422, detail="Upload a JPG, PNG or WEBP photo")
    data = await file.read(AVATAR_MAX_BYTES + 1)
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Photo is larger than 3 MB")
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty")
    os.makedirs(_photo_dir(client_id), exist_ok=True)
    name = f"avatar-{secrets.token_hex(8)}{ext}"
    with open(os.path.join(_photo_dir(client_id), name), "wb") as fh:
        fh.write(data)
    _remove_avatar(client)  # the old one
    client.avatar = name
    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}/avatar")
def avatar_file(client_id: int, db: Session = Depends(get_db)):
    c = _client_or_404(db, client_id)
    path = os.path.join(_photo_dir(c.id), os.path.basename(c.avatar or ""))
    if not c.avatar or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No profile photo")
    ext = os.path.splitext(path)[1]
    media = next((k for k, v in AVATAR_TYPES.items() if v == ext), "image/jpeg")
    return FileResponse(path, media_type=media, headers={"Cache-Control": "private, max-age=86400"})  # name changes on every upload


@router.delete("/{client_id}/avatar")
def delete_avatar(client_id: int, db: Session = Depends(get_db)):
    c = _client_or_404(db, client_id)
    _remove_avatar(c)
    db.commit()
    return {"detail": "deleted"}


@router.get("/photos/{photo_id}/file")
def photo_file(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(models.ProgressPhoto).filter(models.ProgressPhoto.id == photo_id).first()
    if not p or not os.path.exists(_photo_path(p)):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(_photo_path(p), media_type=p.content_type, headers={"Cache-Control": "private, no-store"})


@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(models.ProgressPhoto).filter(models.ProgressPhoto.id == photo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Photo not found")
    _remove_photo_file(p)
    db.delete(p)
    db.commit()
    return {"detail": "deleted"}


@router.get("/{client_id}/notes", response_model=List[schemas.ClientNoteResponse])
def list_notes(client_id: int, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    return (db.query(models.ClientNote).filter(models.ClientNote.client_id == client_id)
            .order_by(models.ClientNote.created_at.desc(), models.ClientNote.id.desc()).all())


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
    changes = client.model_dump(exclude_unset=True)
    if "photo_consent" in changes and bool(changes["photo_consent"]) != bool(db_client.photo_consent):
        if changes["photo_consent"]:
            db_client.photo_consent_at = utcnow()
        else:
            # Consent withdrawn: the photos must go, files included
            for p in list(db_client.photos):
                _remove_photo_file(p)
                db.delete(p)
            db_client.photo_consent_at = None
    for key, value in changes.items():
        setattr(db_client, key, value)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    if db_client.payments:
        # Payments are the studio's revenue history: never delete them with the client. Archive instead.
        db_client.active = False
        db.commit()
        return {"detail": "This client has payments, so they were archived instead of deleted. "
                          "Their history and revenue stay in the reports.", "archived": True}
    db.query(models.NotificationLog).filter(models.NotificationLog.client_id == client_id).delete()
    for p in db_client.photos:
        _remove_photo_file(p)
    _remove_avatar(db_client)
    db.delete(db_client)
    db.commit()
    return {"detail": "Client deleted"}
