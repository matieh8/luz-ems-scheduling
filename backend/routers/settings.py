from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
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
    for key, value in settings.model_dump(exclude_unset=True).items():
        setattr(db_settings, key, value)
    db.commit()
    db.refresh(db_settings)
    return db_settings
