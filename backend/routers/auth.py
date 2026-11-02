from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.auth import verify_password, create_token, require_auth, hash_password, AUTH_DISABLED

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login")
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    settings = db.query(models.Setting).first()
    if AUTH_DISABLED:
        return {"token": create_token(), "business_name": settings.business_name if settings else "LUZ EMS"}
    if not settings or not verify_password(req.password, settings.admin_password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    return {"token": create_token(), "business_name": settings.business_name}


@router.get("/me", dependencies=[Depends(require_auth)])
def me(db: Session = Depends(get_db)):
    settings = db.query(models.Setting).first()
    return {"ok": True, "business_name": settings.business_name if settings else "LUZ EMS",
            "currency": settings.currency if settings else "AED", "timezone": settings.timezone if settings else "Asia/Dubai",
            "demo_mode": settings.demo_mode if settings else True}


@router.post("/password", dependencies=[Depends(require_auth)])
def change_password(req: schemas.PasswordChange, db: Session = Depends(get_db)):
    settings = db.query(models.Setting).first()
    if not verify_password(req.current_password, settings.admin_password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    settings.admin_password_hash = hash_password(req.new_password)
    db.commit()
    return {"detail": "Password updated"}
