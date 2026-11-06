"""Unauthenticated endpoints for the client self-booking page and manage-booking links."""
from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, notifications
from backend.scheduling import availability, check_conflicts, within_business_hours, get_settings
from backend.tz import to_utc_naive, utcnow, fmt_date, fmt_time, local_today
from backend.routers.appointments import find_active_subscription

router = APIRouter(prefix="/api/public", tags=["Public"])


class PublicBooking(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    service_id: int
    staff_id: Optional[int] = None
    start_time: datetime
    notes: Optional[str] = None


class CancelBody(BaseModel):
    reason: Optional[str] = None


def _appt_view(a: models.Appointment, settings: models.Setting):
    now = utcnow()
    can_cancel = a.status in ("scheduled", "confirmed") and a.start_time > now + timedelta(hours=settings.online_allow_cancel_hours)
    return {
        "token": a.public_token, "status": a.status,
        "client_name": a.client.name, "service": a.service.name, "duration": a.service.duration_minutes,
        "staff": a.staff.name if a.staff else None,
        "start_time": a.start_time, "date": fmt_date(a.start_time, settings.timezone), "time": fmt_time(a.start_time, settings.timezone),
        "price": a.price, "covered_by_package": bool(a.subscription_id), "currency": settings.currency,
        "can_cancel": can_cancel, "can_confirm": a.status == "scheduled" and a.start_time > now,
        "cancel_notice_hours": settings.online_allow_cancel_hours,
        "business": {"name": settings.business_name, "phone": settings.business_phone, "address": settings.business_address},
    }


@router.get("/info")
def info(db: Session = Depends(get_db)):
    s = get_settings(db)
    services = db.query(models.Service).filter(models.Service.active == True, models.Service.online_bookable == True)\
        .order_by(models.Service.price).all()
    staff = db.query(models.Staff).filter(models.Staff.active == True).order_by(models.Staff.name).all()
    hours = db.query(models.BusinessHours).order_by(models.BusinessHours.day_of_week).all()
    plans = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.active == True)\
        .order_by(models.SubscriptionPlan.price).all()
    return {
        "business_name": s.business_name, "phone": s.business_phone, "email": s.business_email, "address": s.business_address,
        "timezone": s.timezone, "currency": s.currency, "online_booking_enabled": s.online_booking_enabled,
        "min_notice_hours": s.online_min_notice_hours, "max_days_ahead": s.online_max_days_ahead,
        "today": local_today(s.timezone).isoformat(),
        "services": [{"id": x.id, "name": x.name, "duration_minutes": x.duration_minutes, "price": x.price,
                      "description": x.description, "color": x.color} for x in services],
        "staff": [{"id": x.id, "name": x.name, "role": x.role, "color": x.color} for x in staff],
        "hours": [{"day_of_week": h.day_of_week, "open_time": h.open_time, "close_time": h.close_time, "closed": h.closed} for h in hours],
        "plans": [{"id": p.id, "name": p.name, "sessions_included": p.sessions_included, "duration_days": p.duration_days,
                   "price": p.price, "description": p.description} for p in plans],
    }


@router.get("/availability")
def public_availability(service_id: int, date: date, staff_id: Optional[int] = None, db: Session = Depends(get_db)):
    s = get_settings(db)
    if not s.online_booking_enabled:
        raise HTTPException(status_code=403, detail="Online booking is disabled")
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.active == True).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    if date > local_today(s.timezone) + timedelta(days=s.online_max_days_ahead):
        raise HTTPException(status_code=400, detail=f"You can book up to {s.online_max_days_ahead} days ahead")
    result = availability(db, service, date, staff_id, public=True)
    result["slots"] = [sl for sl in result["slots"] if sl["available"]]  # never leak other clients' bookings
    return result


