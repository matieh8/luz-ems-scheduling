"""Business hours, conflict detection and slot availability."""
from datetime import datetime, timedelta, date
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from backend import models
from backend.tz import local_to_utc, to_local, utcnow

ACTIVE_STATUSES = ("scheduled", "confirmed")


def get_settings(db: Session) -> models.Setting:
    s = db.query(models.Setting).first()
    if not s:
        s = models.Setting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def hours_for_day(db: Session, day_of_week: int) -> Optional[models.BusinessHours]:
    return db.query(models.BusinessHours).filter(models.BusinessHours.day_of_week == day_of_week).first()


def _parse_hm(s: str) -> Tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def within_business_hours(db: Session, start: datetime, end: datetime, tz_name: str) -> Tuple[bool, str]:
    local_start = to_local(start, tz_name)
    local_end = to_local(end, tz_name)
    bh = hours_for_day(db, local_start.weekday())
    if not bh or bh.closed:
        return False, "Studio is closed that day"
    oh, om = _parse_hm(bh.open_time)
    ch, cm = _parse_hm(bh.close_time)
    day_open = local_start.replace(hour=oh, minute=om, second=0, microsecond=0)
    day_close = local_start.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if local_start < day_open or local_end > day_close:
        return False, f"Outside opening hours ({bh.open_time} - {bh.close_time})"
    return True, ""


def overlapping_appointments(db: Session, start: datetime, end: datetime,
                             exclude_id: Optional[int] = None) -> List[models.Appointment]:
    q = (
        db.query(models.Appointment)
        .filter(models.Appointment.status.in_(ACTIVE_STATUSES))
        .filter(models.Appointment.start_time < end)
        .filter(models.Appointment.end_time > start)
    )
    if exclude_id:
        q = q.filter(models.Appointment.id != exclude_id)
    return q.all()


def blocked_for(db: Session, start: datetime, end: datetime, staff_id: Optional[int]) -> Optional[models.BlockedTime]:
    q = (
        db.query(models.BlockedTime)
        .filter(models.BlockedTime.start_time < end)
        .filter(models.BlockedTime.end_time > start)
    )
    for b in q.all():
        if b.staff_id is None or (staff_id is not None and b.staff_id == staff_id):
            return b
    return None


def check_conflicts(db: Session, start: datetime, end: datetime, service: models.Service,
                    staff_id: Optional[int], exclude_id: Optional[int] = None) -> Optional[str]:
    """Return a human-readable reason if the slot cannot be booked, else None."""
    settings = get_settings(db)
    buffer = timedelta(minutes=service.buffer_minutes or 0)
    s, e = start, end + buffer
    block = blocked_for(db, s, e, staff_id)
    if block:
        return f"Time is blocked: {block.reason or 'unavailable'}"
    overlaps = overlapping_appointments(db, s, e, exclude_id)
    if staff_id is not None:
        for a in overlaps:
            if a.staff_id == staff_id:
                return f"{a.staff.name if a.staff else 'Trainer'} already has {a.client.name} at that time"
    if len(overlaps) >= (settings.max_concurrent_sessions or 1):
        return "All machines are booked at that time"
    return None


def availability(db: Session, service: models.Service, day: date, staff_id: Optional[int] = None,
                 public: bool = False, exclude_id: Optional[int] = None):
    settings = get_settings(db)
    tz = settings.timezone
    bh = hours_for_day(db, day.weekday())
    result = {"date": day.isoformat(), "timezone": tz, "open": False, "open_time": None,
              "close_time": None, "slots": []}
    if not bh or bh.closed:
        return result
    result.update(open=True, open_time=bh.open_time, close_time=bh.close_time)
    oh, om = _parse_hm(bh.open_time)
    ch, cm = _parse_hm(bh.close_time)
    day_open = local_to_utc(datetime(day.year, day.month, day.day, oh, om), tz)
    day_close = local_to_utc(datetime(day.year, day.month, day.day, ch, cm), tz)
    step = timedelta(minutes=settings.slot_interval_minutes or 30)
    duration = timedelta(minutes=service.duration_minutes)
    now = utcnow()
    min_start = now + timedelta(hours=settings.online_min_notice_hours or 0) if public else now
    t = day_open
    while t + duration <= day_close:
        slot_end = t + duration
        available, reason = True, None
        if t < min_start:
            available, reason = False, "past"
        else:
            conflict = check_conflicts(db, t, slot_end, service, staff_id, exclude_id)
            if conflict:
                available, reason = False, conflict
        result["slots"].append({
            "start_time": t, "end_time": slot_end,
            "label": to_local(t, tz).strftime("%I:%M %p").lstrip("0"),
            "available": available, "reason": reason,
        })
        t += step
    return result
