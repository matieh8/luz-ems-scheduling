"""Multi-channel client notifications (WhatsApp / SMS / email) driven by editable templates."""
import requests
import os
import smtplib
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend import models
from backend.database import DATA_DIR, SessionLocal
from backend.tz import fmt_date, fmt_time, fmt_datetime, utcnow, to_local

# ---------------------------------------------------------------- templates
DEFAULT_TEMPLATES = {
    "booking_confirmation": {
        "name": "Booking confirmation",
        "subject": "Your {service_name} session is confirmed - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Your *{service_name}* session at *{business_name}* is confirmed.\n\n"
            "📅 {date}\n⏰ {time}\n⏱ {duration} minutes{staff_line}\n\n"
            "Need to change it? Manage your booking here: {manage_link}\n\n"
            "You'll get a reminder {reminder_hours} hours before. See you soon!\n{business_name}"
        ),
    },
    "reminder": {
        "name": "Session reminder",
        "subject": "Reminder: {service_name} {time_relative} - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "⏰ Reminder: your *{service_name}* session at *{business_name}* is {time_relative}.\n\n"
            "📅 {date}\n⏰ {time}\n⏱ {duration} minutes{staff_line}\n\n"
            "Reply or use this link if you need to change it: {manage_link}\n\nSee you soon!"
        ),
    },
    "reschedule": {
        "name": "Booking rescheduled",
        "subject": "Your session has been moved - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Your *{service_name}* session at *{business_name}* has been rescheduled.\n\n"
            "📅 New date: {date}\n⏰ New time: {time}\n⏱ {duration} minutes{staff_line}\n\n"
            "Manage your booking: {manage_link}\n\nSee you then!"
        ),
    },
    "cancellation": {
        "name": "Booking cancelled",
        "subject": "Your session was cancelled - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Your *{service_name}* session on {date} at {time} has been cancelled.{reason_line}\n\n"
            "To book again, contact us on {business_phone} or book online: {booking_link}\n\n{business_name}"
        ),
    },
    "follow_up": {
        "name": "After-session follow-up",
        "subject": "Thanks for training with us - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Thanks for your *{service_name}* session today at *{business_name}*! 💪\n\n"
            "Drink plenty of water and get some rest - EMS works your muscles deeply.\n"
            "{sessions_remaining_line}"
            "Ready for the next one? Book here: {booking_link}\n\n{business_name}"
        ),
    },
    "subscription_purchase": {
        "name": "Package purchased",
        "subject": "Your {plan_name} is active - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Thank you for purchasing the *{plan_name}* at *{business_name}*.\n\n"
            "🎟 Sessions: {sessions_total}\n📅 Valid until: {expiry_date}\n💰 Paid: {currency} {amount}\n\n"
            "Book your sessions here: {booking_link}\n\n{business_name}"
        ),
    },
    "subscription_low": {
        "name": "Package running low",
        "subject": "Only {sessions_remaining} sessions left - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "You have *{sessions_remaining}* session(s) left on your *{plan_name}* at *{business_name}*.\n\n"
            "Renew now to keep your momentum going - just reply to this message or call {business_phone}.\n\n{business_name}"
        ),
    },
    "subscription_expiring": {
        "name": "Package expiring soon",
        "subject": "Your {plan_name} expires on {expiry_date} - {business_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Your *{plan_name}* at *{business_name}* expires on *{expiry_date}* with "
            "{sessions_remaining} session(s) remaining.\n\n"
            "Book them here before they expire: {booking_link}\n\n{business_name}"
        ),
    },
    "admin_session_reminder": {
        "name": "Owner reminder: upcoming session",
        "subject": "Upcoming session {time_relative}: {client_full_name}",
        "body": (
            "⏰ Session {time_relative} at {business_name}\n\n"
            "👤 {client_full_name} ({client_phone})\n✨ {service_name}\n📅 {date} at {time}{staff_line}"
        ),
    },
    "admin_new_booking": {
        "name": "Admin alert: new online booking",
        "subject": "New online booking: {client_name} - {service_name}",
        "body": (
            "📥 New online booking at {business_name}\n\n"
            "👤 {client_name} ({client_phone})\n✨ {service_name}\n📅 {date} at {time}{staff_line}"
        ),
    },
}

