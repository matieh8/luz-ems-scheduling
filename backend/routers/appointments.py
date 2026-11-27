from datetime import datetime, timedelta, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas, notifications
from backend.scheduling import check_conflicts, within_business_hours, availability, get_settings
import secrets
from backend.tz import to_utc_naive, utcnow, to_local, local_to_utc, fmt_date

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


def link_online_booking_to_package(db: Session, appt: models.Appointment) -> Optional[models.Subscription]:
    """Online bookings don't touch a package until the studio has seen the client (see public.book).
    Called when staff confirm or complete one, and by the auto-complete job."""
    if appt.source != "online" or appt.subscription_id:
        return None
    found = find_active_subscription(db, appt.client_id, appt.start_time)
    if found:
        appt.subscription_id, appt.price = found.id, 0.0
    return found


def recheck_package(db: Session, appt: models.Appointment):
    """Keep a session on its package only if the package can still cover it (sessions left, not ended by then);
    otherwise move it to another usable package of the client, or make it pay-per-session. Never overdraws."""
    sub = appt.subscription
    if not sub:
        return
    others = sum(1 for a in sub.appointments if a.id != appt.id and a.status != "cancelled")
    fits = int(sub.sessions_used_before or 0) + others < sub.sessions_total and (sub.end_date is None or sub.end_date >= appt.start_time)
    if fits and sub.status in ("active", "completed"):  # "completed" = every session booked, not ended
        return
    other = find_active_subscription(db, appt.client_id, appt.start_time)
    other = other if other and other.id != sub.id else None
    appt.subscription_id = other.id if other else None
    appt.price = 0.0 if other else float(appt.service.price or 0)


def may_force(request: Request) -> bool:
    """Only the owner and managers may book over a clash or outside opening hours."""
    ident = getattr(request.state, "identity", None) or {"role": "owner"}
    return ident["role"] in ("owner", "manager")


def validate_slot(db: Session, start: datetime, end: datetime, service: models.Service,
                  staff_id: Optional[int], force: bool, exclude_id: Optional[int] = None, client_id: Optional[int] = None):
    settings = get_settings(db)
    if force:
        return
    ok, why = within_business_hours(db, start, end, settings.timezone)
    if not ok:
        raise HTTPException(status_code=409, detail=why)
    conflict = check_conflicts(db, start, end, service, staff_id, exclude_id, client_id)
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
    query = query.order_by(models.Appointment.start_time)
    if unpaid:  # filter before the limit, or new unpaid sessions fall off the end
        return models.unpaid_sessions(db, query)[:limit]
    return query.limit(limit).all()


