import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.scheduling import get_settings
from backend.tz import local_day_bounds, local_today, utcnow

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
