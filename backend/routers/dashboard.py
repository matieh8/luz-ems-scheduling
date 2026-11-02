from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def _week_bounds(d: datetime):
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    start = start - timedelta(days=start.weekday())
    end = start + timedelta(days=7)
    return start, end


@router.get("/", response_model=schemas.DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    week_start, week_end = _week_bounds(now)

    total_clients = db.query(func.count(models.Client.id)).scalar() or 0
    total_services = db.query(func.count(models.Service.id)).filter(models.Service.active == True).scalar() or 0
    upcoming_appointments = (
        db.query(func.count(models.Appointment.id))
        .filter(models.Appointment.start_time >= now)
        .filter(models.Appointment.status == "scheduled")
        .scalar() or 0
    )
    appointments_today = (
        db.query(func.count(models.Appointment.id))
        .filter(models.Appointment.start_time >= today_start)
        .filter(models.Appointment.start_time < today_end)
        .scalar() or 0
    )
    appointments_this_week = (
        db.query(func.count(models.Appointment.id))
        .filter(models.Appointment.start_time >= week_start)
        .filter(models.Appointment.start_time < week_end)
        .scalar() or 0
    )
    recent_appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.start_time >= now)
        .filter(models.Appointment.status == "scheduled")
        .order_by(models.Appointment.start_time)
        .limit(10)
        .all()
    )

    return schemas.DashboardStats(
        total_clients=total_clients,
        total_services=total_services,
        upcoming_appointments=upcoming_appointments,
        appointments_today=appointments_today,
        appointments_this_week=appointments_this_week,
        recent_appointments=recent_appointments,
    )


@router.get("/revenue", response_model=schemas.WeeklyRevenue)
def weekly_revenue(
    week_start: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    if week_start:
        start, end = _week_bounds(week_start)
    else:
        start, end = _week_bounds(now)

    appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.start_time >= start)
        .filter(models.Appointment.start_time < end)
        .all()
    )

    subscriptions = (
        db.query(models.Subscription)
        .filter(models.Subscription.created_at >= start)
        .filter(models.Subscription.created_at < end)
        .all()
    )

    appointments_revenue = 0.0
    by_service = {}
    for a in appointments:
        price = a.service.price or 0
        appointments_revenue += price
        by_service.setdefault(a.service.name, {"count": 0, "revenue": 0.0, "color": a.service.color})
        by_service[a.service.name]["count"] += 1
        by_service[a.service.name]["revenue"] += price

    subscriptions_revenue = sum(s.price_paid for s in subscriptions)

    return schemas.WeeklyRevenue(
        week_start=start.date().isoformat(),
        week_end=(end - timedelta(days=1)).date().isoformat(),
        appointments_revenue=appointments_revenue,
        subscriptions_revenue=subscriptions_revenue,
        total_revenue=appointments_revenue + subscriptions_revenue,
        appointment_count=len(appointments),
        subscription_count=len(subscriptions),
        by_service=[{"name": k, **v} for k, v in by_service.items()],
    )
