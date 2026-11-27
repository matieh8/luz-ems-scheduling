"""Global search across clients, bookings, packages, payments and leads.

Each kind only appears when the signed-in account may already read it (same rules as the rest of the API)."""
import re
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from backend.auth import allowed
from backend.database import get_db
from backend import models
from backend.scheduling import get_settings
from backend.tz import to_local, utcnow

router = APIRouter(prefix="/api/search", tags=["Search"])
LIMIT = 6


@router.get("/")
def search(request: Request, q: str = Query(..., min_length=2, max_length=60), db: Session = Depends(get_db)):
    role = (getattr(request.state, "identity", None) or {"role": "owner"})["role"]
    can = lambda path: allowed(role, "GET", path)
    tz = get_settings(db).timezone
    term = q.strip()
    like, digits = f"%{term}%", re.sub(r"\D", "", term)
    phone_match = lambda col: func.replace(func.replace(col, " ", ""), "-", "").like(f"%{digits}%") if len(digits) >= 3 else False
    when = lambda dt: to_local(dt, tz).strftime("%a %d %b %Y, %H:%M") if dt else ""
    out = {}
    if can("/api/clients/"):
        rows = (db.query(models.Client).filter(or_(models.Client.name.ilike(like), models.Client.email.ilike(like), phone_match(models.Client.phone)))
                .order_by(models.Client.active.desc(), models.Client.name).limit(LIMIT).all())
        out["clients"] = [{"id": c.id, "title": c.name, "sub": " · ".join(filter(None, [c.phone, c.email, None if c.active else "archived"]))} for c in rows]
    if can("/api/appointments/"):
        base = (db.query(models.Appointment).join(models.Client).join(models.Service)
                .filter(or_(models.Client.name.ilike(like), models.Service.name.ilike(like), phone_match(models.Client.phone))))
        now = utcnow()
        rows = (base.filter(models.Appointment.start_time >= now).order_by(models.Appointment.start_time).limit(4).all()
                + base.filter(models.Appointment.start_time < now).order_by(models.Appointment.start_time.desc()).limit(LIMIT - 2).all())[:LIMIT]
        out["bookings"] = [{"id": a.id, "client_id": a.client_id, "title": f"{a.client.name} · {a.service.name}",
                            "sub": f"{when(a.start_time)} · {a.status.replace('_', ' ')}"} for a in rows]
    if can("/api/subscriptions/"):
        rows = (db.query(models.Subscription).join(models.Client).join(models.SubscriptionPlan)
                .filter(or_(models.Client.name.ilike(like), models.SubscriptionPlan.name.ilike(like), phone_match(models.Client.phone)))
                .order_by(models.Subscription.created_at.desc()).limit(LIMIT).all())
        out["packages"] = [{"id": s.id, "client_id": s.client_id, "title": f"{s.client.name} · {s.plan.name}",
                            "sub": f"{s.sessions_remaining} of {s.sessions_total} left · {s.status}"} for s in rows]
    if can("/api/payments/"):
        conds = [models.Client.name.ilike(like), models.Payment.notes.ilike(like)]
        if re.fullmatch(r"\d+(\.\d+)?", term):
            conds.append(models.Payment.amount == float(term))
        rows = (db.query(models.Payment).outerjoin(models.Client).filter(or_(*conds))
                .order_by(models.Payment.paid_at.desc()).limit(LIMIT).all())
        out["payments"] = [{"id": p.id, "client_id": p.client_id, "title": f"{p.client.name if p.client else 'Other income'} · {p.amount:,.2f}",
                            "sub": f"{when(p.paid_at)} · {p.method}{' · refund' if p.amount < 0 else ''}"} for p in rows]
    if can("/api/leads/"):
        rows = (db.query(models.Lead).filter(or_(models.Lead.name.ilike(like), models.Lead.email.ilike(like), phone_match(models.Lead.phone)))
                .order_by(models.Lead.created_at.desc()).limit(LIMIT).all())
        out["leads"] = [{"id": l.id, "title": l.name, "sub": " · ".join(filter(None, [l.phone, l.source, l.status.replace('_', ' ')]))} for l in rows]
    return out
