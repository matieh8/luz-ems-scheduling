from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas

router = APIRouter(prefix="/api/services", tags=["Services"])


@router.get("/", response_model=List[schemas.ServiceResponse])
def list_services(active_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.Service)
    if active_only:
        query = query.filter(models.Service.active == True)
    return query.order_by(models.Service.name).all()


@router.post("/", response_model=schemas.ServiceResponse)
def create_service(service: schemas.ServiceCreate, db: Session = Depends(get_db)):
    db_service = models.Service(**service.model_dump())
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service


@router.get("/{service_id}", response_model=schemas.ServiceResponse)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.put("/{service_id}", response_model=schemas.ServiceResponse)
def update_service(service_id: int, service: schemas.ServiceUpdate, db: Session = Depends(get_db)):
    db_service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Service not found")
    for key, value in service.model_dump(exclude_unset=True).items():
        setattr(db_service, key, value)
    db.commit()
    db.refresh(db_service)
    return db_service


@router.delete("/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    db_service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(db_service)
    db.commit()
    return {"detail": "Service deleted"}
