from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas

router = APIRouter(prefix="/api/staff", tags=["Staff"])


@router.get("/", response_model=List[schemas.StaffResponse])
def list_staff(active_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(models.Staff)
    if active_only:
        q = q.filter(models.Staff.active == True)
    return q.order_by(models.Staff.name).all()


@router.post("/", response_model=schemas.StaffResponse)
def create_staff(staff: schemas.StaffCreate, db: Session = Depends(get_db)):
    s = models.Staff(**staff.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.put("/{staff_id}", response_model=schemas.StaffResponse)
def update_staff(staff_id: int, staff: schemas.StaffUpdate, db: Session = Depends(get_db)):
    s = db.query(models.Staff).filter(models.Staff.id == staff_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Staff not found")
    for k, v in staff.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{staff_id}")
def delete_staff(staff_id: int, db: Session = Depends(get_db)):
    s = db.query(models.Staff).filter(models.Staff.id == staff_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Staff not found")
    if s.appointments:
        s.active = False
        db.commit()
        return {"detail": "Staff has appointments, so it was deactivated instead of deleted"}
    db.delete(s)
    db.commit()
    return {"detail": "Staff deleted"}
