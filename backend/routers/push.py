"""Phone notifications for the admin app: register this device, list devices, send a test."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, push

router = APIRouter(prefix="/api/push", tags=["Push"])


class SubscribeBody(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    device: Optional[str] = None
    origin: Optional[str] = None


class EndpointBody(BaseModel):
    endpoint: str


def _device_view(d: models.PushSubscription):
    return {"id": d.id, "device": d.device or "Device", "created_at": d.created_at,
            "last_success_at": d.last_success_at, "last_error": d.last_error, "endpoint": d.endpoint}


@router.get("/config")
def config(db: Session = Depends(get_db)):
    devices = db.query(models.PushSubscription).order_by(models.PushSubscription.created_at).all()
    return {"available": push.AVAILABLE, "public_key": push.public_key(), "devices": [_device_view(d) for d in devices]}


@router.post("/subscribe")
def subscribe(body: SubscribeBody, db: Session = Depends(get_db)):
    if not push.AVAILABLE:
        raise HTTPException(status_code=503, detail="Push is not available on this server (the cryptography package is missing)")
    if not body.endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid push endpoint")
    try:
        if len(push.b64u_decode(body.p256dh)) != 65 or len(push.b64u_decode(body.auth)) < 16:
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid push keys")
    sub = db.query(models.PushSubscription).filter(models.PushSubscription.endpoint == body.endpoint).first()
    if not sub:
        sub = models.PushSubscription(endpoint=body.endpoint)
        db.add(sub)
    sub.p256dh, sub.auth = body.p256dh, body.auth
    sub.device = (body.device or "Device")[:80]
    if body.origin:
        sub.origin = body.origin[:200]
    db.commit()
    db.refresh(sub)
    return _device_view(sub)


@router.post("/unsubscribe")
def unsubscribe(body: EndpointBody, db: Session = Depends(get_db)):
    n = db.query(models.PushSubscription).filter(models.PushSubscription.endpoint == body.endpoint).delete()
    db.commit()
    return {"removed": n}


@router.delete("/devices/{device_id}")
def remove_device(device_id: int, db: Session = Depends(get_db)):
    n = db.query(models.PushSubscription).filter(models.PushSubscription.id == device_id).delete()
    db.commit()
    if not n:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"removed": n}


@router.post("/test")
def test(body: Optional[EndpointBody] = None, db: Session = Depends(get_db)):
    """Send a test notification to one device (when its endpoint is given) or to all of them."""
    q = db.query(models.PushSubscription)
    if body and body.endpoint:
        q = q.filter(models.PushSubscription.endpoint == body.endpoint)
    subs = q.all()
    if not subs:
        raise HTTPException(status_code=404, detail="No device has notifications turned on yet")
    settings = db.query(models.Setting).first()
    result = push.deliver(db, subs, {"title": f"{settings.business_name}: notifications are on",
                                     "body": "This is a test. Booking alerts will arrive like this.",
                                     "url": "/admin#settings", "tag": "test"})
    if not result["sent"]:
        why = "; ".join(result["errors"]) or "the device's subscription has expired, turn notifications on again"
        raise HTTPException(status_code=502, detail=f"The push service refused the test: {why}")
    return result