PLACEHOLDERS = [
    "client_name", "client_full_name", "client_phone", "business_name", "business_phone", "business_address", "service_name",
    "date", "time", "datetime", "duration", "staff_name", "staff_line", "price", "price_line", "currency",
    "manage_link", "booking_link", "reminder_hours", "time_relative", "reason_line", "plan_name",
    "sessions_total", "sessions_remaining", "sessions_remaining_line", "expiry_date", "amount",
]


CLIENT_PRICE_FREE_KEYS = {"booking_confirmation", "reminder", "reschedule", "cancellation", "follow_up"}


def ensure_templates(db: Session):
    templates = {t.key: t for t in db.query(models.MessageTemplate).all()}
    for key, t in DEFAULT_TEMPLATES.items():
        if key not in templates:
            db.add(models.MessageTemplate(key=key, name=t["name"], subject=t["subject"], body=t["body"], enabled=True))
    # Client-facing session messages never mention prices (one-time cleanup of templates saved before this rule).
    for key, t in templates.items():
        if key in CLIENT_PRICE_FREE_KEYS and t.body and ("{price_line}" in t.body or "{price}" in t.body):
            t.body = t.body.replace("{price_line}", "").replace("{price}", "")
            if t.subject:
                t.subject = t.subject.replace("{price_line}", "").replace("{price}", "")
    db.commit()


def get_settings(db: Session) -> models.Setting:
    settings = db.query(models.Setting).first()
    if not settings:
        settings = models.Setting()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render(db: Session, key: str, ctx: Dict[str, str]):
    tpl = db.query(models.MessageTemplate).filter(models.MessageTemplate.key == key).first()
    if tpl and not tpl.enabled:
        return None, None
    subject = tpl.subject if tpl else DEFAULT_TEMPLATES[key]["subject"]
    body = tpl.body if tpl else DEFAULT_TEMPLATES[key]["body"]
    safe = _SafeDict(ctx)
    return (subject or "").format_map(safe), body.format_map(safe)


def build_context(db: Session, client: models.Client, appointment: Optional[models.Appointment] = None,
                  subscription: Optional[models.Subscription] = None, extra: Optional[dict] = None) -> Dict[str, str]:
    s = get_settings(db)
    tz = s.timezone
    base = (s.public_base_url or "").rstrip("/")
    ctx = {
        "client_name": client.name.split(" ")[0] if client.name else "there",
        "client_full_name": client.name,
        "client_phone": client.phone,
        "business_name": s.business_name,
        "business_phone": s.business_phone or "",
        "business_address": s.business_address or "",
        "currency": s.currency,
        "reminder_hours": str(s.reminder_hours_before),
        "booking_link": f"{base}/book" if base else "(online booking link)",
        "staff_line": "", "price_line": "", "reason_line": "", "sessions_remaining_line": "",
        "time_relative": f"in {s.reminder_hours_before} hours",
    }
    if appointment:
        svc = appointment.service
        ctx.update({
            "service_name": svc.name,
            "date": fmt_date(appointment.start_time, tz),
            "time": fmt_time(appointment.start_time, tz),
            "datetime": fmt_datetime(appointment.start_time, tz),
            "duration": str(svc.duration_minutes),
            "staff_name": appointment.staff.name if appointment.staff else "",
            "price": f"{appointment.price:.0f}",
            "manage_link": f"{base}/a/{appointment.public_token}" if base else "(booking link)",
        })
        if appointment.staff:
            ctx["staff_line"] = f"\n👤 Trainer: {appointment.staff.name}"
        if appointment.subscription_id:
            ctx["price_line"] = "\n🎟 Covered by your package"
        elif appointment.price:
            ctx["price_line"] = f"\n💰 Price: {s.currency} {appointment.price:.0f}"
        if appointment.cancel_reason:
            ctx["reason_line"] = f"\nReason: {appointment.cancel_reason}"
        sub = appointment.subscription
        if sub:
            remaining = max(sub.sessions_total - sub.sessions_used, 0)
            ctx["sessions_remaining"] = str(remaining)
            ctx["sessions_remaining_line"] = f"You have {remaining} session(s) left on your {sub.plan.name}.\n\n"
    if subscription:
        remaining = max(subscription.sessions_total - subscription.sessions_used, 0)
        ctx.update({
            "plan_name": subscription.plan.name,
            "sessions_total": str(subscription.sessions_total),
            "sessions_remaining": str(remaining),
            "expiry_date": fmt_date(subscription.end_date, tz).split(", ", 1)[-1] if subscription.end_date else "no expiry",
            "amount": f"{subscription.price_paid:.0f}",
        })
    if extra:
        ctx.update(extra)
    return ctx


