from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.notifications import send_booking_confirmation

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


def _compute_end_time(start_time: datetime, service_id: int, db: Session):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")
    return start_time + timedelta(minutes=service.duration_minutes)


@router.get("/", response_model=List[schemas.AppointmentResponse])
def list_appointments(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Appointment)
    if from_date:
        query = query.filter(models.Appointment.start_time >= from_date)
    if to_date:
        query = query.filter(models.Appointment.start_time < to_date)
    if client_id:
        query = query.filter(models.Appointment.client_id == client_id)
    if status:
        query = query.filter(models.Appointment.status == status)
    return query.order_by(models.Appointment.start_time).all()


@router.post("/", response_model=schemas.AppointmentResponse)
def create_appointment(appointment: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    # Create client inline if requested
    if appointment.client_id:
        client = db.query(models.Client).filter(models.Client.id == appointment.client_id).first()
        if not client:
            raise HTTPException(status_code=400, detail="Client not found")
    else:
        if not appointment.client_name or not appointment.client_phone:
            raise HTTPException(status_code=400, detail="Client name and phone are required")
        client = models.Client(
            name=appointment.client_name,
            phone=appointment.client_phone,
        )
        db.add(client)
        db.commit()
        db.refresh(client)

    service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")

    end_time = _compute_end_time(appointment.start_time, appointment.service_id, db)

    db_appointment = models.Appointment(
        client_id=client.id,
        service_id=appointment.service_id,
        start_time=appointment.start_time,
        end_time=end_time,
        status="scheduled",
        notes=appointment.notes,
    )
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)

    # Send WhatsApp booking confirmation
    try:
        send_booking_confirmation(db, db_appointment)
    except Exception as e:
        # Do not fail the booking if notification fails
        print(f"Failed to send booking confirmation: {e}")

    return db_appointment


@router.get("/{appointment_id}", response_model=schemas.AppointmentResponse)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


@router.put("/{appointment_id}", response_model=schemas.AppointmentResponse)
def update_appointment(
    appointment_id: int,
    appointment: schemas.AppointmentUpdate,
    db: Session = Depends(get_db),
):
    db_appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    data = appointment.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(db_appointment, key, value)

    if "service_id" in data or "start_time" in data:
        db_appointment.end_time = _compute_end_time(
            db_appointment.start_time, db_appointment.service_id, db
        )

    db.commit()
    db.refresh(db_appointment)
    return db_appointment


@router.delete("/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    db_appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(db_appointment)
    db.commit()
    return {"detail": "Appointment deleted"}
