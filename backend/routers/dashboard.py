import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.scheduling import get_settings
from backend.tz import local_day_bounds, local_today, to_local, utcnow

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def _dismissed(settings) -> dict:
    try:
        raw = json.loads(settings.alerts_dismissed or "{}")
    except ValueError:
        raw = {}
    out = {}
    for k, v in raw.items():
        try:
            out[k] = datetime.fromisoformat(v)
        except (TypeError, ValueError):
            pass
    return out


@router.post("/alerts/{key}/dismiss")
def dismiss_alert(key: str, db: Session = Depends(get_db)):
    settings = db.query(models.Setting).first()
    d = {k: v.isoformat() for k, v in _dismissed(settings).items()}
    d[key] = datetime.utcnow().isoformat()  # full precision: a failure logged the same second must not re-trigger
    settings.alerts_dismissed = json.dumps(d)
    db.commit()
    return {"detail": "dismissed", "key": key}


def _pct(value: float, prev: float):
    if not prev:
        return None
    return round((value - prev) / abs(prev) * 100, 1)


def _kpi(value, prev):
    return {"value": value, "prev": prev, "change_pct": _pct(value, prev)}


def _month_start(d: date, back: int = 0) -> date:
    y, m = d.year, d.month - back
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Owner dashboard. Money and sessions are month-to-date, compared with the same days of last month."""
    settings = get_settings(db)
    tz = settings.timezone
    now = utcnow()
    today = local_today(tz)
    this_m = today.replace(day=1)
    prev_m = _month_start(today, 1)
    # Same span last month: day 1 up to today's day number (capped at last month's length)
    prev_span_end_day = min(today.day, (this_m - timedelta(days=1)).day)
    cur_start, _ = local_day_bounds(this_m, tz)
    _, cur_end = local_day_bounds(today, tz)
    prev_start, _ = local_day_bounds(prev_m, tz)
    _, prev_end = local_day_bounds(prev_m.replace(day=prev_span_end_day), tz)

    window_first = _month_start(today, 5)
    window_start, _ = local_day_bounds(window_first, tz)
    periods = [_month_start(today, i).strftime("%Y-%m") for i in range(5, -1, -1)]
    months = {p: {"period": p, "revenue": 0.0, "expenses": 0.0, "profit": 0.0, "sessions": 0} for p in periods}

    def key(dt):
        return to_local(dt, tz).strftime("%Y-%m")

    def in_span(dt, start, end):
        return start <= dt < end

    span_start = min(window_start, prev_start)
    # Everything stops at the end of today, so bills entered ahead of time don't count yet
    payments = db.query(models.Payment).filter(models.Payment.paid_at >= span_start, models.Payment.paid_at < cur_end).all()
    expenses = db.query(models.Expense).filter(models.Expense.date >= span_start, models.Expense.date < cur_end).all()
    done = db.query(models.Appointment).filter(models.Appointment.start_time >= span_start, models.Appointment.start_time < cur_end,
                                                models.Appointment.status == "completed").all()
    for p in payments:
        k = key(p.paid_at)
        if k in months:
            months[k]["revenue"] += float(p.amount)
    for e in expenses:
        k = key(e.date)
        if k in months:
            months[k]["expenses"] += float(e.amount)
    for a in done:
        k = key(a.start_time)
        if k in months:
            months[k]["sessions"] += 1
    for m in months.values():
        m["revenue"] = round(m["revenue"], 2)
        m["expenses"] = round(m["expenses"], 2)
        m["profit"] = round(m["revenue"] - m["expenses"], 2)

    rev = round(sum(float(p.amount) for p in payments if in_span(p.paid_at, cur_start, cur_end)), 2)
    rev_prev = round(sum(float(p.amount) for p in payments if in_span(p.paid_at, prev_start, prev_end)), 2)
    exp = round(sum(float(e.amount) for e in expenses if in_span(e.date, cur_start, cur_end)), 2)
    exp_prev = round(sum(float(e.amount) for e in expenses if in_span(e.date, prev_start, prev_end)), 2)
    ses = sum(1 for a in done if in_span(a.start_time, cur_start, cur_end))
    ses_prev = sum(1 for a in done if in_span(a.start_time, prev_start, prev_end))

    # Active clients: anyone with a session (not cancelled) in the last 30 days, vs the 30 days before that
    def active_clients(start, end):
        q = db.query(func.count(func.distinct(models.Appointment.client_id))).filter(
            models.Appointment.start_time >= start, models.Appointment.start_time < end,
            models.Appointment.status.in_(("scheduled", "confirmed", "completed")))
        return int(q.scalar() or 0)
    ac = active_clients(now - timedelta(days=30), now + timedelta(seconds=1))
    ac_prev = active_clients(now - timedelta(days=60), now - timedelta(days=30))

    today_start, today_end = local_day_bounds(today, tz)
    sessions_today = db.query(func.count(models.Appointment.id)).filter(
        models.Appointment.start_time >= today_start, models.Appointment.start_time < today_end,
        models.Appointment.status != "cancelled").scalar() or 0

    # Packages
    subs = db.query(models.Subscription).all()
    soon = now + timedelta(days=settings.subscription_expiry_notice_days)
    active, expiring, ended = [], [], 0
    for s in subs:
        usable = s.status == "active" and s.sessions_remaining > 0 and (s.end_date is None or s.end_date >= now)
        if usable:
            if (s.end_date and s.end_date <= soon) or s.sessions_remaining <= settings.subscription_low_threshold:
                expiring.append(s)
            else:
                active.append(s)
        elif s.status != "cancelled":
            last = s.end_date if (s.end_date and s.end_date < now) else s.updated_at
            if last and last >= now - timedelta(days=30):
                ended += 1
    expiring.sort(key=lambda s: (s.end_date or datetime.max, s.sessions_remaining))
    sessions_remaining = sum(s.sessions_remaining for s in active + expiring)

    # Money still owed for completed sessions
    unpaid = [a for a in db.query(models.Appointment).filter(models.Appointment.status == "completed").all() if a.balance_due > 0]

    # Best sellers this month
    svc = defaultdict(lambda: {"count": 0, "value": 0.0})
    for a in db.query(models.Appointment).filter(models.Appointment.start_time >= cur_start, models.Appointment.start_time < cur_end,
                                                 models.Appointment.status.in_(("scheduled", "confirmed", "completed"))).all():
        row = svc[a.service.name if a.service else "Other"]
        row["count"] += 1
        if a.subscription_id and a.subscription and a.subscription.sessions_total:
            row["value"] += float(a.subscription.price_paid) / a.subscription.sessions_total
        else:
            row["value"] += float(a.price or 0)
    top_services = sorted(({"name": k, "count": v["count"], "value": round(v["value"], 2)} for k, v in svc.items()),
                          key=lambda r: (-r["count"], -r["value"]))[:5]
    pl = defaultdict(lambda: {"count": 0, "value": 0.0})
    for s in subs:
        if s.created_at and cur_start <= s.created_at < cur_end and s.status != "cancelled":
            row = pl[s.plan.name if s.plan else "Package"]
            row["count"] += 1
            row["value"] += float(s.price_paid or 0)
    top_plans = sorted(({"name": k, "count": v["count"], "value": round(v["value"], 2)} for k, v in pl.items()),
                       key=lambda r: (-r["count"], -r["value"]))[:5]

    recent = db.query(models.Payment).order_by(models.Payment.paid_at.desc(), models.Payment.id.desc()).limit(6).all()

    def pay_label(p):
        if p.subscription_id and p.subscription and p.subscription.plan:
            return p.subscription.plan.name
        if p.appointment_id and p.appointment and p.appointment.service:
            return p.appointment.service.name
        return p.notes or "Payment"

    return {
        "today": today.isoformat(),
        "compare_label": f"vs 1–{prev_span_end_day} {prev_m.strftime('%b')}",
        "kpis": {
            "revenue": _kpi(rev, rev_prev),
            "expenses": _kpi(exp, exp_prev),
            "profit": _kpi(round(rev - exp, 2), round(rev_prev - exp_prev, 2)),
            "active_clients": _kpi(ac, ac_prev),
            "sessions": {**_kpi(ses, ses_prev), "today": int(sessions_today)},
        },
        "months": [months[p] for p in periods],
        "packages": {"active": len(active), "expiring": len(expiring), "ended": ended},
        "expiring_list": [{"id": s.id, "client_id": s.client_id, "client_name": s.client.name if s.client else "",
                           "plan": s.plan.name if s.plan else "", "remaining": s.sessions_remaining,
                           "end_date": s.end_date.isoformat() if s.end_date else None} for s in expiring[:5]],
        "sessions_remaining": int(sessions_remaining),
        "due": {"count": len(unpaid), "amount": round(float(sum(a.balance_due for a in unpaid)), 2)},
        "top_services": top_services,
        "top_plans": top_plans,
        "recent_payments": [{"id": p.id, "client_name": p.client.name if p.client else "", "label": pay_label(p),
                             "amount": float(p.amount), "method": p.method, "paid_at": p.paid_at.isoformat()} for p in recent],
    }


@router.get("/", response_model=schemas.DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    settings = get_settings(db)
    tz = settings.timezone
    now = utcnow()
    today = local_today(tz)
    today_start, today_end = local_day_bounds(today, tz)
    week_start, _ = local_day_bounds(today - timedelta(days=today.weekday()), tz)
    week_end = week_start + timedelta(days=7)
    month_start, _ = local_day_bounds(today.replace(day=1), tz)

    def pay_sum(start, end=None):
        q = db.query(func.coalesce(func.sum(models.Payment.amount), 0.0)).filter(models.Payment.paid_at >= start)
        if end:
            q = q.filter(models.Payment.paid_at < end)
        return float(q.scalar() or 0)

    active = ("scheduled", "confirmed")
    total_clients = db.query(func.count(models.Client.id)).filter(models.Client.active == True).scalar() or 0
    new_clients = db.query(func.count(models.Client.id)).filter(models.Client.created_at >= month_start).scalar() or 0
    total_services = db.query(func.count(models.Service.id)).filter(models.Service.active == True).scalar() or 0
    upcoming_q = db.query(models.Appointment).filter(models.Appointment.start_time >= now,
                                                     models.Appointment.status.in_(active))
    upcoming_count = upcoming_q.count()
    unconfirmed = upcoming_q.filter(models.Appointment.status == "scheduled",
                                    models.Appointment.start_time < now + timedelta(hours=24)).count()
    today_appts = (db.query(models.Appointment).filter(models.Appointment.start_time >= today_start,
                                                       models.Appointment.start_time < today_end)
                   .order_by(models.Appointment.start_time).all())
    week_count = db.query(func.count(models.Appointment.id)).filter(models.Appointment.start_time >= week_start,
                                                                    models.Appointment.start_time < week_end,
                                                                    models.Appointment.status != "cancelled").scalar() or 0
    sessions_month = db.query(func.count(models.Appointment.id)).filter(models.Appointment.start_time >= month_start,
                                                                        models.Appointment.status == "completed").scalar() or 0
    unpaid = [a for a in db.query(models.Appointment).filter(models.Appointment.status == "completed").all() if a.balance_due > 0]
    subs = db.query(models.Subscription).filter(models.Subscription.status == "active").all()
    active_subs = [s for s in subs if s.sessions_remaining > 0 and (s.end_date is None or s.end_date >= now)]
    expiring = [s for s in active_subs if (s.end_date and s.end_date <= now + timedelta(days=settings.subscription_expiry_notice_days))
                or s.sessions_remaining <= settings.subscription_low_threshold]
    upcoming = upcoming_q.order_by(models.Appointment.start_time).limit(8).all()

    dismissed = _dismissed(settings)
    alerts = []
    if unconfirmed:
        alerts.append({"key": "unconfirmed", "level": "warning", "text": f"{unconfirmed} session(s) in the next 24h are not confirmed yet"})
    if unpaid:
        alerts.append({"key": "unpaid", "level": "serious", "text": f"{len(unpaid)} completed session(s) have unpaid balances", "link": "payments"})
    if expiring:
        alerts.append({"key": "packages", "level": "info", "text": f"{len(expiring)} package(s) are running low or expiring soon", "link": "subscriptions"})
    failed_since = max(now - timedelta(days=2), dismissed.get("failed_messages") or datetime.min)
    failed = db.query(func.count(models.NotificationLog.id)).filter(models.NotificationLog.status == "failed",
                                                                    models.NotificationLog.created_at > failed_since).scalar() or 0
    if failed:
        alerts.append({"key": "failed_messages", "level": "serious", "text": f"{failed} message(s) failed to send in the last 2 days", "link": "messages"})
    from backend.routers.devices import needing_service
    due = needing_service(db)
    if due:
        late = [d for d in due if d["service_state"] == "overdue"]
        alerts.append({"key": "devices", "level": "serious" if late else "warning",
                       "text": (f"{len(late)} device(s) are overdue for service" if late else f"{len(due)} device(s) are due for service soon")
                               + ": " + ", ".join(d["name"] for d in due[:3]), "link": "catalog"})
    held = db.query(func.count(models.NotificationLog.id)).filter(models.NotificationLog.status == "pending_approval").scalar() or 0
    if held:
        alerts.append({"key": "pending_messages", "level": "warning", "text": f"{held} message(s) are waiting for your approval before they are sent", "link": "messages"})
    if settings.demo_mode:
        alerts.append({"key": "demo_mode", "level": "info", "text": "Demo mode is on: messages are logged, not sent to clients", "link": "settings"})
    # Dismissed alerts stay hidden for a day (failed_messages instead only counts newer failures, handled above).
    alerts = [a for a in alerts if a["key"] == "failed_messages" or not dismissed.get(a["key"]) or dismissed[a["key"]] < now - timedelta(hours=24)]

    return schemas.DashboardStats(
        total_clients=total_clients, new_clients_this_month=new_clients, total_services=total_services,
        upcoming_appointments=upcoming_count, appointments_today=len(today_appts), appointments_this_week=week_count,
        unconfirmed_upcoming=unconfirmed, unpaid_count=len(unpaid), unpaid_amount=float(sum(a.balance_due for a in unpaid)),
        revenue_today=pay_sum(today_start, today_end), revenue_this_week=pay_sum(week_start, week_end),
        revenue_this_month=pay_sum(month_start), sessions_this_month=sessions_month,
        active_subscriptions=len(active_subs), subscriptions_expiring_soon=len(expiring),
        today_appointments=today_appts, upcoming=upcoming, alerts=alerts,
    )
