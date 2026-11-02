from typing import List
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.notifications import send_reminder
from backend import whatsapp_web_client

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/logs", response_model=List[schemas.NotificationLogResponse])
def list_logs(limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(models.NotificationLog)
        .order_by(models.NotificationLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/{appointment_id}/reminder", response_model=schemas.NotificationLogResponse)
def send_reminder_now(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    log = send_reminder(db, appointment)
    return log


@router.get("/whatsapp-status", response_model=Dict[str, Any])
def whatsapp_status():
    return whatsapp_web_client.get_status()
