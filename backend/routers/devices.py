"""EMS devices and their maintenance log."""
from datetime import date, datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models
from backend.scheduling import get_settings
from backend.tz import local_today

router = APIRouter(prefix="/api/devices", tags=["Devices"])
DUE_SOON_DAYS = 14


class DeviceIn(BaseModel):
    name: str = Field(..., min_length=1)
    model: Optional[str] = None
    serial_number: Optional[str] = None
    purchased_on: Optional[date] = None
    status: str = Field("active", pattern="^(active|maintenance|retired)$")
    needed_for_sessions: bool = True  # new devices count as machines unless unticked
    service_every_days: Optional[int] = Field(None, ge=1, le=1825)
    notes: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    model: Optional[str] = None
    serial_number: Optional[str] = None
    purchased_on: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(active|maintenance|retired)$")
    needed_for_sessions: Optional[bool] = None
    service_every_days: Optional[int] = Field(None, ge=1, le=1825)
    notes: Optional[str] = None


class MaintenanceIn(BaseModel):
    done_on: date
    kind: str = Field("service", pattern="^(service|repair|inspection|cleaning)$")
    cost: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    add_expense: bool = False


def service_info(d: models.Device, today: date) -> dict:
    """Last service, next due date and a simple state: never | ok | due_soon | overdue | no_schedule."""
    services = [m for m in d.maintenance if m.kind in ("service", "inspection")]
    last = max((m.done_on for m in services), default=None)
    if not d.service_every_days:
        return {"last_service_on": last, "next_service_due": None, "service_state": "no_schedule"}
    if not last:
        return {"last_service_on": None, "next_service_due": None, "service_state": "never"}
    due = date.fromisoformat(last) + timedelta(days=d.service_every_days)
    state = "overdue" if due < today else "due_soon" if due <= today + timedelta(days=DUE_SOON_DAYS) else "ok"
    return {"last_service_on": last, "next_service_due": due.isoformat(), "service_state": state}


def _out(d: models.Device, today: date) -> dict:
    return {"id": d.id, "name": d.name, "model": d.model, "serial_number": d.serial_number, "purchased_on": d.purchased_on,
            "status": d.status, "needed_for_sessions": bool(d.needed_for_sessions), "service_every_days": d.service_every_days, "notes": d.notes,
            "maintenance_count": len(d.maintenance),
            "maintenance_cost": round(sum(m.cost or 0 for m in d.maintenance), 2), **service_info(d, today)}


def needing_service(db: Session) -> List[dict]:
    today = local_today(get_settings(db).timezone)
    rows = [_out(d, today) for d in db.query(models.Device).filter(models.Device.status != "retired").all()]
    return [r for r in rows if r["service_state"] in ("overdue", "due_soon")]


def _get(db: Session, device_id: int) -> models.Device:
    d = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    return d


@router.get("/")
def list_devices(db: Session = Depends(get_db)):
    today = local_today(get_settings(db).timezone)
    rows = db.query(models.Device).order_by(models.Device.status == "retired", models.Device.name).all()
    return [_out(d, today) for d in rows]


@router.post("/")
def create_device(body: DeviceIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["purchased_on"] = data["purchased_on"].isoformat() if data["purchased_on"] else None
    d = models.Device(**data)
    db.add(d)
    db.commit()
    db.refresh(d)
    return _out(d, local_today(get_settings(db).timezone))


@router.get("/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_db)):
    return _out(_get(db, device_id), local_today(get_settings(db).timezone))


@router.put("/{device_id}")
def update_device(device_id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    d = _get(db, device_id)
    data = body.model_dump(exclude_unset=True)
    if "purchased_on" in data:
        data["purchased_on"] = data["purchased_on"].isoformat() if data["purchased_on"] else None
    for k, v in data.items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return _out(d, local_today(get_settings(db).timezone))


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, device_id))
    db.commit()
    return {"detail": "deleted"}


@router.get("/{device_id}/maintenance")
def list_maintenance(device_id: int, db: Session = Depends(get_db)):
    d = _get(db, device_id)
    return [{"id": m.id, "done_on": m.done_on, "kind": m.kind, "cost": m.cost, "notes": m.notes, "expense_id": m.expense_id}
            for m in sorted(d.maintenance, key=lambda m: (m.done_on, m.id), reverse=True)]


@router.post("/{device_id}/maintenance")
def add_maintenance(device_id: int, body: MaintenanceIn, db: Session = Depends(get_db)):
    d = _get(db, device_id)
    m = models.DeviceMaintenance(device_id=d.id, done_on=body.done_on.isoformat(), kind=body.kind, cost=body.cost,
                                 notes=(body.notes or "").strip() or None)
    if body.add_expense and body.cost:
        e = models.Expense(date=datetime(body.done_on.year, body.done_on.month, body.done_on.day, 12), category="Maintenance",
                           amount=body.cost, payment_method="Card", notes=f"{d.name}: {body.kind}" + (f" ({m.notes})" if m.notes else ""))
        db.add(e)
        db.flush()
        m.expense_id = e.id
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "done_on": m.done_on, "kind": m.kind, "cost": m.cost, "notes": m.notes, "expense_id": m.expense_id}


@router.delete("/maintenance/{maintenance_id}")
def delete_maintenance(maintenance_id: int, db: Session = Depends(get_db)):
    m = db.query(models.DeviceMaintenance).filter(models.DeviceMaintenance.id == maintenance_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(m)
    db.commit()
    return {"detail": "deleted"}