# ---------------------------------------------------------------- delivery
def normalize_phone(phone: str) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) in (9, 10):
        digits = "971" + digits[1:]
    elif digits.startswith("5") and len(digits) == 9:
        digits = "971" + digits
    return digits


def _demo_log(channel: str, to: str, message_type: str, subject: Optional[str], body: str):
    path = os.path.join(DATA_DIR, "demo_messages.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n{utcnow().isoformat()} UTC | {channel} -> {to} | {message_type}\n")
            if subject:
                f.write(f"Subject: {subject}\n")
            f.write(f"{body}\n")
    except Exception:
        pass


def _send_whatsapp(settings: models.Setting, to_phone: str, body: str) -> str:
    provider = settings.whatsapp_provider or "demo"
    if provider == "whatsapp_web":
        from backend import whatsapp_web_client
        try:
            resp = whatsapp_web_client.send_message(to_phone, body)
        except requests.exceptions.ConnectionError:
            raise whatsapp_web_client.BridgeNotReady("WhatsApp bridge is not running on this server. Open Settings → Messaging for the reason, or switch Demo mode on.")
        return f"whatsapp_web: {resp}"
    from twilio.rest import Client
    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number]):
        raise ValueError("Twilio credentials incomplete")
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    sender = settings.twilio_phone_number
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"
    msg = client.messages.create(from_=sender, body=body, to=f"whatsapp:+{to_phone}")
    if msg.status in ("failed", "undelivered"):
        raise RuntimeError(f"twilio status {msg.status}")
    return f"twilio: sid={msg.sid}; status={msg.status}"


def _send_sms(settings: models.Setting, to_phone: str, body: str) -> str:
    from twilio.rest import Client
    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_sms_number]):
        raise ValueError("Twilio SMS credentials incomplete")
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    plain = body.replace("*", "")
    msg = client.messages.create(from_=settings.twilio_sms_number, body=plain, to=f"+{to_phone}")
    if msg.status in ("failed", "undelivered"):
        raise RuntimeError(f"twilio status {msg.status}")
    return f"twilio-sms: sid={msg.sid}; status={msg.status}"


def _send_email(settings: models.Setting, to_email: str, subject: str, body: str) -> str:
    if not settings.smtp_host:
        raise ValueError("SMTP host not configured")
    msg = MIMEText(body.replace("*", ""), "plain", "utf-8")
    msg["Subject"] = subject or settings.business_name
    msg["From"] = settings.smtp_from or settings.smtp_username or settings.business_email or "noreply@example.com"
    msg["To"] = to_email
    port = settings.smtp_port or 587
    if port == 465:
        server = smtplib.SMTP_SSL(settings.smtp_host, port, timeout=20)
    else:
        server = smtplib.SMTP(settings.smtp_host, port, timeout=20)
        server.ehlo()
        try:
            server.starttls()
        except smtplib.SMTPException:
            pass
    try:
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.sendmail(msg["From"], [to_email], msg.as_string())
    finally:
        server.quit()
    return "smtp: accepted"


RETRY_MAX_ATTEMPTS = 6
RETRY_INTERVAL = timedelta(minutes=10)
RETRY_WINDOW = timedelta(hours=3)


def _retryable(exc: Exception) -> bool:
    """Temporary conditions: WhatsApp not connected / bridge down / network. Not bad numbers or config errors."""
    from backend import whatsapp_web_client
    return isinstance(exc, (whatsapp_web_client.BridgeNotReady, requests.exceptions.RequestException, smtplib.SMTPConnectError, TimeoutError, ConnectionError))


