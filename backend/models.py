import secrets
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base


def _token():
    return secrets.token_urlsafe(16)


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    date_of_birth = Column(String, nullable=True)
    source = Column(String, nullable=True)  # walk-in / instagram / referral / online
    notify_whatsapp = Column(Boolean, default=True)
    notify_sms = Column(Boolean, default=False)
    notify_email = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="client", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="client", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="client", cascade="all, delete-orphan")


class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    color = Column(String, nullable=False, default="#2a78d6")
    role = Column(String, nullable=True, default="Trainer")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="staff")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)
    buffer_minutes = Column(Integer, nullable=False, default=0)
    price = Column(Float, nullable=True)
    color = Column(String, nullable=False, default="#6366f1")
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    online_bookable = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="service")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    # scheduled | confirmed | completed | cancelled | no_show
    status = Column(String, nullable=False, default="scheduled", index=True)
    price = Column(Float, nullable=False, default=0.0)  # snapshot at booking; 0 when covered by a subscription
    notes = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="admin")  # admin | online
    public_token = Column(String, nullable=True, unique=True, default=_token)
    reminder_sent_at = Column(DateTime, nullable=True)
    admin_reminder_sent_at = Column(DateTime, nullable=True)
    series_id = Column(String, nullable=True, index=True)  # shared by all sessions of one repeat booking
    follow_up_sent_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    cancelled_by = Column(String, nullable=True)  # admin | client
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
    staff = relationship("Staff", back_populates="appointments")
    subscription = relationship("Subscription", back_populates="appointments")
    notifications = relationship("NotificationLog", back_populates="appointment", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="appointment")


class BlockedTime(Base):
    """Holidays, breaks, maintenance - time that cannot be booked."""
    __tablename__ = "blocked_times"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)  # null = whole studio
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    staff = relationship("Staff")


class BusinessHours(Base):
    __tablename__ = "business_hours"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False, unique=True)  # 0 = Monday ... 6 = Sunday
    open_time = Column(String, nullable=False, default="09:00")
    close_time = Column(String, nullable=False, default="21:00")
    closed = Column(Boolean, default=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=False, default="cash")  # cash | card | transfer | online | other
    paid_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="payments")
    appointment = relationship("Appointment", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    type = Column(String, nullable=False)
    channel = Column(String, nullable=False, default="whatsapp")  # whatsapp | sms | email
    recipient = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued")  # queued | sent | failed | skipped
    subject = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    external_response = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)  # set when a failure is worth retrying automatically
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    appointment = relationship("Appointment", back_populates="notifications")
    client = relationship("Client")


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=True)  # used for email
    body = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    sessions_included = Column(Integer, nullable=False, default=1)
    duration_days = Column(Integer, nullable=True)
    price = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    start_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    sessions_total = Column(Integer, nullable=False)
    sessions_used = Column(Integer, nullable=False, default=0)
    price_paid = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="active")  # active | expired | cancelled | completed
    notes = Column(Text, nullable=True)
    low_notified_at = Column(DateTime, nullable=True)
    expiry_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    appointments = relationship("Appointment", back_populates="subscription")
    payments = relationship("Payment", back_populates="subscription")


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, nullable=False, default="LUZ EMS")
    business_phone = Column(String, nullable=True)
    business_email = Column(String, nullable=True)
    business_address = Column(String, nullable=True)
    timezone = Column(String, nullable=False, default="Asia/Dubai")
    currency = Column(String, nullable=False, default="AED")
    public_base_url = Column(String, nullable=True)  # e.g. https://book.luzems.com

    # Scheduling rules
    slot_interval_minutes = Column(Integer, nullable=False, default=30)
    max_concurrent_sessions = Column(Integer, nullable=False, default=1)  # machines / rooms
    auto_complete_past = Column(Boolean, default=True)
    online_booking_enabled = Column(Boolean, default=True)
    online_min_notice_hours = Column(Integer, nullable=False, default=2)
    online_max_days_ahead = Column(Integer, nullable=False, default=30)
    online_allow_cancel_hours = Column(Integer, nullable=False, default=12)

    # WhatsApp
    whatsapp_provider = Column(String, nullable=False, default="demo")  # demo | whatsapp_web | twilio
    whatsapp_enabled = Column(Boolean, default=False)
    twilio_account_sid = Column(String, nullable=True)
    twilio_auth_token = Column(String, nullable=True)
    twilio_phone_number = Column(String, nullable=True)  # WhatsApp sender
    # SMS (Twilio)
    sms_enabled = Column(Boolean, default=False)
    twilio_sms_number = Column(String, nullable=True)
    # Email (SMTP)
    email_enabled = Column(Boolean, default=False)
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True, default=587)
    smtp_username = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)
    smtp_from = Column(String, nullable=True)

    demo_mode = Column(Boolean, default=True)
    reminder_hours_before = Column(Integer, nullable=False, default=12)
    admin_reminder_hours = Column(Integer, nullable=False, default=12)  # owner heads-up before each session; 0 = off
    follow_up_enabled = Column(Boolean, default=True)
    follow_up_hours_after = Column(Integer, nullable=False, default=2)
    subscription_low_threshold = Column(Integer, nullable=False, default=2)
    subscription_expiry_notice_days = Column(Integer, nullable=False, default=7)
    notify_admin_online_booking = Column(Boolean, default=True)

    admin_password_hash = Column(String, nullable=True)
    last_daily_job_at = Column(DateTime, nullable=True)
    alerts_dismissed = Column(Text, nullable=True)  # JSON {alert_key: iso utc timestamp}
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, default=datetime.utcnow)
    category = Column(String, nullable=False)
    payment_method = Column(String, nullable=True, default="Card")
    amount = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    paid = Column(Boolean, nullable=False, default=True)  # False = bill still to pay
    created_at = Column(DateTime, default=datetime.utcnow)


# ---- derived values exposed to the API (read by pydantic via from_attributes) ----
def _appt_paid_amount(self):
    return float(sum(p.amount for p in self.payments))


def _appt_balance_due(self):
    if self.status in ("cancelled", "no_show") or self.subscription_id:
        return 0.0
    return max(float(self.price or 0) - _appt_paid_amount(self), 0.0)


def _sub_remaining(self):
    return max(int(self.sessions_total) - int(self.sessions_used), 0)


def _sub_paid(self):
    return float(sum(p.amount for p in self.payments))


Appointment.paid_amount = property(_appt_paid_amount)
Appointment.balance_due = property(_appt_balance_due)
Subscription.sessions_remaining = property(_sub_remaining)
Subscription.paid_amount = property(_sub_paid)

# Transient, per-request extras returned by the booking endpoint (never stored).
Appointment.notify_result = None
Appointment.series_created = None
Appointment.series_skipped = None
