from datetime import datetime, timedelta, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas, notifications
from backend.scheduling import check_conflicts, within_business_hours, availability, get_settings
from backend.tz import to_utc_naive, utcnow

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


def find_active_subscription(db: Session, client_id: int, at: datetime) -> Optional[models.Subscription]:
    subs = (
        db.query(models.Subscription)
        .filter(models.Subscription.client_id == client_id)
        .filter(models.Subscription.status == "active")
        .order_by(models.Subscription.end_date.asc().nulls_last())
        .all()
    )
    for s in subs:
        if s.sessions_remaining > 0 and (s.end_date is None or s.end_date >= at):
            return s
    return None


def validate_slot(db: Session, start: datetime, end: datetime, service: models.Service,
                  staff_id: Optional[int], force: bool, exclude_id: Optional[int] = None):
    settings = get_settings(db)
    if force:
        return
    ok, why = within_business_hours(db, start, end, settings.timezone)
    if not ok:
        raise HTTPException(status_code=409, detail=why)
    conflict = check_conflicts(db, start, end, service, staff_id, exclude_id)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)


@router.get("/", response_model=List[schemas.AppointmentResponse])
def list_appointments(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    client_id: Optional[int] = None,
    staff_id: Optional[int] = None,
    status: Optional[str] = None,
    unpaid: bool = False,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    query = db.query(models.Appointment)
    if from_date:
        query = query.filter(models.Appointment.start_time >= to_utc_naive(from_date))
    if to_date:
        query = query.filter(models.Appointment.start_time < to_utc_naive(to_date))
    if client_id:
        query = query.filter(models.Appointment.client_id == client_id)
    if staff_id:
        query = query.filter(models.Appointment.staff_id == staff_id)
    if status:
        query = query.filter(models.Appointment.status.in_(status.split(",")))
    rows = query.order_by(models.Appointment.start_time).limit(limit).all()
    if unpaid:
        rows = [a for a in rows if a.balance_due > 0]
    return rows


@router.get("/availability", response_model=schemas.AvailabilityResponse)
def get_availability(service_id: int, day: date = Query(..., alias="date"), staff_id: Optional[int] = None,
                     exclude_id: Optional[int] = None, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return availability(db, service, day, staff_id, public=False, exclude_id=exclude_id)


@router.post("/", response_model=schemas.AppointmentResponse)
def create_appointment(body: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    if body.client_id:
        client = db.query(models.Client).filter(models.Client.id == body.client_id).first()
        if not client:
            raise HTTPException(status_code=400, detail="Client not found")
    else:
        if not body.client_name or not body.client_phone:
            raise HTTPException(status_code=400, detail="Client name and phone are required")
        client = models.Client(name=body.client_name.strip(), phone=body.client_phone.strip(),
                               email=(body.client_email or "").strip() or None, source="walk-in")
        db.add(client)
        db.commit()
        db.refresh(client)

    service = db.query(models.Service).filter(models.Service.id == body.service_id).first()
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")
    if body.staff_id and not db.query(models.Staff).filter(models.Staff.id == body.staff_id).first():
        raise HTTPException(status_code=400, detail="Trainer not found")

    start = to_utc_naive(body.start_time)
    end = start + timedelta(minutes=service.duration_minutes)
    validate_slot(db, start, end, service, body.staff_id, body.force)

    sub = None
    if body.use_subscription is not False:
        sub = find_active_subscription(db, client.id, start)
        if body.use_subscription is True and not sub:
            raise HTTPException(status_code=400, detail="Client has no active package with sessions left")
    price = body.price if body.price is not None else (0.0 if sub else float(service.price or 0))

    appt = models.Appointment(
        client_id=client.id, service_id=service.id, staff_id=body.staff_id,
        subscription_id=sub.id if sub else None, start_time=start, end_time=end,
        status="scheduled", price=price, notes=body.notes, source="admin",
    )
    if sub:
        sub.sessions_used += 1
    db.add(appt)
    db.commit()
    db.refresh(appt)

    if body.send_notification:
        try:
            notifications.send_booking_confirmation(db, appt)
        except Exception as e:
            print(f"[notify] confirmation failed: {e}")
    return appt


@router.get("/{appointment_id}", response_model=schemas.AppointmentResponse)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.put("/{appointment_id}", response_model=schemas.AppointmentResponse)
def update_appointment(appointment_id: int, body: schemas.AppointmentUpdate, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    data = body.model_dump(exclude_unset=True, exclude={"send_notification", "force"})
    old_start = appt.start_time
    if "start_time" in data and data["start_time"] is not None:
        data["start_time"] = to_utc_naive(data["start_time"])
    for k, v in data.items():
        setattr(appt, k, v)
    service = db.query(models.Service).filter(models.Service.id == appt.service_id).first()
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")
    appt.end_time = appt.start_time + timedelta(minutes=service.duration_minutes)
    if any(k in data for k in ("start_time", "service_id", "staff_id")) and appt.status in ("scheduled", "confirmed"):
        validate_slot(db, appt.start_time, appt.end_time, service, appt.staff_id, body.force, exclude_id=appt.id)
    db.commit()
    db.refresh(appt)
    if appt.start_time != old_start and body.send_notification and appt.status in ("scheduled", "confirmed"):
        try:
            notifications.send_reschedule(db, appt)
        except Exception as e:
            print(f"[notify] reschedule failed: {e}")
    return appt


@router.post("/{appointment_id}/status", response_model=schemas.AppointmentResponse)
def change_status(appointment_id: int, body: schemas.AppointmentStatusChange, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    new = body.status
    if new not in ("scheduled", "confirmed", "completed", "cancelled", "no_show"):
        raise HTTPException(status_code=400, detail="Invalid status")
    old = appt.status
    now = utcnow()
    sub = appt.subscription

    if new == "cancelled" and old != "cancelled":
        appt.cancelled_at = now
        appt.cancel_reason = body.reason
        appt.cancelled_by = "admin"
        if sub and sub.sessions_used > 0:
            sub.sessions_used -= 1  # give the session back
    if old == "cancelled" and new != "cancelled" and sub:
        sub.sessions_used += 1  # re-booked: consume again
        appt.cancelled_at = None
        appt.cancel_reason = None
        appt.cancelled_by = None
    if new == "confirmed":
        appt.confirmed_at = now
    if new == "completed":
        appt.completed_at = now
        if body.payment_amount and body.payment_amount > 0:
            db.add(models.Payment(client_id=appt.client_id, appointment_id=appt.id,
                                  amount=body.payment_amount, method=body.payment_method or "cash", paid_at=now))
    appt.status = new
    db.commit()
    db.refresh(appt)

    if new == "cancelled" and old != "cancelled" and body.send_notification:
        try:
            notifications.send_cancellation(db, appt)
        except Exception as e:
            print(f"[notify] cancellation failed: {e}")
    return appt


@router.delete("/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.subscription and appt.status != "cancelled" and appt.subscription.sessions_used > 0:
        appt.subscription.sessions_used -= 1
    for p in appt.payments:
        p.appointment_id = None
    db.delete(appt)
    db.commit()
    return {"detail": "Appointment deleted"}


# ---------------- blocked time ----------------
blocked_router = APIRouter(prefix="/api/blocked-times", tags=["Blocked time"])


@blocked_router.get("/", response_model=List[schemas.BlockedTimeResponse])
def list_blocked(from_date: Optional[datetime] = None, to_date: Optional[datetime] = None,
                 db: Session = Depends(get_db)):
    q = db.query(models.BlockedTime)
    if from_date:
        q = q.filter(models.BlockedTime.end_time >= to_utc_naive(from_date))
    if to_date:
        q = q.filter(models.BlockedTime.start_time < to_utc_naive(to_date))
    return q.order_by(models.BlockedTime.start_time).all()


@blocked_router.post("/", response_model=schemas.BlockedTimeResponse)
def create_blocked(body: schemas.BlockedTimeCreate, db: Session = Depends(get_db)):
    start, end = to_utc_naive(body.start_time), to_utc_naive(body.end_time)
    if end <= start:
        raise HTTPException(status_code=400, detail="End must be after start")
    b = models.BlockedTime(staff_id=body.staff_id, start_time=start, end_time=end, reason=body.reason)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@blocked_router.delete("/{blocked_id}")
def delete_blocked(blocked_id: int, db: Session = Depends(get_db)):
    b = db.query(models.BlockedTime).filter(models.BlockedTime.id == blocked_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(b)
    db.commit()
    return {"detail": "Deleted"}
