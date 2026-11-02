from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="client", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)
    price = Column(Float, nullable=True)
    color = Column(String, nullable=False, default="#6366f1")
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="service")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="scheduled")
    notes = Column(Text, nullable=True)
    reminder_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
    notifications = relationship("NotificationLog", back_populates="appointment", cascade="all, delete-orphan")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    type = Column(String, nullable=False)
    channel = Column(String, nullable=False, default="whatsapp")
    status = Column(String, nullable=False, default="queued")
    content = Column(Text, nullable=False)
    external_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    appointment = relationship("Appointment", back_populates="notifications")


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

    subscriptions = relationship("Subscription", back_populates="plan", cascade="all, delete-orphan")


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
    status = Column(String, nullable=False, default="active")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", backref="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, nullable=False, default="LUZ EMS")
    business_phone = Column(String, nullable=True)
    twilio_account_sid = Column(String, nullable=True)
    twilio_auth_token = Column(String, nullable=True)
    twilio_phone_number = Column(String, nullable=True)
    whatsapp_provider = Column(String, nullable=False, default="demo")
    whatsapp_enabled = Column(Boolean, default=False)
    demo_mode = Column(Boolean, default=True)
    reminder_hours_before = Column(Integer, nullable=False, default=12)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
