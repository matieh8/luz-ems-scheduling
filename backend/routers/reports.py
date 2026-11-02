"""Revenue and performance reports. Date params are local (business timezone) calendar dates, inclusive."""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models
from backend.scheduling import get_settings
from backend.tz import local_day_bounds, local_today, to_local

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _range(db, from_date: Optional[date], to_date: Optional[date]):
    settings = get_settings(db)
    tz = settings.timezone
    today = local_today(tz)
    if not to_date:
        to_date = today
    if not from_date:
        from_date = to_date - timedelta(days=29)
    start, _ = local_day_bounds(from_date, tz)
    _, end = local_day_bounds(to_date, tz)
    return settings, tz, from_date, to_date, start, end


def _session_value(a: models.Appointment) -> float:
    """What a delivered session is worth: its price, or its share of the package price."""
    if a.subscription_id and a.subscription and a.subscription.sessions_total:
        return float(a.subscription.price_paid) / a.subscription.sessions_total
    return float(a.price or 0)


@router.get("/summary")
def summary(from_date: Optional[date] = Query(None, alias="from"), to_date: Optional[date] = Query(None, alias="to"),
            db: Session = Depends(get_db)):
    settings, tz, f, t, start, end = _range(db, from_date, to_date)
    payments = db.query(models.Payment).filter(models.Payment.paid_at >= start, models.Payment.paid_at < end).all()
    appts = db.query(models.Appointment).filter(models.Appointment.start_time >= start,
                                                models.Appointment.start_time < end).all()
    subs = db.query(models.Subscription).filter(models.Subscription.created_at >= start,
                                                models.Subscription.created_at < end).all()
    new_clients = db.query(models.Client).filter(models.Client.created_at >= start, models.Client.created_at < end).count()

    by_method = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for p in payments:
        by_method[p.method]["amount"] += p.amount
        by_method[p.method]["count"] += 1
    collected = sum(p.amount for p in payments)
    collected_sessions = sum(p.amount for p in payments if p.appointment_id)
    collected_packages = sum(p.amount for p in payments if p.subscription_id)
    collected_other = collected - collected_sessions - collected_packages

    completed = [a for a in appts if a.status == "completed"]
    by_service = defaultdict(lambda: {"count": 0, "value": 0.0, "color": "#999"})
    by_staff = defaultdict(lambda: {"count": 0, "value": 0.0, "color": "#999"})
    for a in completed:
        v = _session_value(a)
        s = by_service[a.service.name]
        s["count"] += 1; s["value"] += v; s["color"] = a.service.color
        name = a.staff.name if a.staff else "Unassigned"
        st = by_staff[name]
        st["count"] += 1; st["value"] += v; st["color"] = a.staff.color if a.staff else "#94a3b8"

    status_counts = defaultdict(int)
    for a in appts:
        status_counts[a.status] += 1

    # Outstanding balances are all-time, not range-bound: money still owed today
    unpaid = [a for a in db.query(models.Appointment).filter(models.Appointment.status == "completed").all() if a.balance_due > 0]
    outstanding = sum(a.balance_due for a in unpaid)

    session_value = sum(_session_value(a) for a in completed)
    days = (t - f).days + 1
    return {
        "from": f.isoformat(), "to": t.isoformat(), "days": days, "currency": settings.currency,
        "collected": collected, "collected_sessions": collected_sessions, "collected_packages": collected_packages,
        "collected_other": collected_other, "payments_count": len(payments),
        "by_method": [{"method": k, **v} for k, v in sorted(by_method.items(), key=lambda kv: -kv[1]["amount"])],
        "sessions_completed": len(completed), "session_value": session_value,
        "avg_session_value": (session_value / len(completed)) if completed else 0.0,
        "sessions_from_packages": len([a for a in completed if a.subscription_id]),
        "by_service": [{"name": k, **v} for k, v in sorted(by_service.items(), key=lambda kv: -kv[1]["value"])],
        "by_staff": [{"name": k, **v} for k, v in sorted(by_staff.items(), key=lambda kv: -kv[1]["value"])],
        "status_counts": dict(status_counts),
        "cancellation_rate": (status_counts["cancelled"] / len(appts)) if appts else 0.0,
        "no_show_rate": (status_counts["no_show"] / len(appts)) if appts else 0.0,
        "packages_sold": len(subs), "packages_value": sum(s.price_paid for s in subs),
        "new_clients": new_clients,
        "outstanding": outstanding, "outstanding_count": len(unpaid),
    }


