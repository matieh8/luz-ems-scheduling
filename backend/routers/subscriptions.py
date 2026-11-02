from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas

router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=List[schemas.SubscriptionPlanResponse])
def list_plans(active_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.SubscriptionPlan)
    if active_only:
        query = query.filter(models.SubscriptionPlan.active == True)
    return query.order_by(models.SubscriptionPlan.name).all()


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
    db.delete(db_plan)
    db.commit()
    return {"detail": "Plan deleted"}


@router.get("/", response_model=List[schemas.SubscriptionResponse])
def list_subscriptions(
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Subscription)
    if client_id:
        query = query.filter(models.Subscription.client_id == client_id)
    if status:
        query = query.filter(models.Subscription.status == status)
    if active is not None:
        now = datetime.utcnow()
        if active:
            query = query.filter(
                (models.Subscription.status == "active") &
                ((models.Subscription.end_date.is_(None)) | (models.Subscription.end_date >= now)) &
                (models.Subscription.sessions_used < models.Subscription.sessions_total)
            )
        else:
            query = query.filter(
                (models.Subscription.status != "active") |
                ((models.Subscription.end_date.isnot(None)) & (models.Subscription.end_date < now)) |
                (models.Subscription.sessions_used >= models.Subscription.sessions_total)
            )
    return query.order_by(models.Subscription.created_at.desc()).all()


@router.post("/", response_model=schemas.SubscriptionResponse)
def create_subscription(sub: schemas.SubscriptionCreate, db: Session = Depends(get_db)):
    plan = db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.id == sub.plan_id).first()
    if not plan:
        raise HTTPException(status_code=400, detail="Plan not found")
    client = db.query(models.Client).filter(models.Client.id == sub.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found")

    end_date = sub.end_date
    if not end_date and plan.duration_days:
        end_date = sub.start_date + timedelta(days=plan.duration_days)

    sessions_total = sub.sessions_total if sub.sessions_total else plan.sessions_included
    price_paid = sub.price_paid if sub.price_paid else plan.price

    db_sub = models.Subscription(
        client_id=sub.client_id,
        plan_id=sub.plan_id,
        start_date=sub.start_date,
        end_date=end_date,
        sessions_total=sessions_total,
        sessions_used=sub.sessions_used,
        price_paid=price_paid,
        status=sub.status,
        notes=sub.notes,
    )
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    return db_sub


@router.put("/{subscription_id}", response_model=schemas.SubscriptionResponse)
def update_subscription(subscription_id: int, sub: schemas.SubscriptionUpdate, db: Session = Depends(get_db)):
    db_sub = db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    for key, value in sub.model_dump(exclude_unset=True).items():
        setattr(db_sub, key, value)
    db.commit()
    db.refresh(db_sub)
    return db_sub


@router.delete("/{subscription_id}")
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    db_sub = db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete(db_sub)
    db.commit()
    return {"detail": "Subscription deleted"}
