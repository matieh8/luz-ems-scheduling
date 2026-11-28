"""Business hours, conflict detection and slot availability."""
from datetime import datetime, timedelta, date
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from backend import models
from backend.tz import local_to_utc, to_local, utcnow

ACTIVE_STATUSES = models.ACTIVE_STATUSES


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


DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def trainer_unavailable(staff: Optional[models.Staff], start: datetime, end: datetime, tz: str) -> Optional[str]:
    """Why the trainer can't take this session under their weekly hours, or None."""
    hours = staff.work_hours if staff else None
    if not hours:
        return None
    ls, le = to_local(start, tz), to_local(end, tz)
    key = str(ls.weekday())
    if key not in hours:
        return None  # day not set: follows the studio's hours
    day = hours[key]
    if day is None:
        return f"{staff.name} doesn't work on {DAY_NAMES[ls.weekday()]}s"
    if ls.strftime("%H:%M") < day[0] or le.date() > ls.date() or le.strftime("%H:%M") > day[1]:
        return f"{staff.name} works {day[0]}–{day[1]} on {DAY_NAMES[ls.weekday()]}s"
    return None


def client_clash(db: Session, client_id: Optional[int], start: datetime, end: datetime,
                 exclude_id: Optional[int] = None) -> Optional[models.Appointment]:
    """The client's other open session that overlaps this time, if any (a client can't be in two places)."""
    if not client_id:
        return None
    q = (db.query(models.Appointment).filter(models.Appointment.client_id == client_id,
                                            models.Appointment.status.in_(ACTIVE_STATUSES),
                                            models.Appointment.start_time < end, models.Appointment.end_time > start))
    if exclude_id:
        q = q.filter(models.Appointment.id != exclude_id)
    return q.first()


def session_capacity(db: Session, settings: models.Setting) -> Tuple[int, Optional[str]]:
    """How many sessions can run at once: the studio setting, limited to the machines that are working."""
    cap = settings.max_concurrent_sessions or 1
    machines = db.query(models.Device).filter(models.Device.needed_for_sessions == True,  # noqa: E712
                                              models.Device.status != "retired").all()
    if not machines:
        return cap, None
    working = sum(1 for d in machines if d.status == "active")
    if working == 0:
        return 0, "No machine available: every machine is in repair"
    return min(cap, working), None


def check_conflicts(db: Session, start: datetime, end: datetime, service: models.Service,
                    staff_id: Optional[int], exclude_id: Optional[int] = None,
                    client_id: Optional[int] = None) -> Optional[str]:
    """Return a human-readable reason if the slot cannot be booked, else None."""
    settings = get_settings(db)
    buffer = timedelta(minutes=service.buffer_minutes or 0)
    s, e = start, end + buffer
    block = blocked_for(db, s, e, staff_id)
    if block:
        return f"Time is blocked: {block.reason or 'unavailable'}"
    if staff_id is not None:
        why = trainer_unavailable(db.get(models.Staff, staff_id), start, end, settings.timezone)
        if why:
            return why
    clash = client_clash(db, client_id, start, end, exclude_id)
    if clash:
        return f"{clash.client.name} already has a session at {to_local(clash.start_time, settings.timezone):%H:%M} that day"
    overlaps = overlapping_appointments(db, s, e, exclude_id)
    if staff_id is not None:
        for a in overlaps:
            if a.staff_id == staff_id:
                return f"{a.staff.name if a.staff else 'Trainer'} already has {a.client.name} at that time"
    cap, why = session_capacity(db, settings)
    if why:
        return why
    if len(overlaps) >= cap:
        return f"All {cap} machine{'s are' if cap != 1 else ' is'} booked at that time"
    return None


def availability(db: Session, service: models.Service, day: date, staff_id: Optional[int] = None,
                 public: bool = False, exclude_id: Optional[int] = None, client_id: Optional[int] = None,
                 minutes: Optional[int] = None):
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
    duration = timedelta(minutes=minutes or service.duration_minutes)
    now = utcnow()
    min_start = now + timedelta(hours=settings.online_min_notice_hours or 0) if public else now
    t = day_open
    while t + duration <= day_close:
        slot_end = t + duration
        available, reason = True, None
        if t < min_start:
            available, reason = False, "past"
        else:
            conflict = check_conflicts(db, t, slot_end, service, staff_id, exclude_id, client_id)
            if conflict:
                available, reason = False, conflict
        result["slots"].append({
            "start_time": t, "end_time": slot_end,
            "label": to_local(t, tz).strftime("%I:%M %p").lstrip("0"),
            "available": available, "reason": reason,
        })
        t += step
    return result
