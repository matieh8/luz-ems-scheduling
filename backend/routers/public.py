"""Unauthenticated endpoints for the client self-booking page and manage-booking links."""
import time
from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, notifications, push
from backend.scheduling import availability, check_conflicts, within_business_hours, get_settings
from backend.tz import to_utc_naive, utcnow, fmt_date, fmt_time, local_today, to_local

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
        "currency": settings.currency,
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
        "services": [{"id": x.id, "name": x.name, "duration_minutes": x.duration_minutes,
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


_BOOKINGS_BY_IP: dict = {}
MAX_BOOKINGS_PER_HOUR = 10


def _too_many_bookings(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _BOOKINGS_BY_IP.get(ip, []) if t > now - 3600]
    _BOOKINGS_BY_IP[ip] = recent
    if len(_BOOKINGS_BY_IP) > 10000:
        for k in [k for k, v in _BOOKINGS_BY_IP.items() if not v or v[-1] <= now - 3600]:
            _BOOKINGS_BY_IP.pop(k, None)
    return len(recent) >= MAX_BOOKINGS_PER_HOUR


@router.post("/book")
def book(body: PublicBooking, request: Request, db: Session = Depends(get_db)):
    s = get_settings(db)
    if not s.online_booking_enabled:
        raise HTTPException(status_code=403, detail="Online booking is disabled")
    ip = request.client.host if request.client else "?"
    if _too_many_bookings(ip):
        raise HTTPException(status_code=429, detail="Too many bookings from this connection. Please call the studio.")
    if body.staff_id is not None and not db.query(models.Staff).filter(models.Staff.id == body.staff_id,
                                                                     models.Staff.active == True).first():
        raise HTTPException(status_code=400, detail="That trainer isn't available")
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
    # shortcut: compares every client's phone in Python; fine up to a few thousand clients, add an indexed normalised phone column beyond that
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

    # Anyone can type any phone number here, so an online booking never uses a package session by itself.
    # The studio links it to the client's package when they confirm or complete the session.
    appt = models.Appointment(client_id=client.id, service_id=service.id, staff_id=body.staff_id,
                              subscription_id=None, start_time=start, end_time=end,
                              status="scheduled", price=float(service.price or 0),
                              notes=body.notes, source="online")
    db.add(appt)
    db.commit()
    db.refresh(appt)
    _BOOKINGS_BY_IP.setdefault(ip, []).append(time.time())
    try:
        notifications.send_booking_confirmation(db, appt)
        notifications.notify_admin_new_booking(db, appt)
    except Exception as e:
        print(f"[notify] online booking notification failed: {e}")
    push.notify(db, "booking", "New online booking", notifications.push_line(appt, s), url="/admin#calendar",
                tag=f"booking-{appt.id}")
    view = _appt_view(appt, s)
    view["client_name"] = body.name.strip()  # never reveal the name stored for that phone number
    return view


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
    s = get_settings(db)
    if a.status == "scheduled":
        a.status = "confirmed"
        a.confirmed_at = utcnow()
        db.commit()
        push.notify(db, "booking", f"{a.client.name} confirmed", notifications.push_line(a, s, with_client=False),
                    url="/admin#calendar", tag=f"booking-{a.id}")
    return _appt_view(a, s)


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
    db.commit()
    try:
        notifications.send_cancellation(db, a)
    except Exception as e:
        print(f"[notify] cancellation failed: {e}")
    reason = f" Reason: {body.reason.strip()}" if (body.reason or "").strip() else ""
    push.notify(db, "booking", f"{a.client.name} cancelled", notifications.push_line(a, s, with_client=False) + reason,
                url="/admin#calendar", tag=f"booking-{a.id}")
    return _appt_view(a, s)


# ---------------------------------------------------------------- the client's own page (/c/<token>)

def _portal_client(db: Session, token: str) -> models.Client:
    c = db.query(models.Client).filter(models.Client.portal_token == token).first() if token else None
    if not c or not c.active:
        raise HTTPException(status_code=404, detail="This link isn't active. Ask the studio for a new one.")
    return c


@router.get("/portal/{token}")
def portal(token: str, db: Session = Depends(get_db)):
    """Read-only view of one client's own bookings, packages, payments and progress.
    Staff notes, health notes and photos are never included."""
    c = _portal_client(db, token)
    s = get_settings(db)
    tz, now = s.timezone, utcnow()
    when = lambda dt: {"date": fmt_date(dt, tz), "time": fmt_time(dt, tz)}
    appts = sorted(c.appointments, key=lambda a: a.start_time)
    upcoming = [{"token": a.public_token, "service": a.service.name if a.service else "", "status": a.status,
                 "staff": a.staff.name if a.staff else None, **when(a.start_time)}
                for a in appts if a.start_time >= now and a.status in ("scheduled", "confirmed")]
    history = [{"service": a.service.name if a.service else "", "status": a.status, **when(a.start_time)}
               for a in reversed(appts) if a.start_time < now and a.status in ("completed", "no_show")][:30]
    packages = [{"name": p.plan.name if p.plan else "Package", "sessions_total": p.sessions_total,
                 "sessions_used": p.sessions_used, "sessions_remaining": p.sessions_remaining,
                 "start": fmt_date(p.start_date, tz) if p.start_date else None,
                 "end": fmt_date(p.end_date, tz) if p.end_date else None,
                 "active": p.status == "active" and p.sessions_remaining > 0 and (p.end_date is None or p.end_date >= now)}
                for p in sorted(c.subscriptions, key=lambda p: p.start_date or p.created_at, reverse=True)]

    def paid_for(p):
        if p.subscription and p.subscription.plan:
            return p.subscription.plan.name
        if p.appointment and p.appointment.service:
            return f"{p.appointment.service.name} session"
        return "Payment"
    payments = [{"id": p.id, "date": fmt_date(p.paid_at, tz), "amount": round(float(p.amount), 2), "method": p.method,
                 "for": paid_for(p)} for p in sorted(c.payments, key=lambda p: (p.paid_at, p.id), reverse=True)]
    progress = [{"date": to_local(m.measured_at, tz).date().isoformat(), "weight_kg": m.weight_kg,
                 "body_fat_pct": m.body_fat_pct, "muscle_kg": m.muscle_kg, "waist_cm": m.waist_cm}
                for m in sorted(c.measurements, key=lambda m: m.measured_at)]
    owed = models.unpaid_sessions(db, db.query(models.Appointment).filter(models.Appointment.client_id == c.id))
    return {"name": c.name, "currency": s.currency, "online_booking": bool(s.online_booking_enabled),
            "business": {"name": s.business_name, "phone": s.business_phone, "address": s.business_address},
            "upcoming": upcoming, "history": history, "packages": packages, "payments": payments,
            "progress": progress, "owed": round(sum(a.balance_due for a in owed), 2)}


@router.get("/portal/{token}/invoice/{payment_id}")
def portal_invoice(token: str, payment_id: int, db: Session = Depends(get_db)):
    from backend.routers.payments import invoice_data
    c = _portal_client(db, token)
    p = db.query(models.Payment).filter(models.Payment.id == payment_id, models.Payment.client_id == c.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice_data(db, p)