def run_retry_job(db: Session):
    """Re-send failed messages whose failure was temporary (e.g. WhatsApp not yet paired)."""
    now = utcnow()
    due = (db.query(models.NotificationLog)
           .filter(models.NotificationLog.status == "failed", models.NotificationLog.next_retry_at != None,  # noqa: E711
                   models.NotificationLog.next_retry_at <= now).all())
    for log in due:
        log.status = "queued"
        log.next_retry_at = None
    db.commit()
    for log in due:
        threading.Thread(target=_deliver, args=(log.id,), daemon=True).start()
    return len(due)


def _deliver(log_id: int):
    """Runs in a worker thread with its own session."""
    db = SessionLocal()
    try:
        log = db.query(models.NotificationLog).get(log_id)
        if not log:
            return
        settings = get_settings(db)
        try:
            if log.channel == "whatsapp":
                log.external_response = _send_whatsapp(settings, log.recipient, log.content)
            elif log.channel == "sms":
                log.external_response = _send_sms(settings, log.recipient, log.content)
            elif log.channel == "email":
                log.external_response = _send_email(settings, log.recipient, log.subject, log.content)
            log.status = "sent"
            log.next_retry_at = None
        except Exception as e:
            log.status = "failed"
            log.attempts = (log.attempts or 0) + 1
            log.external_response = f"{log.channel}: {e}"
            if _retryable(e) and log.attempts < RETRY_MAX_ATTEMPTS and log.created_at > utcnow() - RETRY_WINDOW:
                log.next_retry_at = utcnow() + RETRY_INTERVAL
                log.external_response += f" — will retry automatically (attempt {log.attempts} of {RETRY_MAX_ATTEMPTS})"
            else:
                log.next_retry_at = None
        db.commit()
    finally:
        db.close()


def channels_for(settings: models.Setting, client: models.Client) -> List[str]:
    out = []
    if client.phone and client.notify_whatsapp and (settings.whatsapp_enabled or settings.demo_mode):
        out.append("whatsapp")
    if client.phone and client.notify_sms and (settings.sms_enabled or settings.demo_mode):
        out.append("sms")
    if client.email and client.notify_email and (settings.email_enabled or settings.demo_mode):
        out.append("email")
    return out


def send(db: Session, key: str, client: models.Client, appointment: Optional[models.Appointment] = None,
         subscription: Optional[models.Subscription] = None, extra: Optional[dict] = None,
         channels: Optional[List[str]] = None, raw_body: Optional[str] = None, raw_subject: Optional[str] = None,
         recipient_override: Optional[dict] = None, sync: bool = False,
         append: Optional[str] = None) -> List[models.NotificationLog]:
    """Render template `key` for the client and send on every channel they accept."""
    settings = get_settings(db)
    if raw_body is not None:
        subject, body = raw_subject or settings.business_name, raw_body
    else:
        subject, body = render(db, key, build_context(db, client, appointment, subscription, extra))
        if body is None:  # template disabled
            return []
    if append:
        body = f"{body}\n\n{append}"
    chans = channels if channels is not None else channels_for(settings, client)
    logs: List[models.NotificationLog] = []
    for channel in chans:
        if channel == "email":
            recipient = (recipient_override or {}).get("email") or client.email
        else:
            recipient = normalize_phone((recipient_override or {}).get("phone") or client.phone)
        if not recipient:
            continue
        log = models.NotificationLog(
            appointment_id=appointment.id if appointment else None,
            client_id=client.id if client.id else None,
            type=key, channel=channel, recipient=recipient,
            status="queued", subject=subject if channel == "email" else None, content=body,
        )
        db.add(log)
        logs.append(log)
    db.commit()
    for log in logs:
        if settings.demo_mode:
            log.status = "sent"
            log.external_response = f"DEMO MODE: {log.channel} message logged, not sent"
            _demo_log(log.channel, log.recipient, key, log.subject, body)
            db.commit()
            continue
        enabled = {"whatsapp": settings.whatsapp_enabled, "sms": settings.sms_enabled, "email": settings.email_enabled}
        if not enabled.get(log.channel):
            log.status = "skipped"
            log.external_response = f"{log.channel} not enabled in settings"
            db.commit()
            continue
        if sync:
            _deliver(log.id)
        else:
            threading.Thread(target=_deliver, args=(log.id,), daemon=True).start()
    return logs


