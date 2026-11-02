from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas, notifications
from backend.tz import to_utc_naive, utcnow

router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=List[schemas.SubscriptionPlanResponse])
def list_plans(active_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.SubscriptionPlan)
    if active_only:
        query = query.filter(models.SubscriptionPlan.active == True)
    return query.order_by(models.SubscriptionPlan.price).all()


@router.post("/plans", response_model=schemas.SubscriptionPlanResponse)
def create_plan(plan: schemas.SubscriptionPlanCreate, db: Session = Depends(get_db)):
    db_plan = models.SubscriptionPlan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.put("/plans/{plan_id}", response_model=schemas.SubscriptionPlanResponse)
def update_plan(plan_id: int, plan: schemas.SubscriptionPlanUpdate, db: Session = Depends(get_db)):
    db_plan = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.id == plan_id).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    for key, value in plan.model_dump(exclude_unset=True).items():
        setattr(db_plan, key, value)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    db_plan = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.id == plan_id).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if db_plan.subscriptions:
        db_plan.active = False
        db.commit()
        return {"detail": "Plan has been sold, so it was deactivated instead of deleted"}
    db.delete(db_plan)
    db.commit()
    return {"detail": "Plan deleted"}


@router.get("/", response_model=List[schemas.SubscriptionResponse])
def list_subscriptions(client_id: Optional[int] = None, status: Optional[str] = None,
                       active: Optional[bool] = None, db: Session = Depends(get_db)):
    query = db.query(models.Subscription)
    if client_id:
        query = query.filter(models.Subscription.client_id == client_id)
    if status:
        query = query.filter(models.Subscription.status == status)
    rows = query.order_by(models.Subscription.created_at.desc()).all()
    if active is not None:
        now = utcnow()
        def is_active(s):
            return s.status == "active" and (s.end_date is None or s.end_date >= now) and s.sessions_remaining > 0
        rows = [s for s in rows if is_active(s) == active]
    return rows


@router.post("/", response_model=schemas.SubscriptionResponse)
def create_subscription(sub: schemas.SubscriptionCreate, db: Session = Depends(get_db)):
    plan = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.id == sub.plan_id).first()
    if not plan:
        raise HTTPException(status_code=400, detail="Plan not found")
    client = db.query(models.Client).filter(models.Client.id == sub.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found")

    start = to_utc_naive(sub.start_date) if sub.start_date else utcnow()
    end = to_utc_naive(sub.end_date) if sub.end_date else (start + timedelta(days=plan.duration_days) if plan.duration_days else None)
    sessions_total = sub.sessions_total or plan.sessions_included
    price_paid = sub.price_paid if sub.price_paid is not None else plan.price

    db_sub = models.Subscription(
        client_id=sub.client_id, plan_id=sub.plan_id, start_date=start, end_date=end,
        sessions_total=sessions_total, sessions_used=sub.sessions_used, price_paid=price_paid,
        status=sub.status, notes=sub.notes,
    )
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    if sub.record_payment and price_paid > 0:
        db.add(models.Payment(client_id=client.id, subscription_id=db_sub.id, amount=price_paid,
                              method=sub.payment_method or "cash", paid_at=utcnow(), notes=f"{plan.name}"))
        db.commit()
        db.refresh(db_sub)
    if sub.send_notification:
        try:
            notifications.send_subscription_purchase(db, db_sub)
        except Exception as e:
            print(f"[notify] subscription purchase failed: {e}")
    return db_sub


@router.put("/{subscription_id}", response_model=schemas.SubscriptionResponse)
def update_subscription(subscription_id: int, sub: schemas.SubscriptionUpdate, db: Session = Depends(get_db)):
    db_sub = db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    data = sub.model_dump(exclude_unset=True)
    for k in ("start_date", "end_date"):
        if data.get(k) is not None:
            data[k] = to_utc_naive(data[k])
    for key, value in data.items():
        setattr(db_sub, key, value)
    db.commit()
    db.refresh(db_sub)
    return db_sub


@router.delete("/{subscription_id}")
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    db_sub = db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    for a in db_sub.appointments:
        a.subscription_id = None
    for p in db_sub.payments:
        p.subscription_id = None
    db.delete(db_sub)
    db.commit()
    return {"detail": "Subscription deleted"}