@router.post("/book")
def book(body: PublicBooking, db: Session = Depends(get_db)):
    s = get_settings(db)
    if not s.online_booking_enabled:
        raise HTTPException(status_code=403, detail="Online booking is disabled")
    service = db.query(models.Service).filter(models.Service.id == body.service_id, models.Service.active == True,
                                              models.Service.online_bookable == True).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    if not body.name.strip() or len(notifications.normalize_phone(body.phone)) < 9:
        raise HTTPException(status_code=400, detail="Please enter your name and a valid phone number")
    start = to_utc_naive(body.start_time)
    end = start + timedelta(minutes=service.duration_minutes)
    now = utcnow()
    if start < now + timedelta(hours=s.online_min_notice_hours):
        raise HTTPException(status_code=409, detail=f"Bookings need at least {s.online_min_notice_hours} hours notice")
    if start > now + timedelta(days=s.online_max_days_ahead):
        raise HTTPException(status_code=409, detail=f"You can book up to {s.online_max_days_ahead} days ahead")
    ok, why = within_business_hours(db, start, end, s.timezone)
    if not ok:
        raise HTTPException(status_code=409, detail=why)
    conflict = check_conflicts(db, start, end, service, body.staff_id)
    if conflict:
        raise HTTPException(status_code=409, detail="That time was just taken, please pick another slot")

    phone_norm = notifications.normalize_phone(body.phone)
    client = None
    for c in db.query(models.Client).all():
        if notifications.normalize_phone(c.phone) == phone_norm:
            client = c
            break
    if not client:
        client = models.Client(name=body.name.strip(), phone=body.phone.strip(), email=(body.email or "").strip() or None,
                               source="online")
        db.add(client)
        db.commit()
        db.refresh(client)
    elif body.email and not client.email:
        client.email = body.email.strip()

    sub = find_active_subscription(db, client.id, start)
    appt = models.Appointment(client_id=client.id, service_id=service.id, staff_id=body.staff_id,
                              subscription_id=sub.id if sub else None, start_time=start, end_time=end,
                              status="scheduled", price=0.0 if sub else float(service.price or 0),
                              notes=body.notes, source="online")
    if sub:
        sub.sessions_used += 1
    db.add(appt)
    db.commit()
    db.refresh(appt)
    try:
        notifications.send_booking_confirmation(db, appt)
        notifications.notify_admin_new_booking(db, appt)
    except Exception as e:
        print(f"[notify] online booking notification failed: {e}")
    return _appt_view(appt, s)


@router.get("/appointments/{token}")
def view_appointment(token: str, db: Session = Depends(get_db)):
    a = db.query(models.Appointment).filter(models.Appointment.public_token == token).first()
    if not a:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _appt_view(a, get_settings(db))


@router.post("/appointments/{token}/confirm")
def confirm_appointment(token: str, db: Session = Depends(get_db)):
    a = db.query(models.Appointment).filter(models.Appointment.public_token == token).first()
    if not a:
        raise HTTPException(status_code=404, detail="Booking not found")
    if a.status == "scheduled":
        a.status = "confirmed"
        a.confirmed_at = utcnow()
        db.commit()
    return _appt_view(a, get_settings(db))


@router.post("/appointments/{token}/cancel")
def cancel_appointment(token: str, body: CancelBody, db: Session = Depends(get_db)):
    a = db.query(models.Appointment).filter(models.Appointment.public_token == token).first()
    if not a:
        raise HTTPException(status_code=404, detail="Booking not found")
    s = get_settings(db)
    view = _appt_view(a, s)
    if not view["can_cancel"]:
        raise HTTPException(status_code=409, detail=f"Cancellations need at least {s.online_allow_cancel_hours} hours notice. "
                                                   f"Please call {s.business_phone or 'the studio'}.")
    a.status = "cancelled"
    a.cancelled_at = utcnow()
    a.cancelled_by = "client"
    a.cancel_reason = body.reason
    if a.subscription and a.subscription.sessions_used > 0:
        a.subscription.sessions_used -= 1
    db.commit()
    try:
        notifications.send_cancellation(db, a)
    except Exception as e:
        print(f"[notify] cancellation failed: {e}")
    return _appt_view(a, s)
