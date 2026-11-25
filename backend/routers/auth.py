from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.auth import (verify_password, create_token, require_auth, hash_password, AUTH_DISABLED, PAGES,
                          identity_for, token_from, too_many_attempts, record_failure, clear_failures, _pw_stamp)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login")
def login(req: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    settings = db.query(models.Setting).first()
    business = settings.business_name if settings else "LUZ EMS"
    if AUTH_DISABLED:
        return {"token": create_token(), "business_name": business}
    username = (req.username or "").strip().lower()
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")
    key = f"{ip}|{username}"
    if too_many_attempts(key):
        raise HTTPException(status_code=429, detail="Too many wrong passwords. Wait 15 minutes and try again.")
    if username:  # staff account
        s = db.query(models.Staff).filter(func.lower(models.Staff.login_username) == username).first()
        if not s or not s.active or not s.access_role or not verify_password(req.password, s.password_hash):
            record_failure(key)
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        clear_failures(key)
        return {"token": create_token(s.access_role, s.id, _pw_stamp(s.password_hash)), "business_name": business}
    if not settings or not verify_password(req.password, settings.admin_password_hash):
        record_failure(key)
        raise HTTPException(status_code=401, detail="Incorrect password")
    clear_failures(key)
    return {"token": create_token(), "business_name": business}


@router.get("/me", dependencies=[Depends(require_auth)])
def me(request: Request, db: Session = Depends(get_db)):
    settings = db.query(models.Setting).first()
    ident = getattr(request.state, "identity", None) or identity_for(token_from(request), db) or {"role": "owner", "name": "Owner", "staff_id": 0}
    return {"ok": True, "business_name": settings.business_name if settings else "LUZ EMS",
            "currency": settings.currency if settings else "AED", "timezone": settings.timezone if settings else "Asia/Dubai",
            "demo_mode": settings.demo_mode if settings else True,
            "role": ident["role"], "name": ident["name"], "staff_id": ident["staff_id"], "pages": PAGES.get(ident["role"], [])}


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
