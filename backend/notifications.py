import os
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend import models


def _get_settings(db: Session):
    settings = db.query(models.Setting).first()
    if not settings:
        settings = models.Setting()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("0") and len(digits) >= 9:
        digits = "971" + digits[1:]
    elif digits.startswith("5") and len(digits) == 9:
        digits = "971" + digits
    elif len(digits) == 10 and digits.startswith("05"):
        digits = "971" + digits[1:]
    return digits


def _send_whatsapp_message(
    db: Session,
    appointment: models.Appointment,
    message_type: str,
    body: str,
) -> models.NotificationLog:
    settings = _get_settings(db)
    to_phone = _normalize_phone(appointment.client.phone)

    log = models.NotificationLog(
        appointment_id=appointment.id,
        type=message_type,
        channel="whatsapp",
        status="queued",
        content=body,
    )
    db.add(log)
    db.commit()

    provider = settings.whatsapp_provider if settings.whatsapp_provider else "demo"

    if provider == "demo" or settings.demo_mode:
        log.status = "sent"
        log.external_response = f"DEMO_MODE ({provider}): message logged, not sent"
        db.commit()
        # Also append to a local demo log file for easy review
        demo_log_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "demo_messages.log"
        )
        try:
            with open(demo_log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Time: {datetime.utcnow().isoformat()} UTC\n")
                f.write(f"To: +{to_phone}\n")
                f.write(f"Provider: {provider}\n")
                f.write(f"Type: {message_type}\n")
                f.write(f"Body:\n{body}\n")
        except Exception:
            pass
        return log

    if not settings.whatsapp_enabled:
        log.status = "failed"
        log.external_response = "WhatsApp not enabled in settings"
        db.commit()
        return log

    if provider == "whatsapp_web":
        try:
            from backend import whatsapp_web_client
            resp = whatsapp_web_client.send_message(to_phone, body)
            log.status = "sent"
            log.external_response = f"whatsapp_web: {resp}"
        except Exception as e:
            log.status = "failed"
            log.external_response = f"whatsapp_web: {str(e)}"
        db.commit()
        return log

    # Default: Twilio
    try:
        from twilio.rest import Client

        if not all([
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            settings.twilio_phone_number,
        ]):
            raise ValueError("Twilio credentials incomplete")

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        twilio_msg = client.messages.create(
            from_=f"whatsapp:{settings.twilio_phone_number}",
            body=body,
            to=f"whatsapp:+{to_phone}",
        )
        log.status = "sent" if twilio_msg.status not in ("failed", "undelivered") else "failed"
        log.external_response = f"twilio: sid={twilio_msg.sid}; status={twilio_msg.status}"
    except Exception as e:
        log.status = "failed"
        log.external_response = f"twilio: {str(e)}"

    db.commit()
    return log


def _format_datetime(dt: datetime) -> str:
    return dt.strftime("%A, %d %B %Y at %I:%M %p")


def send_booking_confirmation(db: Session, appointment: models.Appointment) -> models.NotificationLog:
    settings = _get_settings(db)
    body = (
        f"Hi {appointment.client.name},\n\n"
        f"Your {appointment.service.name} session at *{settings.business_name}* is confirmed.\n\n"
        f"📅 Date & Time: {_format_datetime(appointment.start_time)}\n"
        f"⏱ Duration: {appointment.service.duration_minutes} minutes\n"
    )
    if appointment.service.price:
        body += f"💰 Price: AED {appointment.service.price:.2f}\n"
    body += (
        f"\nYou'll receive a reminder {settings.reminder_hours_before} hours before your session.\n\n"
        f"See you soon!\n{settings.business_name}"
    )
    return _send_whatsapp_message(db, appointment, "booking_confirmation", body)


def send_reminder(db: Session, appointment: models.Appointment) -> models.NotificationLog:
    settings = _get_settings(db)
    body = (
        f"Hi {appointment.client.name},\n\n"
        f"⏰ Reminder: You have a *{appointment.service.name}* session at *{settings.business_name}* "
        f"in {settings.reminder_hours_before} hours.\n\n"
        f"📅 {_format_datetime(appointment.start_time)}\n"
        f"⏱ {appointment.service.duration_minutes} minutes\n\n"
        f"See you soon!"
    )
    log = _send_whatsapp_message(db, appointment, "reminder", body)
    if log.status in ("sent",):
        appointment.reminder_sent_at = datetime.utcnow()
        db.commit()
    return log


def run_reminder_job(db: Session):
    settings = _get_settings(db)
    if settings.reminder_hours_before <= 0:
        return

    now = datetime.utcnow()
    window_start = now
    window_end = now + timedelta(minutes=5)
    reminder_due_before = now + timedelta(hours=settings.reminder_hours_before)

    appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.status == "scheduled")
        .filter(models.Appointment.reminder_sent_at.is_(None))
        .filter(models.Appointment.start_time <= reminder_due_before)
        .filter(models.Appointment.start_time >= window_start)
        .all()
    )

    for appointment in appointments:
        try:
            send_reminder(db, appointment)
        except Exception as e:
            print(f"Reminder job failed for appointment {appointment.id}: {e}")
