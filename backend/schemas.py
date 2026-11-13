from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


# ---------- Clients ----------
class ClientBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    notes: Optional[str] = None
    date_of_birth: Optional[str] = None
    source: Optional[str] = None
    notify_whatsapp: bool = True
    notify_sms: bool = False
    notify_email: bool = True
    active: bool = True


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    date_of_birth: Optional[str] = None
    source: Optional[str] = None
    notify_whatsapp: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_email: Optional[bool] = None
    active: Optional[bool] = None


class ClientResponse(ClientBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ClientSummary(ClientResponse):
    total_appointments: int = 0
    completed_appointments: int = 0
    no_shows: int = 0
    total_spent: float = 0.0
    outstanding: float = 0.0
    sessions_remaining: int = 0
    last_visit: Optional[datetime] = None
    next_visit: Optional[datetime] = None


# ---------- Staff ----------
class StaffBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    color: str = "#2a78d6"
    role: Optional[str] = "Trainer"
    active: bool = True


class StaffCreate(StaffBase):
    pass


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    color: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None


class StaffResponse(StaffBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---------- Services ----------
class ServiceBase(BaseModel):
    name: str
    duration_minutes: int = 60
    buffer_minutes: int = 0
    price: Optional[float] = None
    color: str = "#6366f1"
    description: Optional[str] = None
    category: Optional[str] = None
    online_bookable: bool = True
    active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    duration_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None
    price: Optional[float] = None
    color: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    online_bookable: Optional[bool] = None
    active: Optional[bool] = None


class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------- Subscriptions ----------
class SubscriptionPlanBase(BaseModel):
    name: str
    sessions_included: int = 1
    duration_days: Optional[int] = None
    price: float
    description: Optional[str] = None
    active: bool = True


class SubscriptionPlanCreate(SubscriptionPlanBase):
    pass


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    sessions_included: Optional[int] = None
    duration_days: Optional[int] = None
    price: Optional[float] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class SubscriptionPlanResponse(SubscriptionPlanBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SubscriptionCreate(BaseModel):
    client_id: int
    plan_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sessions_total: Optional[int] = None
    sessions_used: int = 0
    price_paid: Optional[float] = None
    status: str = "active"
    notes: Optional[str] = None
    payment_method: Optional[str] = "cash"  # records a payment for the sale; None = unpaid
    record_payment: bool = True
    send_notification: bool = True


class SubscriptionUpdate(BaseModel):
    client_id: Optional[int] = None
    plan_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sessions_total: Optional[int] = None
    sessions_used: Optional[int] = None
    price_paid: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class SubscriptionResponse(BaseModel):
    id: int
    client_id: int
    plan_id: int
    start_date: datetime
    end_date: Optional[datetime] = None
    sessions_total: int
    sessions_used: int
    price_paid: float
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    client: ClientResponse
    plan: SubscriptionPlanResponse
    sessions_remaining: int = 0
    paid_amount: float = 0.0
    model_config = ConfigDict(from_attributes=True)


# ---------- Payments ----------
class PaymentCreate(BaseModel):
    client_id: int
    appointment_id: Optional[int] = None
    subscription_id: Optional[int] = None
    amount: float
    method: str = "cash"
    paid_at: Optional[datetime] = None
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    amount: Optional[float] = None
    method: Optional[str] = None
    paid_at: Optional[datetime] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    client_id: int
    appointment_id: Optional[int] = None
    subscription_id: Optional[int] = None
    amount: float
    method: str
    paid_at: datetime
    notes: Optional[str] = None
    created_at: datetime
    client: ClientResponse
    model_config = ConfigDict(from_attributes=True)


# ---------- Appointments ----------
class AppointmentCreate(BaseModel):
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    client_email: Optional[str] = None
    service_id: int
    staff_id: Optional[int] = None
    start_time: datetime
    notes: Optional[str] = None
    use_subscription: Optional[bool] = None  # None = auto (use if the client has one)
    price: Optional[float] = None  # override service price
    send_notification: bool = True
    force: bool = False  # admin override for conflicts / outside hours
    repeat_interval_weeks: int = 0  # 0 = single booking, 1 = weekly, 2 = every two weeks
    repeat_count: int = 1  # total number of sessions including the first


class AppointmentUpdate(BaseModel):
    client_id: Optional[int] = None
    service_id: Optional[int] = None
    staff_id: Optional[int] = None
    start_time: Optional[datetime] = None
    notes: Optional[str] = None
    price: Optional[float] = None
    send_notification: bool = True
    force: bool = False


class AppointmentStatusChange(BaseModel):
    status: str  # confirmed | completed | cancelled | no_show | scheduled
    reason: Optional[str] = None
    send_notification: bool = True
    payment_amount: Optional[float] = None
    payment_method: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: int
    client_id: int
    service_id: int
    staff_id: Optional[int] = None
    subscription_id: Optional[int] = None
    start_time: datetime
    end_time: datetime
    status: str
    price: float
    notes: Optional[str] = None
    source: str
    public_token: Optional[str] = None
    reminder_sent_at: Optional[datetime] = None
    series_id: Optional[str] = None
    notify_result: Optional[List[Dict[str, Any]]] = None
    series_created: Optional[int] = None
    series_skipped: Optional[List[Dict[str, Any]]] = None
    follow_up_sent_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    client: ClientResponse
    service: ServiceResponse
    staff: Optional[StaffResponse] = None
    paid_amount: float = 0.0
    balance_due: float = 0.0
    model_config = ConfigDict(from_attributes=True)


class Slot(BaseModel):
    start_time: datetime
    end_time: datetime
    label: str
    available: bool
    reason: Optional[str] = None


class AvailabilityResponse(BaseModel):
    date: str
    timezone: str
    open: bool
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    slots: List[Slot]


# ---------- Blocked time ----------
class BlockedTimeCreate(BaseModel):
    staff_id: Optional[int] = None
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None


class BlockedTimeResponse(BlockedTimeCreate):
    id: int
    staff: Optional[StaffResponse] = None
    model_config = ConfigDict(from_attributes=True)


class BusinessHoursItem(BaseModel):
    day_of_week: int
    open_time: str = "09:00"
    close_time: str = "21:00"
    closed: bool = False
    model_config = ConfigDict(from_attributes=True)


# ---------- Notifications ----------
class NotificationLogResponse(BaseModel):
    id: int
    appointment_id: Optional[int] = None
    client_id: Optional[int] = None
    type: str
    channel: str
    recipient: Optional[str] = None
    status: str
    subject: Optional[str] = None
    content: str
    external_response: Optional[str] = None
    attempts: int = 0
    next_retry_at: Optional[datetime] = None
    created_at: datetime
    client: Optional[ClientResponse] = None
    model_config = ConfigDict(from_attributes=True)


class MessageTemplateResponse(BaseModel):
    id: int
    key: str
    name: str
    subject: Optional[str] = None
    body: str
    enabled: bool
    model_config = ConfigDict(from_attributes=True)


class MessageTemplateUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    enabled: Optional[bool] = None


class CustomMessage(BaseModel):
    client_id: int
    body: str
    subject: Optional[str] = None
    channels: Optional[List[str]] = None


# ---------- Settings ----------
class SettingsResponse(BaseModel):
    id: int
    business_name: str
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    business_address: Optional[str] = None
    timezone: str
    currency: str
    public_base_url: Optional[str] = None
    slot_interval_minutes: int
    max_concurrent_sessions: int
    auto_complete_past: bool
    online_booking_enabled: bool
    online_min_notice_hours: int
    online_max_days_ahead: int
    online_allow_cancel_hours: int
    whatsapp_provider: str
    whatsapp_enabled: bool
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    sms_enabled: bool
    twilio_sms_number: Optional[str] = None
    email_enabled: bool
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    demo_mode: bool
    reminder_hours_before: int
    admin_reminder_hours: int = 12
    follow_up_enabled: bool
    follow_up_hours_after: int
    subscription_low_threshold: int
    subscription_expiry_notice_days: int
    notify_admin_online_booking: bool
    push_bookings: bool = True
    push_session_reminders: bool = True
    push_failed_messages: bool = True
    push_daily_summary: bool = True
    push_summary_hour: int = 8
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    business_name: Optional[str] = None
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    business_address: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    public_base_url: Optional[str] = None
    slot_interval_minutes: Optional[int] = None
    max_concurrent_sessions: Optional[int] = None
    auto_complete_past: Optional[bool] = None
    online_booking_enabled: Optional[bool] = None
    online_min_notice_hours: Optional[int] = None
    online_max_days_ahead: Optional[int] = None
    online_allow_cancel_hours: Optional[int] = None
    whatsapp_provider: Optional[str] = None
    whatsapp_enabled: Optional[bool] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    sms_enabled: Optional[bool] = None
    twilio_sms_number: Optional[str] = None
    email_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    demo_mode: Optional[bool] = None
    reminder_hours_before: Optional[int] = None
    admin_reminder_hours: Optional[int] = None
    follow_up_enabled: Optional[bool] = None
    follow_up_hours_after: Optional[int] = None
    subscription_low_threshold: Optional[int] = None
    subscription_expiry_notice_days: Optional[int] = None
    notify_admin_online_booking: Optional[bool] = None
    push_bookings: Optional[bool] = None
    push_session_reminders: Optional[bool] = None
    push_failed_messages: Optional[bool] = None
    push_daily_summary: Optional[bool] = None
    push_summary_hour: Optional[int] = Field(default=None, ge=0, le=23)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class LoginRequest(BaseModel):
    password: str


# ---------- Dashboard / reports ----------
class DashboardStats(BaseModel):
    total_clients: int
    new_clients_this_month: int
    total_services: int
    upcoming_appointments: int
    appointments_today: int
    appointments_this_week: int
    unconfirmed_upcoming: int
    unpaid_count: int
    unpaid_amount: float
    revenue_today: float
    revenue_this_week: float
    revenue_this_month: float
    sessions_this_month: int
    active_subscriptions: int
    subscriptions_expiring_soon: int
    today_appointments: List[AppointmentResponse]
    upcoming: List[AppointmentResponse]
    alerts: List[Dict[str, Any]]


# ---------- Expenses ----------
class ExpenseBase(BaseModel):
    date: datetime
    category: str
    payment_method: Optional[str] = "Card"
    amount: float
    notes: Optional[str] = None
    paid: bool = True


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    date: Optional[datetime] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    amount: Optional[float] = None
    notes: Optional[str] = None
    paid: Optional[bool] = None


class ExpenseResponse(ExpenseBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ExpenseSummary(BaseModel):
    category: str
    total: float
    count: int


class ExpenseMonthSummary(BaseModel):
    year: int
    month: int
    expenses: List[ExpenseResponse]
    by_category: List[ExpenseSummary]
    grand_total: float
    unpaid_total: float = 0.0
    unpaid_count: int = 0
