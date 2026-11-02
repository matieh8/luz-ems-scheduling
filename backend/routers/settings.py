from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo
from backend.database import get_db
from backend import models, schemas

router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _get_or_create_settings(db: Session):
    settings = db.query(models.Setting).first()
    if not settings:
        settings = models.Setting()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/", response_model=schemas.SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    return _get_or_create_settings(db)


@router.put("/", response_model=schemas.SettingsResponse)
def update_settings(settings: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    db_settings = _get_or_create_settings(db)
    data = settings.model_dump(exclude_unset=True)
    if data.get("timezone"):
        try:
            ZoneInfo(data["timezone"])
        except Exception:
            raise HTTPException(status_code=400, detail="Unknown timezone")
    for key, value in data.items():
        setattr(db_settings, key, value)
    db.commit()
    db.refresh(db_settings)
    return db_settings


@router.get("/hours", response_model=List[schemas.BusinessHoursItem])
def get_hours(db: Session = Depends(get_db)):
    return db.query(models.BusinessHours).order_by(models.BusinessHours.day_of_week).all()


@router.put("/hours", response_model=List[schemas.BusinessHoursItem])
def update_hours(items: List[schemas.BusinessHoursItem], db: Session = Depends(get_db)):
    for item in items:
        row = db.query(models.BusinessHours).filter(models.BusinessHours.day_of_week == item.day_of_week).first()
        if not row:
            row = models.BusinessHours(day_of_week=item.day_of_week)
            db.add(row)
        row.open_time, row.close_time, row.closed = item.open_time, item.close_time, item.closed
    db.commit()
    return db.query(models.BusinessHours).order_by(models.BusinessHours.day_of_week).all()
