from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas

router = APIRouter(prefix="/api/clients", tags=["Clients"])


@router.get("/", response_model=List[schemas.ClientResponse])
def list_clients(q: str = "", db: Session = Depends(get_db)):
    query = db.query(models.Client)
    if q:
        query = query.filter(
            (models.Client.name.ilike(f"%{q}%")) |
            (models.Client.phone.ilike(f"%{q}%")) |
            (models.Client.email.ilike(f"%{q}%"))
        )
    return query.order_by(models.Client.name).all()


@router.post("/", response_model=schemas.ClientResponse)
def create_client(client: schemas.ClientCreate, db: Session = Depends(get_db)):
    db_client = models.Client(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.get("/{client_id}", response_model=schemas.ClientResponse)
def get_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/{client_id}", response_model=schemas.ClientResponse)
def update_client(client_id: int, client: schemas.ClientUpdate, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    for key, value in client.model_dump(exclude_unset=True).items():
        setattr(db_client, key, value)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(db_client)
    db.commit()
    return {"detail": "Client deleted"}
