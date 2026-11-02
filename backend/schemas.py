from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ClientBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    notes: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None


class ClientResponse(ClientBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ServiceBase(BaseModel):
    name: str
    duration_minutes: int = 60
    price: Optional[float] = None
    color: str = "#6366f1"
    description: Optional[str] = None
    active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    color: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AppointmentBase(BaseModel):
    client_id: int
    service_id: int
    start_time: datetime
    end_time: datetime
    status: str = "scheduled"
    notes: Optional[str] = None


class AppointmentCreate(BaseModel):
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    service_id: int
    start_time: datetime
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    client_id: Optional[int] = None
    service_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: int
    client_id: int
    service_id: int
    start_time: datetime
    end_time: datetime
    status: str
    notes: Optional[str] = None
    reminder_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    client: ClientResponse
    service: ServiceResponse
    model_config = ConfigDict(from_attributes=True)


class NotificationLogResponse(BaseModel):
    id: int
    appointment_id: int
    type: str
    channel: str
    status: str
    content: str
    external_response: Optional[str] = None
    created_at: datetime
    appointment: Optional[AppointmentResponse] = None
    model_config = ConfigDict(from_attributes=True)


class SettingsBase(BaseModel):
    business_name: str = "LUZ EMS"
    business_phone: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    whatsapp_provider: str = "demo"
    whatsapp_enabled: bool = False
    demo_mode: bool = True
    reminder_hours_before: int = 12


class SettingsUpdate(BaseModel):
    business_name: Optional[str] = None
    business_phone: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    whatsapp_provider: Optional[str] = None
    whatsapp_enabled: Optional[bool] = None
    demo_mode: Optional[bool] = None
    reminder_hours_before: Optional[int] = None


class SettingsResponse(SettingsBase):
    id: int
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DashboardStats(BaseModel):
    total_clients: int
    total_services: int
    upcoming_appointments: int
    appointments_today: int
    appointments_this_week: int
    recent_appointments: List[AppointmentResponse]


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


class SubscriptionBase(BaseModel):
    client_id: int
    plan_id: int
    start_date: datetime
    end_date: Optional[datetime] = None
    sessions_total: int
    sessions_used: int = 0
    price_paid: float
    status: str = "active"
    notes: Optional[str] = None


class SubscriptionCreate(SubscriptionBase):
    pass


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


class SubscriptionResponse(SubscriptionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    client: ClientResponse
    plan: SubscriptionPlanResponse
    model_config = ConfigDict(from_attributes=True)


class WeeklyRevenue(BaseModel):
    week_start: str
    week_end: str
    appointments_revenue: float
    subscriptions_revenue: float
    total_revenue: float
    appointment_count: int
    subscription_count: int
    by_service: List[dict]