@router.get("/availability", response_model=schemas.AvailabilityResponse)
def get_availability(service_id: int, day: date = Query(..., alias="date"), staff_id: Optional[int] = None,
                     exclude_id: Optional[int] = None, client_id: Optional[int] = None,
                     minutes: Optional[int] = Query(None, ge=5, le=240), db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return availability(db, service, day, staff_id, public=False, exclude_id=exclude_id, client_id=client_id, minutes=minutes)


@router.post("/", response_model=schemas.AppointmentResponse)
def create_appointment(body: schemas.AppointmentCreate, request: Request, db: Session = Depends(get_db)):
    body.force = bool(body.force) and may_force(request)
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
    length = timedelta(minutes=body.duration_minutes or service.duration_minutes)
    end = start + length
    validate_slot(db, start, end, service, body.staff_id, body.force, client_id=client.id)

    sub = None
    if body.use_subscription is not False:
        sub = find_active_subscription(db, client.id, start)
        if body.use_subscription is True and not sub:
            raise HTTPException(status_code=400, detail="Client has no active package with sessions left")
    price = body.price if body.price is not None else (0.0 if sub else float(service.price or 0))

    # Repeat booking: same weekday and local time, every N weeks.
    interval = max(int(body.repeat_interval_weeks or 0), 0)
    count = min(max(int(body.repeat_count or 1), 1), 52) if interval else 1
    series_id = secrets.token_urlsafe(8) if count > 1 else None

    appt = models.Appointment(
        client_id=client.id, service_id=service.id, staff_id=body.staff_id,
        subscription_id=sub.id if sub else None, start_time=start, end_time=end,
        status="scheduled", price=price, notes=body.notes, source="admin", series_id=series_id,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    created, skipped, last_start = 1, [], start
    if count > 1:
        tz = get_settings(db).timezone
        local0 = to_local(start, tz).replace(tzinfo=None)
        for i in range(1, count):
            s_i = local_to_utc(local0 + timedelta(weeks=i * interval), tz)
            e_i = s_i + length
            try:
                validate_slot(db, s_i, e_i, service, body.staff_id, body.force, client_id=client.id)
            except HTTPException as ex:
                skipped.append({"date": fmt_date(s_i, tz), "reason": str(ex.detail)})
                continue
            sub_i = find_active_subscription(db, client.id, s_i) if body.use_subscription is not False else None
            price_i = 0.0 if sub_i else (float(body.price) if body.price else float(service.price or 0))
            db.add(models.Appointment(
                client_id=client.id, service_id=service.id, staff_id=body.staff_id,
                subscription_id=sub_i.id if sub_i else None, start_time=s_i, end_time=e_i,
                status="scheduled", price=price_i, notes=body.notes, source="admin", series_id=series_id,
            ))
            db.commit()
            created += 1
            last_start = s_i
        db.refresh(appt)

    notify_result = None
    if body.send_notification:
        append = None
        if created > 1:
            tz = get_settings(db).timezone
            every = "every week" if interval == 1 else f"every {interval} weeks"
            append = f"🔁 This repeats {every} at the same time: {created} sessions in total, until {fmt_date(last_start, tz)}."
        try:
            logs = notifications.send_booking_confirmation(db, appt, append=append, sync=True)
            notify_result = notifications.explain_result(db, "booking_confirmation", client, logs)
        except Exception as e:
            print(f"[notify] confirmation failed: {e}")
            notify_result = [{"channel": None, "status": "failed", "detail": str(e)}]
    appt.notify_result = notify_result
    appt.series_created = created if count > 1 else None
    appt.series_skipped = skipped if count > 1 else None
    return appt


class SeriesCancel(schemas.BaseModel):
    reason: Optional[str] = None
    send_notification: bool = True


@router.post("/{appointment_id}/cancel-series")
def cancel_series(appointment_id: int, body: SeriesCancel, db: Session = Depends(get_db)):
    """Cancel this session and every later open session of the same repeat booking."""
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if not appt.series_id:
        raise HTTPException(status_code=400, detail="This session is not part of a repeat booking")
    now = utcnow()
    rows = (db.query(models.Appointment)
            .filter(models.Appointment.series_id == appt.series_id,
                    models.Appointment.start_time >= appt.start_time,
                    models.Appointment.status.in_(("scheduled", "confirmed")))
            .order_by(models.Appointment.start_time).all())
    for a in rows:
        a.status = "cancelled"
        a.cancelled_at = now
        a.cancel_reason = body.reason
        a.cancelled_by = "admin"
    db.commit()
    if rows and body.send_notification:
        try:
            extra = f"This also cancels the {len(rows) - 1} following repeat session(s)." if len(rows) > 1 else None
            notifications.send(db, "cancellation", rows[0].client, rows[0], append=extra)
        except Exception as e:
            print(f"[notify] series cancellation failed: {e}")
    return {"detail": "Series cancelled", "cancelled": len(rows)}


@router.get("/{appointment_id}", response_model=schemas.AppointmentResponse)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.put("/{appointment_id}", response_model=schemas.AppointmentResponse)
def update_appointment(appointment_id: int, body: schemas.AppointmentUpdate, request: Request, db: Session = Depends(get_db)):
    body.force = bool(body.force) and may_force(request)
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    data = body.model_dump(exclude_unset=True, exclude={"send_notification", "force", "duration_minutes"})
    old_start, old_length, old_service, old_client = appt.start_time, appt.end_time - appt.start_time, appt.service_id, appt.client_id
    if "start_time" in data and data["start_time"] is not None:
        data["start_time"] = to_utc_naive(data["start_time"])
    if data.get("client_id") and not db.query(models.Client).filter(models.Client.id == data["client_id"]).first():
        raise HTTPException(status_code=400, detail="Client not found")
    for k, v in data.items():
        setattr(appt, k, v)
    service = db.query(models.Service).filter(models.Service.id == appt.service_id).first()
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")
    # Length: as given; else the new service's length when the service changed; else keep this booking's own length
    if body.duration_minutes:
        length = timedelta(minutes=body.duration_minutes)
    elif appt.service_id != old_service:
        length = timedelta(minutes=service.duration_minutes)
    else:
        length = old_length
    appt.end_time = appt.start_time + length
    if appt.client_id != old_client and appt.subscription_id:
        # Moved to another client: the old client's package must not pay for it; use the new client's package if any
        new_sub = find_active_subscription(db, appt.client_id, appt.start_time)
        appt.subscription_id = new_sub.id if new_sub else None
        appt.price = 0.0 if new_sub else float(service.price or 0)
    if appt.start_time != old_start and appt.status in ("scheduled", "confirmed"):
        db.flush()
        recheck_package(db, appt)  # moved past the package's end date: it can't use that package any more
    if (any(k in data for k in ("start_time", "service_id", "staff_id", "client_id")) or body.duration_minutes) \
            and appt.status in ("scheduled", "confirmed"):
        validate_slot(db, appt.start_time, appt.end_time, service, appt.staff_id, body.force, exclude_id=appt.id, client_id=appt.client_id)
    db.commit()
    db.refresh(appt)
    if appt.start_time != old_start and body.send_notification and appt.status in ("scheduled", "confirmed"):
        try:
            notifications.send_reschedule(db, appt)
        except Exception as e:
            print(f"[notify] reschedule failed: {e}")
    return appt


@router.post("/{appointment_id}/status", response_model=schemas.AppointmentResponse)
def change_status(appointment_id: int, body: schemas.AppointmentStatusChange, request: Request, db: Session = Depends(get_db)):
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
    if old == "cancelled" and new != "cancelled":  # package use follows the status on its own
        recheck_package(db, appt)  # the package may be full by now: never take it below zero
        sub = appt.subscription
        appt.cancelled_at = None
        appt.cancel_reason = None
        appt.cancelled_by = None
    if new in ("confirmed", "completed"):
        sub = link_online_booking_to_package(db, appt) or sub
    if new == "confirmed":
        appt.confirmed_at = now
    if new == "completed":
        appt.completed_at = now
        if body.late_minutes is not None:
            appt.late_minutes = body.late_minutes
        if body.payment_amount and body.payment_amount > 0 and old != "completed":
            db.add(models.Payment(client_id=appt.client_id, appointment_id=appt.id,
                                  amount=body.payment_amount, method=body.payment_method or "cash", paid_at=now))
    appt.status = new
    db.commit()
    db.refresh(appt)

    if new in ("confirmed", "cancelled") and old != new:  # every device with notifications on hears about it
        ident = getattr(request.state, "identity", None) or {}
        from backend import push
        push.notify(db, "booking", f"{appt.client.name} {new}" + (f" by {ident['name']}" if ident.get("name") else " by the studio"),
                    notifications.push_line(appt, get_settings(db), with_client=False), url="/admin#calendar", tag=f"booking-{appt.id}")
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