@router.get("/timeseries")
def timeseries(from_date: Optional[date] = Query(None, alias="from"), to_date: Optional[date] = Query(None, alias="to"),
               granularity: str = "day", db: Session = Depends(get_db)):
    settings, tz, f, t, start, end = _range(db, from_date, to_date)
    payments = db.query(models.Payment).filter(models.Payment.paid_at >= start, models.Payment.paid_at < end).all()
    appts = db.query(models.Appointment).filter(models.Appointment.start_time >= start,
                                                models.Appointment.start_time < end,
                                                models.Appointment.status == "completed").all()

    def bucket(dt: datetime) -> str:
        d = to_local(dt, tz).date()
        if granularity == "month":
            return d.strftime("%Y-%m")
        if granularity == "week":
            return (d - timedelta(days=d.weekday())).isoformat()
        return d.isoformat()

    # Build all buckets in range so the chart has no gaps
    buckets = []
    d = f
    while d <= t:
        key = bucket(datetime(d.year, d.month, d.day, 12) - timedelta(hours=to_local(datetime.utcnow(), tz).utcoffset().total_seconds() / 3600))
        if not buckets or buckets[-1] != key:
            buckets.append(key)
        d += timedelta(days=1)
    series = {k: {"period": k, "collected": 0.0, "sessions": 0, "session_value": 0.0, "packages": 0.0} for k in buckets}
    for p in payments:
        k = bucket(p.paid_at)
        if k in series:
            series[k]["collected"] += p.amount
            if p.subscription_id:
                series[k]["packages"] += p.amount
    for a in appts:
        k = bucket(a.start_time)
        if k in series:
            series[k]["sessions"] += 1
            series[k]["session_value"] += _session_value(a)
    return {"granularity": granularity, "currency": settings.currency, "points": list(series.values())}


@router.get("/top-clients")
def top_clients(from_date: Optional[date] = Query(None, alias="from"), to_date: Optional[date] = Query(None, alias="to"),
                limit: int = 10, db: Session = Depends(get_db)):
    settings, tz, f, t, start, end = _range(db, from_date, to_date)
    payments = db.query(models.Payment).filter(models.Payment.paid_at >= start, models.Payment.paid_at < end).all()
    appts = db.query(models.Appointment).filter(models.Appointment.start_time >= start,
                                                models.Appointment.start_time < end,
                                                models.Appointment.status == "completed").all()
    agg = {}
    for p in payments:
        a = agg.setdefault(p.client_id, {"client_id": p.client_id, "name": p.client.name, "phone": p.client.phone,
                                         "spent": 0.0, "sessions": 0})
        a["spent"] += p.amount
    for ap in appts:
        a = agg.setdefault(ap.client_id, {"client_id": ap.client_id, "name": ap.client.name, "phone": ap.client.phone,
                                          "spent": 0.0, "sessions": 0})
        a["sessions"] += 1
    rows = sorted(agg.values(), key=lambda r: (-r["spent"], -r["sessions"]))[:limit]
    return {"currency": settings.currency, "clients": rows}


def _csv_response(rows, header, filename):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/export/payments.csv")
def export_payments(from_date: Optional[date] = Query(None, alias="from"), to_date: Optional[date] = Query(None, alias="to"),
                    db: Session = Depends(get_db)):
    settings, tz, f, t, start, end = _range(db, from_date, to_date)
    payments = db.query(models.Payment).filter(models.Payment.paid_at >= start, models.Payment.paid_at < end)\
        .order_by(models.Payment.paid_at).all()
    rows = [[to_local(p.paid_at, tz).strftime("%Y-%m-%d %H:%M"), p.client.name, p.client.phone, p.amount, p.method,
             "session" if p.appointment_id else ("package" if p.subscription_id else "other"), p.notes or ""]
            for p in payments]
    return _csv_response(rows, ["Date", "Client", "Phone", f"Amount ({settings.currency})", "Method", "For", "Notes"],
                         f"payments_{f}_{t}.csv")


@router.get("/export/appointments.csv")
def export_appointments(from_date: Optional[date] = Query(None, alias="from"), to_date: Optional[date] = Query(None, alias="to"),
                        db: Session = Depends(get_db)):
    settings, tz, f, t, start, end = _range(db, from_date, to_date)
    appts = db.query(models.Appointment).filter(models.Appointment.start_time >= start,
                                                models.Appointment.start_time < end).order_by(models.Appointment.start_time).all()
    rows = [[to_local(a.start_time, tz).strftime("%Y-%m-%d %H:%M"), a.client.name, a.client.phone, a.service.name,
             a.staff.name if a.staff else "", a.status, a.price, a.paid_amount, a.balance_due,
             "yes" if a.subscription_id else "no", a.source, a.notes or ""] for a in appts]
    return _csv_response(rows, ["Start", "Client", "Phone", "Service", "Trainer", "Status", "Price", "Paid", "Balance",
                                "Package", "Source", "Notes"], f"appointments_{f}_{t}.csv")
