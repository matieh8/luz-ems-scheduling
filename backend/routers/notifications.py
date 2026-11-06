from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas, notifications, whatsapp_web_client

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/logs", response_model=List[schemas.NotificationLogResponse])
def list_logs(limit: int = 100, status: Optional[str] = None, channel: Optional[str] = None,
              type: Optional[str] = None, client_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.NotificationLog)
    if status:
        q = q.filter(models.NotificationLog.status == status)
    if channel:
        q = q.filter(models.NotificationLog.channel == channel)
    if type:
        q = q.filter(models.NotificationLog.type == type)
    if client_id:
        q = q.filter(models.NotificationLog.client_id == client_id)
    return q.order_by(models.NotificationLog.created_at.desc()).limit(limit).all()


@router.post("/{appointment_id}/reminder", response_model=List[schemas.NotificationLogResponse])
def send_reminder_now(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return notifications.send_reminder(db, appointment)


@router.post("/{appointment_id}/confirmation", response_model=List[schemas.NotificationLogResponse])
def resend_confirmation(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return notifications.send_booking_confirmation(db, appointment)


@router.post("/logs/{log_id}/retry", response_model=schemas.NotificationLogResponse)
def retry(log_id: int, db: Session = Depends(get_db)):
    log = db.query(models.NotificationLog).filter(models.NotificationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    log.status = "queued"
    log.external_response = None
    db.commit()
    settings = notifications.get_settings(db)
    if settings.demo_mode:
        log.status = "sent"
        log.external_response = "DEMO MODE: retried, logged not sent"
        db.commit()
    else:
        notifications._deliver(log.id)
        db.refresh(log)
    return log


@router.post("/custom", response_model=List[schemas.NotificationLogResponse])
def send_custom(body: schemas.CustomMessage, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == body.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    ctx = notifications.build_context(db, client)
    rendered = body.body.format_map(notifications._SafeDict(ctx))
    return notifications.send(db, "custom", client, raw_body=rendered, raw_subject=body.subject, channels=body.channels)


@router.get("/templates", response_model=List[schemas.MessageTemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    notifications.ensure_templates(db)
    return db.query(models.MessageTemplate).order_by(models.MessageTemplate.id).all()


@router.get("/templates/placeholders")
def placeholders():
    return {"placeholders": notifications.PLACEHOLDERS}


@router.put("/templates/{key}", response_model=schemas.MessageTemplateResponse)
def update_template(key: str, body: schemas.MessageTemplateUpdate, db: Session = Depends(get_db)):
    t = db.query(models.MessageTemplate).filter(models.MessageTemplate.key == key).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.post("/templates/{key}/reset", response_model=schemas.MessageTemplateResponse)
def reset_template(key: str, db: Session = Depends(get_db)):
    t = db.query(models.MessageTemplate).filter(models.MessageTemplate.key == key).first()
    if not t or key not in notifications.DEFAULT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    t.subject = notifications.DEFAULT_TEMPLATES[key]["subject"]
    t.body = notifications.DEFAULT_TEMPLATES[key]["body"]
    db.commit()
    db.refresh(t)
    return t


@router.post("/templates/{key}/preview")
def preview_template(key: str, db: Session = Depends(get_db)):
    appt = db.query(models.Appointment).order_by(models.Appointment.id.desc()).first()
    sub = db.query(models.Subscription).order_by(models.Subscription.id.desc()).first()
    client = appt.client if appt else (sub.client if sub else models.Client(name="Sarah Ahmed", phone="0501234567"))
    ctx = notifications.build_context(db, client, appt, sub)
    subject, body = notifications.render(db, key, ctx)
    return {"subject": subject, "body": body}


@router.get("/whatsapp-status", response_model=Dict[str, Any])
def whatsapp_status():
    st = whatsapp_web_client.get_status()
    if st.get("status") == "bridge_offline":
        from backend.main import BRIDGE_REASON
        st["reason"] = BRIDGE_REASON.get("reason") or "bridge process is not running (check the server log)"
    return st


@router.post("/whatsapp-reset")
def whatsapp_reset():
    return whatsapp_web_client.reset_bridge()


@router.post("/run-jobs")
def run_jobs_now(db: Session = Depends(get_db)):
    notifications.run_all_jobs(db)
    notifications.run_subscription_job(db)
    return {"detail": "Jobs executed"}
