"""Revenue and performance reports. Date params are local (business timezone) calendar dates, inclusive."""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models
from backend.scheduling import get_settings
from backend.tz import local_day_bounds, local_today, to_local
from backend.tz import now_utc

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


EXPENSE_GROUPS = [
    ("Fuel & transport", ("fuel", "transport", "petrol", "taxi", "parking", "salik", "car", "travel")),
    ("Maintenance & equipment", ("maintenance", "repair", "equipment", "device", "machine", "suit")),
    ("Marketing", ("marketing", "ads", "advert", "instagram", "promotion", "printing")),
    ("Staff", ("salar", "wage", "commission", "staff", "bonus")),
    ("Premises & utilities", ("rent", "electric", "water", "internet", "phone", "utilit", "cleaning", "dewa")),
    ("Software & subscriptions", ("subscription", "software", "app")),
]


def expense_group(category: str) -> str:
    c = (category or "").lower()
    for name, words in EXPENSE_GROUPS:
        if any(w in c for w in words):
            return name
    return "Other"


def _month_start(d: date, back: int = 0) -> date:
    y, m = d.year, d.month - back
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


@router.get("/finance")
def finance(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    """Cash flow, revenue per client and estimated profit per service and package over the last N months.

    Cash flow uses money that actually moved: payments received and expenses marked paid.
    Profit per service/package is an estimate: every delivered session carries an equal share of all expenses
    (cost per session = expenses / sessions delivered in the period)."""
    settings = get_settings(db)
    tz = settings.timezone
    today = local_today(tz)
    periods = [_month_start(today, i).strftime("%Y-%m") for i in range(months - 1, -1, -1)]
    start, _ = local_day_bounds(_month_start(today, months - 1), tz)
    _, end = local_day_bounds(today, tz)
    key = lambda dt: to_local(dt, tz).strftime("%Y-%m")

    pays = db.query(models.Payment).filter(models.Payment.paid_at >= start, models.Payment.paid_at < end).all()
    exps = db.query(models.Expense).filter(models.Expense.date >= start, models.Expense.date < end).all()
    done = db.query(models.Appointment).filter(models.Appointment.start_time >= start, models.Appointment.start_time < end,
                                               models.Appointment.status == "completed").all()
    subs = db.query(models.Subscription).filter(models.Subscription.created_at >= start, models.Subscription.created_at < end,
                                                models.Subscription.status != "cancelled").all()

    # 42 Cash flow
    flow = {p: {"period": p, "money_in": 0.0, "money_out": 0.0} for p in periods}
    for p in pays:
        if key(p.paid_at) in flow:
            flow[key(p.paid_at)]["money_in"] += float(p.amount)
    for e in exps:
        if e.paid and key(e.date) in flow:
            flow[key(e.date)]["money_out"] += float(e.amount)
    balance, rows = 0.0, []
    for p in periods:
        r = flow[p]
        r["money_in"], r["money_out"] = round(r["money_in"], 2), round(r["money_out"], 2)
        r["net"] = round(r["money_in"] - r["money_out"], 2)
        balance = round(balance + r["net"], 2)
        r["balance"] = balance
        rows.append(r)
    owed_sessions = sum(a.balance_due for a in db.query(models.Appointment).filter(models.Appointment.status == "completed").all())
    owed_packages = sum(max(float(s.price_paid or 0) - s.paid_amount, 0) for s in db.query(models.Subscription).filter(models.Subscription.status != "cancelled").all())
    bills = sum(float(e.amount) for e in db.query(models.Expense).filter(models.Expense.paid == False).all())  # noqa: E712

    # 43 Revenue per client
    revenue = sum(float(p.amount) for p in pays)
    by_client = defaultdict(float)
    for p in pays:
        by_client[p.client_id] += float(p.amount)
    all_time = db.query(models.Payment.client_id, func.sum(models.Payment.amount)).group_by(models.Payment.client_id).all()
    lifetime = [float(t or 0) for _, t in all_time if t]

    # 44 Estimated profit per service / package
    expenses_total = sum(float(e.amount) for e in exps)
    cost_per_session = round(expenses_total / len(done), 2) if done else 0.0
    svc = defaultdict(lambda: {"sessions": 0, "revenue": 0.0})
    for a in done:
        r = svc[a.service.name if a.service else "Other"]
        r["sessions"] += 1
        r["revenue"] += _session_value(a)
    services = []
    for name, r in svc.items():
        cost = round(r["sessions"] * cost_per_session, 2)
        rev = round(r["revenue"], 2)
        services.append({"name": name, "sessions": r["sessions"], "revenue": rev, "avg_price": round(rev / r["sessions"], 2),
                         "est_cost": cost, "est_profit": round(rev - cost, 2), "margin_pct": round((rev - cost) / rev * 100, 1) if rev else None})
    services.sort(key=lambda r: -r["est_profit"])
    pl = defaultdict(lambda: {"sold": 0, "revenue": 0.0, "sessions": 0})
    for s in subs:
        r = pl[s.plan.name if s.plan else "Package"]
        r["sold"] += 1
        r["revenue"] += float(s.price_paid or 0)
        r["sessions"] += int(s.sessions_total or 0)
    plans = []
    for name, r in pl.items():
        cost = round(r["sessions"] * cost_per_session, 2)
        rev = round(r["revenue"], 2)
        plans.append({"name": name, "sold": r["sold"], "revenue": rev, "sessions_sold": r["sessions"],
                      "price_per_session": round(rev / r["sessions"], 2) if r["sessions"] else None,
                      "est_cost": cost, "est_profit": round(rev - cost, 2), "margin_pct": round((rev - cost) / rev * 100, 1) if rev else None})
    plans.sort(key=lambda r: -r["est_profit"])

    # 45 Expenses by business group
    groups = defaultdict(float)
    for e in exps:
        groups[expense_group(e.category)] += float(e.amount)

    return {
        "from": _month_start(today, months - 1).isoformat(), "to": today.isoformat(),
        "months": rows,
        "outstanding": {"owed_to_you": round(owed_sessions + owed_packages, 2), "owed_sessions": round(owed_sessions, 2),
                        "owed_packages": round(owed_packages, 2), "bills_to_pay": round(bills, 2)},
        "per_client": {"paying_clients": len(by_client), "revenue": round(revenue, 2),
                       "avg_per_client": round(revenue / len(by_client), 2) if by_client else 0.0,
                       "avg_per_client_per_month": round(revenue / len(by_client) / months, 2) if by_client else 0.0,
                       "avg_lifetime_value": round(sum(lifetime) / len(lifetime), 2) if lifetime else 0.0},
        "costs": {"expenses_total": round(expenses_total, 2), "sessions_delivered": len(done), "cost_per_session": cost_per_session},
        "services": services, "plans": plans,
        "expense_groups": sorted(({"group": g, "total": round(t, 2)} for g, t in groups.items()), key=lambda r: -r["total"]),
    }


@router.get("/staff")
def staff_report(from_date: Optional[date] = Query(None, alias="from"), to_date: Optional[date] = Query(None, alias="to"),
                 db: Session = Depends(get_db)):
    """Per trainer: sessions done, no-shows, cancellations, clients, value delivered, late arrivals and commission due."""
    settings, tz, from_date, to_date, start, end = _range(db, from_date, to_date)
    appts = db.query(models.Appointment).filter(models.Appointment.start_time >= start, models.Appointment.start_time < end,
                                                models.Appointment.staff_id.isnot(None)).all()
    rows = {}
    for s in db.query(models.Staff).all():
        rows[s.id] = {"staff_id": s.id, "name": s.name, "color": s.color, "active": s.active, "completed": 0, "no_show": 0,
                      "cancelled": 0, "late": 0, "value": 0.0, "clients": set(),
                      "commission_type": s.commission_type or "none", "commission_value": s.commission_value or 0}
    for a in appts:
        r = rows.get(a.staff_id)
        if not r:
            continue
        if a.status == "completed":
            r["completed"] += 1
            r["value"] += _session_value(a)
            r["clients"].add(a.client_id)
            if (a.late_minutes or 0) > 0:
                r["late"] += 1
        elif a.status == "no_show":
            r["no_show"] += 1
        elif a.status == "cancelled":
            r["cancelled"] += 1
    out = []
    for r in rows.values():
        if not (r["completed"] or r["no_show"] or r["cancelled"]) and not r["active"]:
            continue
        kind, v = r["commission_type"], float(r["commission_value"] or 0)
        commission = r["value"] * v / 100 if kind == "percent" else r["completed"] * v if kind == "per_session" else 0.0
        booked = r["completed"] + r["no_show"]
        out.append({**r, "clients": len(r["clients"]), "value": round(r["value"], 2), "commission": round(commission, 2),
                    "show_rate": round(r["completed"] / booked * 100, 1) if booked else None,
                    "avg_value": round(r["value"] / r["completed"], 2) if r["completed"] else 0.0})
    out.sort(key=lambda r: -r["value"])
    return {"from": from_date.isoformat(), "to": to_date.isoformat(), "staff": out,
            "total_commission": round(sum(r["commission"] for r in out), 2)}


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
    unpaid = models.unpaid_sessions(db)
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
        key = bucket(datetime(d.year, d.month, d.day, 12) - timedelta(hours=to_local(now_utc(), tz).utcoffset().total_seconds() / 3600))
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