# ---------------------------------------------------------------- high-level events
def send_booking_confirmation(db, appointment, append=None, sync=False):
    return send(db, "booking_confirmation", appointment.client, appointment, append=append, sync=sync)


def explain_result(db, key: str, client: models.Client, logs: List[models.NotificationLog]) -> List[dict]:
    """Plain-language outcome of a send, so the UI can say what really happened."""
    settings = get_settings(db)
    if logs:
        out = []
        for log in logs:
            db.refresh(log)
            out.append({"channel": log.channel, "status": log.status, "detail": log.external_response or ""})
        return out
    tpl = db.query(models.MessageTemplate).filter(models.MessageTemplate.key == key).first()
    if tpl and not tpl.enabled:
        why = "the message template is switched off (Messages → Templates)"
    elif not (client.notify_whatsapp or client.notify_sms or client.notify_email):
        why = "this client has all notifications switched off"
    elif client.notify_whatsapp and not (settings.whatsapp_enabled or settings.demo_mode):
        why = "WhatsApp is not enabled in Settings → Messaging"
    elif not client.phone:
        why = "the client has no phone number"
    else:
        why = "no channel is enabled for this client (check Settings → Messaging and the client's notification choices)"
    return [{"channel": None, "status": "skipped", "detail": why}]


def send_reminder(db, appointment):
    settings = get_settings(db)
    hours = max(int((appointment.start_time - utcnow()).total_seconds() // 3600), 0)
    rel = "today" if hours < 1 else ("in 1 hour" if hours == 1 else f"in {hours} hours")
    logs = send(db, "reminder", appointment.client, appointment, extra={"time_relative": rel})
    if any(l.status in ("sent", "queued") for l in logs):
        appointment.reminder_sent_at = utcnow()
        db.commit()
    return logs


def send_reschedule(db, appointment):
    appointment.reminder_sent_at = None  # a new reminder will go out for the new time
    db.commit()
    return send(db, "reschedule", appointment.client, appointment)


def send_cancellation(db, appointment):
    return send(db, "cancellation", appointment.client, appointment)


def send_follow_up(db, appointment):
    logs = send(db, "follow_up", appointment.client, appointment)
    appointment.follow_up_sent_at = utcnow()
    db.commit()
    return logs


def send_subscription_purchase(db, subscription):
    return send(db, "subscription_purchase", subscription.client, subscription=subscription)


def notify_admin_new_booking(db, appointment):
    settings = get_settings(db)
    if not settings.notify_admin_online_booking or not (settings.business_phone or settings.business_email):
        return []
    admin = models.Client(name=settings.business_name, phone=settings.business_phone or "",
                          email=settings.business_email, notify_whatsapp=True, notify_sms=False,
                          notify_email=bool(settings.business_email))
    ctx = build_context(db, appointment.client, appointment)
    subject, body = render(db, "admin_new_booking", ctx)
    if body is None:
        return []
    chans = []
    if settings.business_phone and (settings.whatsapp_enabled or settings.demo_mode):
        chans.append("whatsapp")
    if settings.business_email and (settings.email_enabled or settings.demo_mode):
        chans.append("email")
    return send(db, "admin_new_booking", admin, appointment, channels=chans, raw_body=body, raw_subject=subject,
                recipient_override={"phone": settings.business_phone, "email": settings.business_email})


def notify_admin_upcoming(db, appointment):
    """Heads-up to the owner (business phone / email) before a session."""
    settings = get_settings(db)
    if not (settings.business_phone or settings.business_email):
        return []
    hours = max(int(round((appointment.start_time - utcnow()).total_seconds() / 3600)), 0)
    rel = "starting now" if hours < 1 else ("in 1 hour" if hours == 1 else f"in {hours} hours")
    ctx = build_context(db, appointment.client, appointment, extra={"time_relative": rel})
    subject, body = render(db, "admin_session_reminder", ctx)
    if body is None:
        return []
    admin = models.Client(name=settings.business_name, phone=settings.business_phone or "",
                          email=settings.business_email, notify_whatsapp=True, notify_sms=False,
                          notify_email=bool(settings.business_email))
    chans = []
    if settings.business_phone and (settings.whatsapp_enabled or settings.demo_mode):
        chans.append("whatsapp")
    if settings.business_email and (settings.email_enabled or settings.demo_mode):
        chans.append("email")
    return send(db, "admin_session_reminder", admin, appointment, channels=chans, raw_body=body, raw_subject=subject,
                recipient_override={"phone": settings.business_phone, "email": settings.business_email})


def run_admin_reminder_job(db: Session):
    settings = get_settings(db)
    hours = settings.admin_reminder_hours or 0
    if hours <= 0:
        return
    now = utcnow()
    due = (
        db.query(models.Appointment)
        .filter(models.Appointment.status.in_(("scheduled", "confirmed")))
        .filter(models.Appointment.admin_reminder_sent_at.is_(None))
        .filter(models.Appointment.start_time <= now + timedelta(hours=hours))
        .filter(models.Appointment.start_time >= now)
        .all()
    )
    for a in due:
        try:
            notify_admin_upcoming(db, a)
        except Exception as e:
            print(f"[jobs] owner reminder failed for appointment {a.id}: {e}")
        a.admin_reminder_sent_at = now
    db.commit()


# ---------------------------------------------------------------- background jobs
def run_reminder_job(db: Session):
    settings = get_settings(db)
    if settings.reminder_hours_before <= 0:
        return
    now = utcnow()
    due = (
        db.query(models.Appointment)
        .filter(models.Appointment.status.in_(("scheduled", "confirmed")))
        .filter(models.Appointment.reminder_sent_at.is_(None))
        .filter(models.Appointment.start_time <= now + timedelta(hours=settings.reminder_hours_before))
        .filter(models.Appointment.start_time >= now)
        .all()
    )
    for a in due:
        try:
            send_reminder(db, a)
        except Exception as e:
            print(f"[jobs] reminder failed for appointment {a.id}: {e}")


def run_auto_complete_job(db: Session):
    settings = get_settings(db)
    if not settings.auto_complete_past:
        return
    now = utcnow()
    past = (
        db.query(models.Appointment)
        .filter(models.Appointment.status.in_(("scheduled", "confirmed")))
        .filter(models.Appointment.end_time <= now)
        .all()
    )
    for a in past:
        a.status = "completed"
        a.completed_at = a.end_time
    if past:
        db.commit()


def run_follow_up_job(db: Session):
    settings = get_settings(db)
    if not settings.follow_up_enabled:
        return
    now = utcnow()
    due = (
        db.query(models.Appointment)
        .filter(models.Appointment.status == "completed")
        .filter(models.Appointment.follow_up_sent_at.is_(None))
        .filter(models.Appointment.end_time <= now - timedelta(hours=settings.follow_up_hours_after))
        .filter(models.Appointment.end_time >= now - timedelta(days=2))  # never spam old history
        .all()
    )
    for a in due:
        try:
            send_follow_up(db, a)
        except Exception as e:
            print(f"[jobs] follow-up failed for appointment {a.id}: {e}")


def run_subscription_job(db: Session):
    settings = get_settings(db)
    now = utcnow()
    subs = db.query(models.Subscription).filter(models.Subscription.status == "active").all()
    for s in subs:
        remaining = s.sessions_total - s.sessions_used
        if s.end_date and s.end_date < now:
            s.status = "expired"
            continue
        if remaining <= 0:
            s.status = "completed"
            continue
        if remaining <= settings.subscription_low_threshold and not s.low_notified_at:
            send(db, "subscription_low", s.client, subscription=s)
            s.low_notified_at = now
        if (s.end_date and not s.expiry_notified_at
                and s.end_date <= now + timedelta(days=settings.subscription_expiry_notice_days)):
            send(db, "subscription_expiring", s.client, subscription=s)
            s.expiry_notified_at = now
    db.commit()


def run_all_jobs(db: Session):
    """Called every minute by the scheduler."""
    run_auto_complete_job(db)
    run_reminder_job(db)
    run_admin_reminder_job(db)
    run_follow_up_job(db)
    run_retry_job(db)
    settings = get_settings(db)
    if not settings.last_daily_job_at or settings.last_daily_job_at < utcnow() - timedelta(hours=6):
        run_subscription_job(db)
        settings.last_daily_job_at = utcnow()
        db.commit()
